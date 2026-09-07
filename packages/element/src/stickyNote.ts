import {
  DEFAULT_STICKY_NOTE_COLOR,
  STICKY_NOTE_PICKS,
} from "@excalidraw/common";

import type { ExcalidrawElement } from "./types";

/** What a click (rather than a drag) drops on the canvas. Square, roughly the
 * proportions of the paper kind, and big enough to write a line or two in. */
export const STICKY_NOTE_DEFAULT_SIZE = 180;

/** A sticky note is a rectangle with `customData.stickyNote`, so it keeps
 * every rectangle behaviour (text binding, arrows, export) while the UI can
 * still tell it apart and offer paper colours instead of element backgrounds. */
export const isStickyNoteElement = (
  element: ExcalidrawElement | null | undefined,
): boolean => element?.type === "rectangle" && !!element.customData?.stickyNote;

/** Keeps a note on paper colours: a carried-over element background (or
 * transparent, which would make the note invisible) falls back to yellow. */
export const stickyNoteColor = (color: string | null | undefined): string =>
  color && (STICKY_NOTE_PICKS as readonly string[]).includes(color)
    ? color
    : DEFAULT_STICKY_NOTE_COLOR;
