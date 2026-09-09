"""End-to-end check of the MCP connection flow.

Run it against a throwaway Postgres — it creates a user and a couple of
drawings:

    createdb aixdraw_test
    DATABASE_URL=postgresql://localhost/aixdraw_test python tests/test_mcp_flow.py

It walks the path a real client takes: discovery, dynamic registration,
authorize, consent, token exchange, then the MCP tools themselves, and checks
the things that would quietly break the integration — PKCE, single-use codes,
redirect_uri pinning, scope enforcement, and revocation.
"""

import base64, hashlib, os, pathlib, secrets, sys, uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", f"postgresql://{os.environ['USER']}@localhost:5432/aixdraw_test")
os.environ.setdefault("AUTH_SECRET", "0123456789012345678901234567890123456789")
os.environ.setdefault("PUBLIC_API_URL", "http://localhost:8000")
os.environ.setdefault("PUBLIC_APP_URL", "http://localhost:3000")

from fastapi.testclient import TestClient
import main
from db import SessionLocal
from models import User
from auth import hash_password, create_access_token

client = TestClient(main.app, follow_redirects=False)

# a verified account to authorize with
db = SessionLocal()
email = f"mcp-{uuid.uuid4().hex[:8]}@example.com"
user = User(email=email, password_hash=hash_password("supersecret1"), username="rahul")
from datetime import datetime, timezone
user.email_verified_at = datetime.now(timezone.utc)
db.add(user); db.commit(); db.refresh(user)
session_token = create_access_token(user)
AUTH = {"Authorization": f"Bearer {session_token}"}

def check(label, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + label + ("" if cond else f"  <- {extra}"))
    return cond

ok = True
# 1. discovery
meta = client.get("/.well-known/oauth-authorization-server").json()
ok &= check("discovery advertises S256 PKCE", meta["code_challenge_methods_supported"] == ["S256"], meta)
res_meta = client.get("/.well-known/oauth-protected-resource").json()
ok &= check("resource metadata points at /mcp", res_meta["resource"].endswith("/mcp"), res_meta)

# 1b. with PUBLIC_API_URL unset the URLs fall back to the host that was called,
# rather than degrading to a bare "/mcp" nobody can connect to
import oauth as oauth_module
configured = oauth_module.PUBLIC_API_URL
oauth_module.PUBLIC_API_URL = ""
oauth_module.ALLOWED_API_HOSTS = {"api.example.com"}
derived = client.get("/.well-known/oauth-protected-resource",
                     headers={"host": "api.example.com", "x-forwarded-proto": "https"}).json()
ok &= check("discovery falls back to the requested host",
            derived["resource"] == "https://api.example.com/mcp", derived)
derived_settings = client.get("/api/settings", headers={**AUTH, "host": "api.example.com",
                                                        "x-forwarded-proto": "https"}).json()
ok &= check("settings shows an absolute MCP url without configuration",
            derived_settings["mcp_endpoint"] == "https://api.example.com/mcp", derived_settings)

# a Host header is set by whoever is calling, so an unrecognised one must not
# become the issuer clients trust
poisoned = client.get("/.well-known/oauth-authorization-server",
                      headers={"host": "evil.example", "x-forwarded-proto": "https"}).json()
ok &= check("a spoofed Host cannot poison the issuer", poisoned["issuer"] == "", poisoned)
poisoned_fwd = client.get("/.well-known/oauth-authorization-server",
                          headers={"host": "api.example.com",
                                   "x-forwarded-host": "evil.example"}).json()
ok &= check("a spoofed X-Forwarded-Host cannot poison the issuer",
            poisoned_fwd["issuer"] == "", poisoned_fwd)
oauth_module.PUBLIC_API_URL = configured
oauth_module.ALLOWED_API_HOSTS = oauth_module._allowed_api_hosts()

