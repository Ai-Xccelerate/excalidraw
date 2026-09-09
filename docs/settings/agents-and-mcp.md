# Connect agents with MCP

getdraw.app exposes an authenticated Model Context Protocol (MCP) server. A compatible external agent—such as Claude, ChatGPT, Cursor, or another MCP host—can work with drawings after you explicitly sign in and approve its requested access.

## Connect an agent

1. From the dashboard, open **Settings**.
2. Choose **Agents & MCP**.
3. Copy the displayed **Connection URL**.
4. In your agent application, add a custom or remote MCP connector using that URL.
5. The agent opens getdraw.app. Sign in if needed.
6. Review the client name and permissions on the consent screen.
7. Choose **Allow access** or cancel the request.

Nothing is shared with the client until approval completes.

## Available tools

An approved agent can receive only the tools covered by its granted scopes:

| Tool | What it does |
| --- | --- |
| `list_drawings` | Lists up to 100 of your owned, active drawings, newest first |
| `get_drawing` | Reads one owned drawing's title, element count, and visible text |
| `get_editor_defaults` | Reads saved font, stroke, arrow, and node preferences |
| `create_flowchart` | Creates a new editable flowchart from nodes, edges, direction, and optional titled lanes |
| `create_mermaid_diagram` | Creates an editable drawing from supported Mermaid flowchart source |
| `create_drawing` | Creates an empty saved drawing and returns its link |

Agent-created drawings are saved to your personal drawing area and returned as full links. They use bound labels and connectors and pick up your saved drawing defaults.

## Permissions shown on consent

- `drawings:read` allows listing and reading the limited drawing summary described above.
- `drawings:write` allows creating drawings and diagrams.
- `profile` allows reading drawing preferences used for generation.

The MCP tools are intentionally scoped to drawings owned by the connected account. They do not list shared-workspace drawings or read another person's canvas from a guessed identifier.

## Mermaid support through MCP

The MCP Mermaid tool currently accepts flowchart/graph syntax with common directions, node shapes, line breaks, edge labels, dotted or thick links, fan-out, and class/style colors. It reports unsupported input rather than silently drawing a misleading result.

Important boundaries:

- Mermaid subgraphs are flattened; their nodes remain but the grouping is not preserved.
- Sequence, class, Gantt, and other non-flowchart Mermaid types are rejected by this server-side MCP tool.
- For a diagram composed by the agent itself, `create_flowchart` supports explicit named groups rendered as lane-like regions.

These limits differ from the Mermaid converter inside the editor.

## Review and disconnect agents

Return to **Settings → Agents & MCP** to see connected client names, granted scopes, last-used time, and connection expiry. Select **Disconnect** to revoke a client. Revocation applies to its tokens; you can reconnect later through a new approval flow.

## Example prompts

- “List my recent getdraw.app drawings.”
- “Create a left-to-right architecture flow for browser, API, worker, and database.”
- “Make a customer-support flowchart with Yes and No branches and group it into Intake, Resolution, and Follow-up.”
- “Turn this Mermaid flowchart into an editable getdraw.app drawing.”
