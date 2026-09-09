# Files, libraries, imports, and exports

getdraw.app combines account-saved drawings with portable files, images, shareable snapshots, and reusable shape libraries.

## Browse account drawings from the editor

Select the folder button to open **Your drawings**. The list is scoped to the personal or shared workspace selected on the dashboard and is ordered by most recently updated. Select a drawing to open it, or choose **Dashboard** to return to the full organizer.

## Save a portable drawing file

Open the main menu and choose **Save to file** or **Save as**. The downloaded `.excalidraw` file contains editable scene data and can be kept as a backup, placed in versioned storage, or sent to another user.

Choose **Open** to load a supported drawing file. Loading a file replaces the current canvas; when prompted, export the current work first if you need to keep it.

## Export an image

Choose **Export image** to create PNG or SVG output or copy an image to the clipboard. Depending on the selected format, export controls include:

- Include the canvas background.
- Export only selected objects.
- Render using dark mode.
- Choose scale and padding.
- Embed scene data in PNG or SVG so a compatible editor can restore it later.

An image without embedded scene data is a presentation asset, not an editable backup.

## Export a read-only link

Open **Share**, then choose **Export to Link**. This uploads an encrypted snapshot and returns a link that opens in view-only mode without requiring sign-in.

Important behaviors:

- The snapshot is separate from the original drawing.
- Later edits to the original do not update an existing snapshot.
- Anyone with the full link can view the snapshot.
- The decryption key is carried in the link fragment rather than sent to the storage service.

For ongoing work with other people, use live collaboration instead.

## Use the shape library

Open **Library** from the toolbar to use reusable groups of shapes. The app includes a curated default library for AI architecture, agentic workflows, cloud infrastructure, and related diagram components.

You can also:

- Select objects and add them to your personal library.
- Search library items.
- Import a compatible `.excalidrawlib` file.
- Export your personal library for backup or reuse.
- Remove or reset personal library items.

Library items remain editable after being placed on the canvas.

## Paste and import content

The editor supports normal clipboard operations, plain-text paste, images, and compatible chart data. Unsupported or oversized files produce an error instead of being silently ignored.