# 2. unauthenticated /mcp challenges with where to authorize
unauth = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
ok &= check("bare /mcp returns 401", unauth.status_code == 401, unauth.status_code)
ok &= check("401 carries resource_metadata", "resource_metadata=" in unauth.headers.get("www-authenticate", ""),
            unauth.headers.get("www-authenticate"))

# 3. dynamic client registration
reg = client.post("/oauth/register", json={
    "client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
}).json()
client_id = reg["client_id"]
ok &= check("dynamic registration issues a client_id", client_id.startswith("aixd_client_"), reg)
bad = client.post("/oauth/register", json={"client_name": "x", "redirect_uris": ["ftp://nope"]})
ok &= check("rejects a non-https redirect", bad.status_code == 400, bad.status_code)

# 4. authorize -> consent screen
verifier = secrets.token_urlsafe(48)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
auth_res = client.get("/oauth/authorize", params={
    "response_type": "code", "client_id": client_id,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "code_challenge": challenge, "code_challenge_method": "S256",
    "state": "xyz", "scope": "drawings:read drawings:write profile",
})
ok &= check("authorize redirects to the consent screen",
            auth_res.status_code == 302 and "/oauth/consent" in auth_res.headers["location"],
            auth_res.headers.get("location"))
spoof = client.get("/oauth/authorize", params={
    "response_type": "code", "client_id": client_id,
    "redirect_uri": "https://evil.example/callback", "code_challenge": challenge,
})
ok &= check("unregistered redirect_uri is refused", spoof.status_code == 400, spoof.status_code)

# 5. consent approval (the app calls this with the user's session)
approve = client.post("/api/oauth/approve", headers=AUTH, json={
    "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "state": "xyz", "code_challenge": challenge, "code_challenge_method": "S256",
    "scope": "drawings:read drawings:write profile", "resource": None,
}).json()
code = approve["redirect_to"].split("code=")[1].split("&")[0]
ok &= check("approval returns a redirect carrying the code", bool(code), approve)

# 6. token exchange
wrong = client.post("/oauth/token", data={
    "grant_type": "authorization_code", "code": code,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "client_id": client_id, "code_verifier": "not-the-verifier",
})
ok &= check("a bad PKCE verifier is rejected", wrong.status_code == 400, wrong.text)
# that attempt burned the single-use code, so run the real flow again
approve = client.post("/api/oauth/approve", headers=AUTH, json={
    "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "state": "xyz", "code_challenge": challenge, "code_challenge_method": "S256",
    "scope": "drawings:read drawings:write profile", "resource": None,
}).json()
code = approve["redirect_to"].split("code=")[1].split("&")[0]
tok = client.post("/oauth/token", data={
    "grant_type": "authorization_code", "code": code,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "client_id": client_id, "code_verifier": verifier,
}).json()
access = tok.get("access_token", "")
ok &= check("token exchange returns an access token", access.startswith("aixd_at_"), tok)
replay = client.post("/oauth/token", data={
    "grant_type": "authorization_code", "code": code,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "client_id": client_id, "code_verifier": verifier,
})
ok &= check("the code cannot be replayed", replay.status_code == 400, replay.text)

MCP = {"Authorization": f"Bearer {access}"}
def rpc(method, params=None, rid=1):
    return client.post("/mcp", headers=MCP, json={
        "jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}).json()

# 7. MCP handshake and tools
init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
ok &= check("initialize returns serverInfo", init["result"]["serverInfo"]["name"] == "getdraw", init)
tools = [t["name"] for t in rpc("tools/list")["result"]["tools"]]
ok &= check("tools are listed", "create_mermaid_diagram" in tools, tools)

# 8. preferences reach the drawing an agent makes
client.patch("/api/settings/editor-defaults", headers=AUTH,
             json={"editor_defaults": {"font_family": "code", "arrow_type": "elbow", "font_size": 28}})
prefs = rpc("tools/call", {"name": "get_editor_defaults", "arguments": {}})["result"]["content"][0]["text"]
ok &= check("agent reads the saved defaults", "font_family: code" in prefs, prefs)

made = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "Onboarding", "mermaid": """flowchart TD
    A[Sign up] --> B{Email verified?}
    B -->|yes| C[Create workspace]
    B -->|no| D(Resend link)
    D --> B
    C --> E[Start drawing]"""}})["result"]
