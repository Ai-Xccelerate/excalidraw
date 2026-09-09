# Troubleshooting and recovery

## I cannot sign in

- Confirm that the email address has been verified.
- Check the password and use **Forgot password?** if needed.
- A password change or reset invalidates older sessions; sign in again.
- If the app returns to sign-in during use, the stored session was rejected or expired.

## I did not receive an account email

- Check spam, quarantine, and mail filtering.
- Confirm the address was typed correctly.
- Wait briefly before requesting another link.
- Verification links expire after 24 hours; password-reset links expire after one hour.

For privacy, the reset screen does not confirm whether an account exists.

## My drawing is missing from the dashboard

- Clear the search field and select **All drawings**.
- Check the current collection and choose **All drawings**.
- Check the workspace selector; the drawing may be in Personal or another workspace.
- Look under **Shared with you**.
- Open **Trash** if you own the drawing and may have deleted it.

## I cannot edit or delete a drawing

Check the role shown on its dashboard card or in list view. Viewers cannot edit. Editors can edit and rename but cannot delete or manage members. Only the owner can move a drawing to Trash, restore it, permanently delete it, or manage invitations.

## Canvas navigation feels wrong

Use the **Auto / Mouse / Trackpad** control in the lower-left corner. Choose Mouse for wheel zoom and right-drag panning, or Trackpad for two-finger panning and pinch zooming.

## The Canvas assistant changed too much

Use undo immediately. For the next request, select only the relevant objects before opening or using the assistant, and describe the exact change. Save a portable file before large automated transformations when the work is important.

## The assistant cannot read my attachment

The current assistant reads images and text-based formats such as TXT, Markdown, CSV, TSV, JSON, YAML, and logs. It does not parse PDF or Word files. Convert the relevant section to text or attach an image. Text attachments are truncated after 20,000 characters.

## An AI tool is unavailable

AI tools require sign-in, server-side AI configuration, and remaining daily allowance. Retry transient errors. If the limit is reached, wait for the daily reset. If the service is not configured, manual drawing, Mermaid insertion, file operations, and collaboration remain available.

## Collaboration is offline or not updating

- Confirm that every participant is signed in and has drawing access.
- Check the browser's network connection.
- A drawing in Trash cannot be joined.
- A removed member may remain connected for only a brief permission-cache interval before access is enforced.
- Export a local file if the app warns that changes cannot be saved.

## A shared link does not show my latest edits

**Export to Link** creates a fixed snapshot. Create a new shareable link after making changes, or use live collaboration for a continuously updated shared drawing.

## I opened the wrong file or link over my canvas

The app warns before replacing existing content with external scene data. If replacement already happened, use undo when available or restore from a previously saved `.excalidraw` file. Image exports without embedded scene data cannot restore a fully editable drawing.

## The drawing is too large to export or share

Remove unnecessary or distant objects, resize very large images, or divide the work into multiple drawings. A shareable snapshot has an upload size cap, and extremely spread-out elements can also make image rendering fail.
