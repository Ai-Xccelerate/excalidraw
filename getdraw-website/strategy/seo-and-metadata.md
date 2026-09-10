# SEO and social metadata

## Site-wide defaults

- Site name: `getdraw.app`
- Canonical origin: `https://www.getdraw.app`
- Product application: `https://login.getdraw.app`
- Default title: `getdraw.app — Turn ideas into editable diagrams`
- Default description: `Draw, diagram, collaborate, and build with AI on one fast, editable canvas.`
- Social image target: 1200 × 630 PNG or WebP
- Primary social image source available now: `public/og-image.png`

The existing app metadata uses `login.getdraw.app`. Create a separate public-site social image and canonical metadata during the website build rather than reusing application URLs blindly.

## Page metadata

| Route | Title | Description |
| --- | --- | --- |
| `/` | getdraw.app — Turn ideas into editable diagrams | Draw, diagram, collaborate, and build with AI on one fast, editable canvas. |
| `/product` | Product — getdraw.app | A complete visual workspace for drawing, diagramming, organizing, sharing, and working with AI. |
| `/ai-canvas` | AI Canvas — getdraw.app | Create and revise editable diagrams with a canvas-aware AI drawing partner. |
| `/teams` | Teams — getdraw.app | Draw together live, organize shared work, and send the right kind of link. |
| `/use-cases` | Use Cases — getdraw.app | Use getdraw.app for architecture, product planning, processes, workshops, wireframes, and AI-assisted visual work. |
| `/trust` | Trust and Control — getdraw.app | Understand how getdraw.app handles access, sharing, agent permissions, and drawing recovery. |
| `/faq` | Frequently Asked Questions — getdraw.app | Answers about drawing, AI, collaboration, sharing, exports, accounts, and agent connections. |

## Search themes

Use naturally in headings and body copy; do not stuff keywords.

- AI diagram maker
- collaborative whiteboard
- editable AI diagrams
- AI flowchart generator
- Mermaid diagram editor
- architecture diagram tool
- process mapping canvas
- AI canvas assistant
- MCP drawing tool
- visual workspace for teams
- wireframe to HTML

## Structured data recommendations

- `SoftwareApplication` on the homepage, without fabricated price or rating fields.
- `FAQPage` only for questions visibly rendered on `/faq`.
- `WebSite` and `Organization` with confirmed legal/brand information.
- Breadcrumb structured data on interior pages.

## Indexing boundaries

The marketing origin should be indexable. Account, dashboard, drawing, OAuth consent, reset, and verification routes on `login.getdraw.app` should not be treated as marketing landing pages. Review robots, canonical tags, and authenticated drawing privacy before launch.

## Suggested social copy

**Title:** Turn ideas into editable diagrams  
**Description:** Draw by hand, build with AI, and work live with your team on one visual canvas.
