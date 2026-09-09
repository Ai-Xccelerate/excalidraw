# Canvas assistant

The Canvas assistant is a conversational drawing partner inside the editor. It sees a simplified description of the current board, can focus on selected objects, and can create, connect, restyle, relabel, or remove supported canvas objects.

## Open the assistant

On desktop, select the sparkle button in the upper-right corner. The panel reports whether it is looking at an empty board, the whole board, or selected objects.

The assistant trigger is not currently shown in the compact mobile editor layout.

## Ask it to draw

Describe the result you want, not just a shape list. For example:

- “Draw a left-to-right customer onboarding flow with decision points for identity verification.”
- “Turn these selected boxes into a three-stage pipeline and connect them.”
- “Make the error states pale red and rename the final box to Approved.”
- “Add a self-loop labeled Retry to the failed-processing step.”

Press Enter to send. Use Shift+Enter for a new line. The assistant replies in the transcript, applies any drawing operations to the canvas, selects newly created objects, and shows a receipt summarizing shapes, connections, changes, and removals.

## Work on selected objects

Select one or more objects before sending a message when you want the assistant to change only that part of the board. The status line changes to **Working on … selected objects**. With nothing selected, the assistant can reason about the whole board.

The assistant receives object types, positions, dimensions, colors, labels, and basic connections—not a pixel-perfect screenshot of the canvas unless you attach an image.

## Attach context

Select the paperclip or paste a file into the composer. Up to four files are accepted from one selection.

Supported context includes:

- Images
- Plain text
- Markdown
- CSV and TSV
- JSON
- YAML
- Log files and other text MIME types

Text from an attachment is limited to the first 20,000 characters. PDF and Word files are not read by the current assistant; convert them to text or attach an image of the relevant content. Text attachments are cleared after a turn that produces canvas operations. Attached images appear in the conversation.

## Dictate a prompt

When the browser supports speech recognition, select the microphone to dictate into the message field. Select it again to stop. Review the transcription before sending, especially for names and technical terms.

## Make readable diagrams

The assistant is designed to:

- Use ellipses for start and end states, rectangles for actions, and diamonds for decisions.
- Label decision branches.
- Use titled lanes for diagrams with multiple stages or systems.
- Route connections around shapes and keep labels clear.
- Create editable shapes and bound connectors rather than a flattened image.

You can refine the result conversationally. Manual edits made between messages are included in the next board description.

## Limits and recovery

AI features require a signed-in account, a configured AI service, and remaining daily usage. If a request fails, the panel keeps the conversation and shows an error so you can retry. Use undo to reverse applied canvas changes. Very large boards may be summarized so the assistant can work within a practical context size; selecting the relevant objects is the best way to focus a complex request.