text = made["content"][0]["text"]
ok &= check("mermaid diagram is created", "Created 'Onboarding'" in text and not made["isError"], text)

drawing_id = text.rsplit("/d/", 1)[1].split()[0].strip()
from models import Drawing
db.expire_all()
drawing = db.get(Drawing, uuid.UUID(drawing_id))
kinds = [e["type"] for e in drawing.elements]
ok &= check("scene has boxes, labels and arrows",
            kinds.count("arrow") == 5 and "text" in kinds and "diamond" in kinds, kinds)
label = next(e for e in drawing.elements if e["type"] == "text" and e["text"] == "Sign up")
ok &= check("labels use the chosen font", label["fontFamily"] == 3 and label["fontSize"] == 28, label)
arrow = next(e for e in drawing.elements if e["type"] == "arrow")
ok &= check("arrows honour the elbow preference", arrow["elbowed"] is True, arrow)
ok &= check("arrows are bound to their boxes",
            arrow["startBinding"]["mode"] == "orbit" and "fixedPoint" in arrow["startBinding"], arrow)

# 9. structured flowchart tool
flow = rpc("tools/call", {"name": "create_flowchart", "arguments": {
    "title": "Deal flow",
    "nodes": [{"id": "a", "label": "Lead"}, {"id": "b", "label": "Qualify", "shape": "diamond"},
              {"id": "c", "label": "Won"}, {"id": "d", "label": "Lost"}],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "label": "yes"},
              {"from": "b", "to": "d", "label": "no"}],
    "direction": "right"}})["result"]
ok &= check("flowchart tool draws", "Created 'Deal flow'" in flow["content"][0]["text"], flow)

# 9b. the mermaid the agent actually sent us, with the pieces that used to be
# mangled: stadium brackets, <br/> line breaks, link styles and classDef colour
rich = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "RAG decision tree", "mermaid": """flowchart TD
    A([Your corpus]) --> B{Small and stable?}
    B -->|yes| C[RUNG 0<br/>Long context]
    B -->|no| D[[RUNG 1<br/>Agent + tools]]
    D -.-> E((Rerank))
    E --- F[/Eval passing?/]
    F ==> G([SHIP IT])
    classDef done fill:#d3f9d8,stroke:#2b8a3e
    class G done"""}})["result"]
ok &= check("the rich mermaid renders", not rich["isError"], rich)
rich_id = rich["content"][0]["text"].rsplit("/d/", 1)[1].split()[0].strip()
db.expire_all()
rich_scene = db.get(Drawing, uuid.UUID(rich_id)).elements
labels = {e["text"] for e in rich_scene if e["type"] == "text"}
ok &= check("stadium brackets do not leak into the label", "Your corpus" in labels, sorted(labels))
ok &= check("<br/> becomes a real line break", "RUNG 0\nLong context" in labels, sorted(labels))
ok &= check("classDef colours the node it names",
            any(e["type"] in ("rectangle", "ellipse") and e["backgroundColor"] == "#d3f9d8"
                for e in rich_scene), None)
ok &= check("a dotted link is drawn dotted",
            any(e["type"] == "arrow" and e["strokeStyle"] == "dashed" for e in rich_scene), None)
ok &= check("an undirected --- link has no arrowhead",
            any(e["type"] == "arrow" and e["endArrowhead"] is None for e in rich_scene), None)

# 9c. a hyphen in a label is a hyphen, not a link
hyphen = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "Reranker", "mermaid": """flowchart TD
    A[Cross-encoder reranker] --> B[RUNG 3 - START HERE]"""}})["result"]
