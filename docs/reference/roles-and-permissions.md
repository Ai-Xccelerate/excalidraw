# Roles and permissions

Permissions are enforced for both saved API changes and live collaboration traffic.

## Drawing roles

| Capability                       | Owner | Editor | Viewer |
| -------------------------------- | :---: | :----: | :----: |
| Open the drawing                 |  Yes  |  Yes   |  Yes   |
| See live participant presence    |  Yes  |  Yes   |  Yes   |
| Edit and save canvas content     |  Yes  |  Yes   |   No   |
| Rename or move the drawing       |  Yes  |  Yes   |   No   |
| Send live scene changes          |  Yes  |  Yes   |   No   |
| Invite or remove drawing members |  Yes  |   No   |   No   |
| Move the drawing to Trash        |  Yes  |   No   |   No   |
| Restore or permanently delete it |  Yes  |   No   |   No   |

Viewers may broadcast presence details such as pointer position, idle state, and visible canvas bounds, but they cannot broadcast scene mutations.

## Workspace roles

| Capability                                       | Admin | Member |
| ------------------------------------------------ | :---: | :----: |
| See workspace drawings and collections           |  Yes  |  Yes   |
| Edit workspace drawings                          |  Yes  |  Yes   |
| Create drawings and collections in the workspace |  Yes  |  Yes   |
| Invite or remove workspace members               |  Yes  |   No   |

The workspace administration endpoints support admin and member roles, but workspace creation and member administration do not yet have controls in the current dashboard UI.

## Pending invitations

If an invitation is sent to an address with no verified account, it stays pending. It converts to membership after that address is verified. This prevents an unverified account from using an address it has not proven it controls.

## Read-only snapshot links

A shareable snapshot is not a drawing membership. Anyone with the full exported link can decrypt and view that fixed snapshot without signing in, but cannot use it to open or modify the original account drawing.

## MCP permissions

External agents receive explicit OAuth scopes. The current scopes separate drawing reads, drawing creation, and profile/default reads. See [Agents and MCP](../settings/agents-and-mcp.md).
