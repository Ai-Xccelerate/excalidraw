# Text to diagram, Mermaid, and wireframe to code

The editor provides three generation paths in addition to the Canvas assistant.

## Text to diagram

Open the text-to-diagram chat and describe the diagram you want. The app streams the generated Mermaid definition, previews it, and lets you insert the result as editable canvas elements.

Use follow-up messages to refine the diagram before insertion. The dialog can show the generated Mermaid source, retry generation, or attempt an automatic repair when the result is invalid.

The current generator is intended for common flowchart, sequence, class, state, and entity-relationship requests. Results depend on the generated syntax and the diagram converter's support.

## Mermaid to editable canvas

Select the Mermaid icon in the main toolbar, enter a Mermaid definition, review the preview, and choose **Insert**.

The in-editor converter supports flowchart, sequence, class, and entity-relationship diagrams as editable elements. Other Mermaid types may be rendered as an image. If parsing fails, edit the source or use the available auto-fix path.

This is distinct from the external-agent MCP tool, whose current server-side Mermaid path intentionally accepts flowcharts only. See [Agents and MCP](../settings/agents-and-mcp.md).

## Wireframe to code

The diagram-to-code feature can turn a selected wireframe area into generated HTML:

1. Create a wireframe using shapes and text.
2. Choose the wireframe/code generation action when available.
3. Select the region to convert.
4. Review the generated HTML preview.

The service sends an image of the selected wireframe and extracted text labels to the configured AI model. Treat generated HTML as a starting point: review accessibility, responsiveness, security, and production integration before using it in a real application.

## Usage limits

Each AI feature has a server-enforced daily allowance. The text-to-diagram interface reports remaining requests. The configured allowance may differ by environment, so rely on the count shown in the app rather than a fixed number in this guide.

## Choose the right tool

| Goal | Best starting point |
| --- | --- |
| Draw and refine through conversation while using the current board | Canvas assistant |
| Generate a new diagram from a plain-language description | Text to diagram |
| Insert known Mermaid source | Mermaid toolbar |
| Turn a visual UI sketch into HTML | Wireframe to code |
| Ask Claude, ChatGPT, or another external agent to create a saved drawing | MCP connection |
