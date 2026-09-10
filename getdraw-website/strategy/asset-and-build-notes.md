# Asset and website build notes

## Current brand assets

The repository currently contains these getdraw assets under `public/`:

| Asset | Dimensions | Recommended use |
| --- | --: | --- |
| `logo-head.png` | 328 × 328 | Large square/head treatment; inspect visually before use |
| `logo-mark.png` | 512 × 512 | Product icon, compact navigation, feature illustrations |
| `logo-mark-dark.png` | 512 × 512 | Product icon on dark backgrounds |
| `og-image.png` | 1200 × 630 | Current application social preview; create public-site variant |
| Favicons and touch icons | Multiple sizes | Browser and install surfaces |

Legacy `AIX-*` source assets remain at the repository root. The current product is branded simply as `getdraw.app` and uses the standalone square mark; `login.getdraw.app` is only its sign-in address. The public website should not default back to the old AIX Draw lockup. A horizontal getdraw.app wordmark is not currently part of the product asset set; render the product name as accessible text beside the mark when navigation or authentication needs it.

## Recommended initial build scope

- Responsive public layout and shared header/footer
- Seven routes in the content map
- Product screenshots or short, real product captures
- Reusable feature, use-case, CTA, FAQ, and trust components
- Direct **Start drawing** and **Sign in** links to `https://login.getdraw.app`
- SEO metadata, social card, sitemap, robots, analytics, and error page
- Accessibility and keyboard review
- Performance budget and responsive image handling
- Legal/footer attribution required by upstream open-source licenses

## Product visuals to capture

Use current app behavior, not conceptual mockups:

1. Dashboard in grid view with search, filters, collections, and workspace selector.
2. Dashboard list view showing collection, role, and modified time.
3. Canvas with sticky notes, bound connector handles, and an elbow-arrow architecture diagram.
4. Canvas assistant editing a selected subset of a board.
5. Agent-created diagram using titled lanes.
6. Live collaboration dialog with QR code and member list, using safe demonstration identities.
7. Settings drawing defaults and Agents & MCP connection list.
8. Trash with restore and retention state.

Do not stage screenshots with real customer data, email addresses, tokens, MCP URLs tied to a real account, or private drawing content.

## Information architecture notes

- Keep the homepage focused on the complete value proposition; do not turn it into a feature inventory.
- Let `/product` carry the detailed feature breadth.
- Let `/ai-canvas` show the conversation-to-editable-output loop.
- Let `/teams` explain the live-room versus snapshot distinction.
- Keep `/trust` factual and narrow until formal policy/compliance materials exist.
- Link the public FAQ to the repository's root `docs/` content when a public documentation experience is added.

## Design direction

The product itself uses a clean light/dark canvas with a warm orange brand mark. The marketing site can pair generous white space, strong dark typography, orange action color, and real canvas fragments. Diagrams should function as the visual language of the page: connectors can lead between sections, frames can group ideas, and sticky notes can carry short proof points without making the site look playful or informal.

Use motion only to clarify the product loop—prompt, editable diagram, collaborative refinement. Respect reduced-motion preferences.

## Content gaps before launch

The following require owner decisions or evidence before new pages are added:

- Pricing and plan entitlements
- Contact-sales motion
- Legal company identity and address for footer/policies
- Terms of service and privacy policy
- Support channel and response expectations
- Customer evidence, testimonials, or case studies
- Formal security/compliance posture
- Workspace provisioning and administration offer
- Whether the public brand is styled `getdraw.app`, `GetDraw`, or another display form outside domain contexts
