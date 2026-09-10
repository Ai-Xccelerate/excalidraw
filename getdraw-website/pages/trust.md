---
title: "Trust and Control — getdraw.app"
description: "Understand how getdraw.app handles access, sharing, agent permissions, and drawing recovery."
route: "/trust"
---

# Clear controls for who can see, change, and create

Trust starts with accurate boundaries. getdraw.app separates account access, drawing roles, live collaboration, read-only snapshots, and external-agent permissions so each can be controlled for its job.

## Verified accounts

New accounts prove control of their email address before they can sign in or claim invitations. Verification and password-reset links are single-use and expire. Changing or resetting a password invalidates older application sessions.

## Drawing-level roles

- **Owner:** edit, invite, remove members, move to Trash, restore, and permanently delete.
- **Editor:** edit, save, rename, and organize a shared drawing.
- **Viewer:** open the drawing and participate in presence without sending canvas changes.

The same role checks protect normal saves and real-time collaboration messages.

## Safer deletion

Deleting an owned drawing first moves it to Trash. The full drawing remains recoverable for 90 days unless the owner deliberately deletes it forever or empties Trash.

## Encrypted read-only snapshots

Read-only shareable links are encrypted in the browser before upload. The decryption key is stored in the link fragment, which is not sent to the snapshot storage endpoint. The snapshot is separate from the account drawing and cannot be used to edit the original.

Anyone who receives the complete link can view that snapshot. It should still be shared intentionally.

## Explicit agent approval

External agents connect through OAuth with PKCE and scoped access. The consent screen identifies the client and its requested permissions. Access and refresh tokens are stored as hashes by the service, connected clients are visible in Settings, and users can disconnect them.

MCP drawing reads are limited to drawings owned by the connected user and return a title, element count, canvas text, and direct link—not the full raw scene.

## Honest boundaries

The initial website should not claim formal compliance certifications, end-to-end encryption for every saved account drawing, data residency, SSO, audit logs, contractual uptime, or administrative controls that have not been implemented and verified. The encrypted claim applies specifically to shareable snapshots and the live-collaboration mechanism described by the application.

## Closing CTA

### Draw with control over how the work moves.

**CTA:** Start drawing