ok &= check("a hyphen inside a label does not split the node", not hyphen["isError"], hyphen)
hyphen_id = hyphen["content"][0]["text"].rsplit("/d/", 1)[1].split()[0].strip()
db.expire_all()
hyphen_labels = {e["text"] for e in db.get(Drawing, uuid.UUID(hyphen_id)).elements
                 if e["type"] == "text"}
ok &= check("the hyphenated label is intact",
            {"Cross-encoder reranker", "RUNG 3 - START HERE"} <= hyphen_labels,
            sorted(hyphen_labels))

# 9c-2. input that would otherwise draw something broken
loop = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "Retry", "mermaid": "flowchart TD\n A[Retry] --> A"}})["result"]
loop_id = loop["content"][0]["text"].rsplit("/d/", 1)[1].split()[0].strip()
db.expire_all()
loop_arrow = next(e for e in db.get(Drawing, uuid.UUID(loop_id)).elements
                  if e["type"] == "arrow")
ok &= check("a self-loop goes around the node, not through it",
            len(loop_arrow["points"]) > 2, loop_arrow["points"])

wide_label = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "Long", "mermaid": "flowchart TD\n A[" + "x" * 400 + "] --> B[ok]"}})["result"]
wide_id = wide_label["content"][0]["text"].rsplit("/d/", 1)[1].split()[0].strip()
db.expire_all()
wide_box = next(e for e in db.get(Drawing, uuid.UUID(wide_id)).elements
                if e["type"] == "rectangle")
ok &= check("an unbreakable label is wrapped, not left overflowing",
            wide_box["height"] > 300, wide_box["height"])

# 9d. children line up under their parents rather than stacking in a column
tree = rpc("tools/call", {"name": "create_flowchart", "arguments": {
    "title": "Layout", "direction": "down",
    "nodes": [{"id": i, "label": i} for i in ["root", "l", "r", "join"]],
    "edges": [{"from": "root", "to": "l"}, {"from": "root", "to": "r"},
              {"from": "l", "to": "join"}, {"from": "r", "to": "join"}]}})["result"]
tree_id = tree["content"][0]["text"].rsplit("/d/", 1)[1].split()[0].strip()
db.expire_all()
boxes = {e["id"]: e for e in db.get(Drawing, uuid.UUID(tree_id)).elements
         if e["type"] == "rectangle"}
labels = {e["containerId"]: e["text"] for e in db.get(Drawing, uuid.UUID(tree_id)).elements
          if e["type"] == "text" and e.get("containerId")}
centres = {labels[bid]: box["x"] + box["width"] / 2 for bid, box in boxes.items()
           if bid in labels}
ok &= check("branches are placed either side of their parent",
            centres["l"] < centres["root"] < centres["r"], centres)
ok &= check("a merge point sits between the branches it joins",
            abs(centres["join"] - (centres["l"] + centres["r"]) / 2) < 2, centres)

flattened = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "Pipeline", "mermaid": """flowchart LR
    subgraph Ingest
      A[Load] --> B[Chunk]
    end
    B --> C[Answer]"""}})["result"]
ok &= check("a flattened subgraph is reported, not hidden",
            "flattened" in flattened["content"][0]["text"], flattened)

bad_mermaid = rpc("tools/call", {"name": "create_mermaid_diagram", "arguments": {
    "title": "x", "mermaid": "sequenceDiagram\n A->>B: hi"}})["result"]
ok &= check("an unsupported diagram type is reported, not half-drawn",
            bad_mermaid["isError"] and "flowchart" in bad_mermaid["content"][0]["text"], bad_mermaid)

# a bad argument is answered, not leaked as a python traceback string
junk = rpc("tools/call", {"name": "list_drawings", "arguments": {"limit": "many"}})["result"]
ok &= check("a bad argument gets a readable message",
            "limit must be a number" in junk["content"][0]["text"], junk)

listed = rpc("tools/call", {"name": "list_drawings", "arguments": {}})["result"]["content"][0]["text"]
ok &= check("the drawings come back in list_drawings", "Onboarding" in listed and "Deal flow" in listed, listed)

