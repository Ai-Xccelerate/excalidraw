import { useEffect, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import {
  approveOAuthRequest,
  denyOAuthRequest,
  describeOAuthClient,
  type OAuthClientInfo,
} from "../data/backend";

import "./SettingsPage.scss";
import "./OAuthConsentPage.scss";

const SCOPE_COPY: Record<string, string> = {
  "drawings:read": "See your drawings and what's on them",
  "drawings:write": "Create new drawings and diagrams for you",
  profile: "Read your drawing defaults so its diagrams match yours",
};

/** The consent step of the OAuth flow an MCP client starts. The API validated
 * the request before redirecting here, so this screen only has to identify who
 * is asking and let the user say yes or no. */
const OAuthConsentPage = () => {
  const { user } = useAuth();
  const params = new URLSearchParams(window.location.search);
  const clientId = params.get("client_id") ?? "";
  const scope = params.get("scope") ?? "";

  const [client, setClient] = useState<OAuthClientInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!clientId) {
      setError("This authorization link is missing its client id.");
      return;
    }
    describeOAuthClient(clientId)
      .then(setClient)
      .catch((e) => setError(e.message));
  }, [clientId]);

  // the refusal is delivered to the client, so where it goes is decided by the
  // API against the client's registered redirect URIs — a redirect_uri from
  // this page's own query string is attacker-controlled
  const deny = async () => {
    setBusy(true);
    try {
      const { redirect_to } = await denyOAuthRequest({
        client_id: clientId,
        redirect_uri: params.get("redirect_uri") ?? "",
        state: params.get("state") ?? "",
      });
      window.location.href = redirect_to ?? "/dashboard";
    } catch {
      window.location.href = "/dashboard";
    }
  };

  const approve = async () => {
    setBusy(true);
    try {
      const { redirect_to } = await approveOAuthRequest({
        client_id: clientId,
        redirect_uri: params.get("redirect_uri") ?? "",
        state: params.get("state") ?? "",
        code_challenge: params.get("code_challenge") ?? "",
        code_challenge_method: params.get("code_challenge_method") ?? "S256",
        scope,
        resource: params.get("resource") || null,
      });
      window.location.href = redirect_to;
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="aix-consent">
      <div className="aix-consent__card">
        <img
          className="aix-consent__logo"
          src="/logo-mark.png"
          alt="draw.getdraw.app"
        />

        {error ? (
          <>
            <h1>Something's off with this request</h1>
            <p className="aix-consent__error">{error}</p>
            <div className="aix-consent__actions">
              <a className="aix-btn" href="/dashboard">
                Back to draw.getdraw.app
              </a>
            </div>
          </>
        ) : (
          <>
            <h1>
              Connect <strong>{client?.client_name ?? "an agent"}</strong>?
            </h1>
            <p className="aix-consent__lead">
              It's asking to work with your draw.getdraw.app account as{" "}
              <strong>{user?.email}</strong>.
            </p>

            <ul className="aix-consent__scopes">
              {scope
                .split(" ")
                .filter(Boolean)
                .map((item) => (
                  <li key={item}>{SCOPE_COPY[item] ?? item}</li>
                ))}
            </ul>

            {client?.client_uri && (
              <p className="aix-consent__origin">{client.client_uri}</p>
            )}
            <p className="aix-consent__fineprint">
              You can disconnect it at any time from Settings → Agents &amp;
              MCP. Only approve agents you recognise.
            </p>

            <div className="aix-consent__actions">
              <button className="aix-btn" onClick={deny} disabled={busy}>
                Cancel
              </button>
              <button
                className="aix-btn aix-btn--primary"
                onClick={approve}
                disabled={busy || !client}
              >
                {busy ? "Connecting…" : "Connect"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default OAuthConsentPage;
