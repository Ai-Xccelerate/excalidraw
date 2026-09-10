# Public claims and release boundaries

Use this matrix during design, copy review, and launch QA. “Safe” means the current repository contains a user-facing path and supporting behavior. Production availability must still be verified on the deployed environment before launch.

## Safe product claims

| Claim | Repository evidence | Copy guidance |
| --- | --- | --- |
| Infinite editable canvas | Core editor and object model | “An infinite canvas for diagrams, whiteboards, and wireframes” |
| Shapes, sticky notes, text, images, frames, arrows, free drawing | Main toolbar and custom sticky-note implementation | List directly |
| Bound connector handles | Custom connector creation and binding | “Drag from a shape to create an arrow that stays connected” |
| Mouse/trackpad modes | Auto, Mouse, and Trackpad footer control | Describe exact gestures |
| Saved account drawings | First-party auth and drawing APIs | “Save drawings to your account” |
| Search, filters, sorting, grid/list | Dashboard controls | List directly |
| Collections | Dashboard and collection APIs | “Organize drawings into collections” |
| Personal and available shared workspace scopes | Workspace selector and scoped APIs | Say “available shared workspaces,” not full self-service admin |
| 90-day recoverable Trash | Trash UI, retention service, tests | State exactly |
| Live collaboration | Authenticated socket rooms and share UI | Avoid unsupported scale or uptime claims |
| Drawing roles | REST and socket enforcement | Owner/editor/viewer are safe to describe |
| Email invitations | Drawing invite UI and pending-invite flow | Current dialog defaults to editor access |
| QR-code room sharing | Collaboration dialog | List directly |
| Read-only snapshot without sign-in | Client-encrypted snapshot backend and view mode | Call it a fixed snapshot, not a live share |
| Client-side encryption for snapshots | Encrypted payload with URL-fragment key | Limit claim to exported shareable snapshots |
| Canvas assistant | Panel, board context, operations, backend | Say it can create/connect/update/delete supported objects |
| Image and text attachments for assistant | Attachment handling | List actual supported text types; exclude PDF/DOCX |
| Dictation when browser-supported | Speech-recognition hook | Always qualify browser support |
| Text-to-diagram | Streaming AI route and dialog | Avoid guaranteed accuracy |
| Mermaid insertion | Editor converter | Explain that unsupported types can become images |
| Wireframe-to-HTML starting point | Diagram-to-code route | Do not call generated code production-ready |
| MCP over OAuth | Discovery, registration, consent, tokens, tools | Say compatible clients; setup varies by client |
| Revocable agent connections | Settings UI and token revocation | List directly |
| Portable file, PNG, SVG, and clipboard export | Editor export paths | List directly |
| Reusable library | Library UI and bundled default library | Avoid claims about a public getdraw marketplace |

## Claims requiring qualification

| Topic | Required qualification |
| --- | --- |
| AI limits | The default backend configuration is not a permanent commercial entitlement; say daily allowances apply and the app shows remaining usage. |
| Mermaid support | The editor and MCP tool have different supported types. Never combine them into one blanket claim. |
| Workspaces | The service and selector exist; dashboard controls for creating and administering workspaces do not. |
| Notifications | Preferences are stored, but the repository does not prove every listed notification email is sent. |
| Encryption | Apply to live-collaboration claims shown by the app and client-encrypted snapshot links, not all account-stored drawings. |
| Mobile | Core app and sharing controls have responsive paths, but the Canvas assistant trigger is hidden in compact mobile UI. |
| Offline/PWA | Upstream PWA components exist, but account persistence, AI, collaboration, and backend saves require network access. Do not sell the full product as offline-first without deployment testing. |
| External agents | Name products as examples only when they support the required remote MCP/OAuth flow in their current version. Confirm before publication. |

## Do not claim yet

- SOC 2, ISO 27001, HIPAA, GDPR compliance certification, or any other formal certification
- End-to-end encryption for all account-saved drawings
- SSO, SCIM, audit logs, admin console, data residency, customer-managed keys, or enterprise retention policy
- Unlimited AI generation
- A specific free tier, paid plan, trial, or price
- Guaranteed uptime, response time, scale, or number of simultaneous collaborators
- Native comments or mentions as an active collaboration feature
- Automatic version history or point-in-time restore beyond Trash recovery and manual portable files
- Production-ready generated HTML
- Support for PDF or Word attachments in the Canvas assistant
- A mobile Canvas assistant experience equivalent to desktop
- Customer names, usage figures, testimonials, awards, or quantified outcomes without separate evidence

## Pre-launch verification

Before the public website ships, verify on the live deployment:

1. Account creation, email delivery, verification, sign-in, reset, and sign-out.
2. Drawing creation, autosave, reload, thumbnail, rename, search, filter, sort, and collection movement.
3. Trash, restore, delete forever, and retention copy.
4. Live collaboration across two authorized accounts, including viewer enforcement if that role is marketed.
5. Export to Link in a signed-out browser.
6. Canvas assistant, attachments, text-to-diagram, Mermaid insertion, and usage-limit states.
7. MCP discovery, OAuth consent, drawing creation, and revocation with each client named on the site.
8. Desktop, tablet, and phone layouts for the marketing site and product entry points.