# 10. scopes are enforced
narrow = client.post("/api/oauth/approve", headers=AUTH, json={
    "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "state": "", "code_challenge": challenge, "code_challenge_method": "S256",
    "scope": "drawings:read", "resource": None}).json()
ncode = narrow["redirect_to"].split("code=")[1].split("&")[0]
ntok = client.post("/oauth/token", data={
    "grant_type": "authorization_code", "code": ncode,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "client_id": client_id, "code_verifier": verifier}).json()
read_only = {"Authorization": f"Bearer {ntok['access_token']}"}
denied = client.post("/mcp", headers=read_only, json={"jsonrpc": "2.0", "id": 9, "method": "tools/call",
    "params": {"name": "create_drawing", "arguments": {"title": "nope"}}}).json()
ok &= check("a read-only token cannot create drawings",
            denied["result"]["isError"] and "drawings:write" in denied["result"]["content"][0]["text"], denied)

# 10b. declining is delivered through the API, never to a caller-supplied URL
open_redirect = client.post("/api/oauth/deny", headers=AUTH, json={
    "client_id": client_id, "redirect_uri": "https://evil.example/steal", "state": "xyz"}).json()
ok &= check("deny refuses an unregistered redirect_uri", open_redirect["redirect_to"] is None, open_redirect)
denied_ok = client.post("/api/oauth/deny", headers=AUTH, json={
    "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback", "state": "xyz"}).json()
ok &= check("deny returns access_denied to the registered redirect",
            denied_ok["redirect_to"].startswith("https://claude.ai/api/mcp/auth_callback?error=access_denied"),
            denied_ok)

# 10c. an unknown scope must not escalate into every scope
import oauth as oauth_mod
ok &= check("only-unknown scopes grant nothing", oauth_mod.normalize_scope("wat") == "",
            oauth_mod.normalize_scope("wat"))
ok &= check("a partly-known scope keeps the known part",
            oauth_mod.normalize_scope("wat drawings:read") == "drawings:read",
            oauth_mod.normalize_scope("wat drawings:read"))
bad_scope = client.get("/oauth/authorize", params={
    "response_type": "code", "client_id": client_id,
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "code_challenge": challenge, "code_challenge_method": "S256", "scope": "everything"})
ok &= check("authorize refuses a scope it can grant nothing for",
            "error=invalid_scope" in bad_scope.headers.get("location", ""),
            bad_scope.headers.get("location"))

# 10d. a callback that already has a query string still gets a readable code
q_client = client.post("/oauth/register", json={
    "client_name": "Tenanted", "redirect_uris": ["https://app.example/cb?tenant=acme"]}).json()
q_approve = client.post("/api/oauth/approve", headers=AUTH, json={
    "client_id": q_client["client_id"], "redirect_uri": "https://app.example/cb?tenant=acme",
    "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256",
    "scope": "drawings:read", "resource": None}).json()
from urllib.parse import urlsplit, parse_qs
q_parsed = parse_qs(urlsplit(q_approve["redirect_to"]).query)
ok &= check("an existing query string is preserved, not clobbered",
            q_parsed.get("tenant") == ["acme"] and len(q_parsed.get("code", [])) == 1,
            q_approve["redirect_to"])

# 10e. a redirect_uri carrying a fragment is refused at registration
frag = client.post("/oauth/register", json={
    "client_name": "Fragment", "redirect_uris": ["https://app.example/cb#/route"]})
ok &= check("a fragment in the callback is refused", frag.status_code == 400, frag.status_code)

# 10f. a confidential client must authenticate to refresh
conf = client.post("/oauth/register", json={
    "client_name": "Confidential", "redirect_uris": ["https://conf.example/cb"],
    "token_endpoint_auth_method": "client_secret_post"}).json()
