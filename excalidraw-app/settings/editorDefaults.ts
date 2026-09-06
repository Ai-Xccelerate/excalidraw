import { FONT_FAMILY } from "@excalidraw/common";

import type { StrokeWidthKey } from "@excalidraw/common";
import type { FontFamilyValues } from "@excalidraw/element/types";
import type { AppState } from "@excalidraw/excalidraw/types";

import type { EditorDefaults } from "../data/backend";

/** The slice of appState the preferences own. Spelled out so `updateScene` can
 * infer which keys are being written instead of demanding the whole state. */
type EditorAppState = Pick<
  AppState,
  | "currentItemFontFamily"
  | "currentItemFontSize"
  | "currentItemStrokeColor"
  | "currentItemBackgroundColor"
  | "currentItemFillStyle"
  | "currentItemStrokeWidthKey"
  | "currentItemStrokeStyle"
  | "currentItemRoughness"
  | "currentItemRoundness"
  | "currentItemArrowType"
>;

const FONT_FAMILIES: Record<EditorDefaults["font_family"], FontFamilyValues> = {
  "hand-drawn": FONT_FAMILY.Excalifont,
  normal: FONT_FAMILY.Nunito,
  code: FONT_FAMILY.Cascadia,
};

// the editor stores the stroke width as a named step, not the raw number the
// preferences (and the diagram builder) work in
const STROKE_WIDTH_KEYS: Record<number, StrokeWidthKey> = {
  1: "thin",
  2: "medium",
  4: "bold",
};

/** Maps the saved preferences onto the appState fields the editor reads when
 * it creates the next element. Server-side names are snake_case because the
 * same payload drives the MCP diagram builder. */
export const editorDefaultsToAppState = (
  defaults: EditorDefaults,
): EditorAppState => ({
  currentItemFontFamily:
    FONT_FAMILIES[defaults.font_family] ?? FONT_FAMILY.Excalifont,
  currentItemFontSize: defaults.font_size,
  currentItemStrokeColor: defaults.stroke_color,
  currentItemBackgroundColor: defaults.background_color,
  currentItemFillStyle: defaults.fill_style,
  currentItemStrokeWidthKey:
    STROKE_WIDTH_KEYS[defaults.stroke_width] ?? "medium",
  currentItemStrokeStyle: defaults.stroke_style,
  currentItemRoughness: defaults.roughness,
  currentItemRoundness: defaults.edges,
  currentItemArrowType: defaults.arrow_type,
});
