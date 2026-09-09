# Sharing and live collaboration

getdraw.app offers two different sharing modes. Choose based on whether recipients should participate or only view a snapshot.

## Live collaboration

Use live collaboration when multiple people need to work in the same drawing.

1. Open the drawing and select **Share** or **Live collaboration**.
2. Choose **Start session**.
3. Enter the name collaborators should see.
4. Copy the collaboration link, use the system share sheet, or let someone scan the QR code.
5. If you own the drawing, enter an email address and choose **Invite** to grant drawing membership.

The member list shows owners, editors, viewers, and invitations pending sign-up. Owners can remove non-owner members or pending invitations.

During a session, authorized collaborators see synchronized canvas changes and participant presence. Selecting a participant can follow their visible canvas location where supported.

### Stop a session

Choose **Stop session** to disconnect your browser from the live room. Other connected participants may continue on their version. Follow the warning shown by the app if stopping could replace locally held content, and export a backup first when needed.

### Access requirements

Live rooms require a valid signed-in account and drawing access. An owner or editor can send scene changes. A viewer can send presence information but cannot modify the saved drawing.

## Invite by email

The owner can invite an existing verified account or an address that has not signed up yet. A new or unverified recipient remains pending until the address is verified. Invitation membership controls ongoing access to the drawing; the collaboration link alone does not bypass that authorization.

The current dialog creates editor invitations by default. Viewer access is supported by the permission model but is not offered as a role selector in this version of the dialog.

## Read-only shareable link

Use **Export to Link** when recipients need a frozen view rather than collaboration.

- It creates a separate encrypted snapshot.
- It opens without sign-in in view-only mode.
- The link does not grant access to the editable account drawing.
- Changes made to the original later are not reflected in that existing link.
- Anyone with the full link can view it, so handle it like a shared document link.

The snapshot is encrypted in the browser before upload. The decryption key is carried in the URL fragment and is not sent to the snapshot storage endpoint.

## Which option should I use?

| Need | Use |
| --- | --- |
| Co-edit a drawing now | Live collaboration |
| Give a teammate ongoing access | Email invitation and live collaboration |
| Let someone view a fixed result without signing in | Export to Link |
| Send a portable editable copy | Save an `.excalidraw` file |
| Place an image in a document or presentation | Export PNG or SVG |