conf_approve = client.post("/api/oauth/approve", headers=AUTH, json={
    "client_id": conf["client_id"], "redirect_uri": "https://conf.example/cb",
    "state": "", "code_challenge": challenge, "code_challenge_method": "S256",
    "scope": "drawings:read", "resource": None}).json()
conf_code = parse_qs(urlsplit(conf_approve["redirect_to"]).query)["code"][0]
conf_tok = client.post("/oauth/token", data={
    "grant_type": "authorization_code", "code": conf_code,
    "redirect_uri": "https://conf.example/cb", "client_id": conf["client_id"],
    "client_secret": conf["client_secret"], "code_verifier": verifier}).json()
no_secret = client.post("/oauth/token", data={
    "grant_type": "refresh_token", "refresh_token": conf_tok["refresh_token"]})
ok &= check("refresh without the client secret is refused", no_secret.status_code == 400,
            no_secret.text)
still_good = client.post("/oauth/token", data={
    "grant_type": "refresh_token", "refresh_token": conf_tok["refresh_token"],
    "client_id": conf["client_id"], "client_secret": conf["client_secret"]})
ok &= check("a failed attempt did not burn the token", still_good.status_code == 200,
            still_good.text)

# 11. a refresh token can be spent once
refreshed = client.post("/oauth/token", data={
    "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]}).json()
ok &= check("refresh returns a new pair", refreshed.get("access_token", "").startswith("aixd_at_"), refreshed)
reused = client.post("/oauth/token", data={
    "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
ok &= check("a spent refresh token is dead", reused.status_code == 400, reused.text)

# 11b. two clients racing the same refresh token: exactly one wins
race_tok = client.post("/oauth/token", data={
    "grant_type": "authorization_code",
    "code": parse_qs(urlsplit(client.post("/api/oauth/approve", headers=AUTH, json={
        "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "state": "", "code_challenge": challenge, "code_challenge_method": "S256",
        "scope": "drawings:read", "resource": None}).json()["redirect_to"]).query)["code"][0],
    "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
    "client_id": client_id, "code_verifier": verifier}).json()

import threading
outcomes: list[int] = []
def redeem():
    response = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": race_tok["refresh_token"]})
    outcomes.append(response.status_code)
threads = [threading.Thread(target=redeem) for _ in range(4)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
ok &= check("only one of four concurrent redemptions succeeds",
            outcomes.count(200) == 1, outcomes)

# 11c. a token only ever reaches its own account's drawings
from models import User as UserModel
from oauth import issue_tokens as _issue
other = UserModel(email=f"other-{uuid.uuid4().hex[:6]}@example.com",
                  password_hash=hash_password("supersecret1"))
other.email_verified_at = datetime.now(timezone.utc)
db.add(other); db.commit(); db.refresh(other)
other_access, _, _ = _issue(db, client_id=client_id, user_id=other.id,
                            scope="drawings:read drawings:write profile")
other_headers = {"Authorization": f"Bearer {other_access}"}
stolen = client.post("/mcp", headers=other_headers, json={
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {"name": "get_drawing", "arguments": {"drawing_id": drawing_id}}}).json()
ok &= check("another account's drawing is invisible even with its id",
            stolen["result"]["isError"], stolen)
their_list = client.post("/mcp", headers=other_headers, json={
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "list_drawings", "arguments": {}}}).json()
ok &= check("and it is not in their listing",
            "Onboarding" not in their_list["result"]["content"][0]["text"],
            their_list["result"]["content"][0]["text"])

# 12. settings page sees the connection, and revoking it cuts access
conns = client.get("/api/settings/connections", headers=AUTH).json()
ok &= check("the connection is listed in settings", any(c["client_name"] == "Claude" for c in conns), conns)
client.delete(f"/api/settings/connections/{client_id}", headers=AUTH)
after = client.post("/mcp", headers=MCP, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
ok &= check("revoking disconnects the agent", after.status_code == 401, after.status_code)

print("\n" + ("ALL PASS" if ok else "SOME FAILURES"))
sys.exit(0 if ok else 1)
