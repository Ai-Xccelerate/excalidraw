import { CaptureUpdateAction } from "@excalidraw/excalidraw";
import { newElementWith } from "@excalidraw/element";
import { getCommonBounds } from "@excalidraw/element";
import { restoreElements } from "@excalidraw/excalidraw/data/restore";

import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import type {
  ExcalidrawElement,
  OrderedExcalidrawElement,
} from "@excalidraw/element/types";

import type { AgentOperations } from "../data/backend";

const GAP = 80;

/** Where new elements should land.
 *
 * Replacing something puts them where it was, so a redrawn diagram doesn't
 * jump across the canvas. Otherwise they go beside what is already there —
 * never on top of it, which is what makes an agent feel careless. */
const placementFor = (
  scene: readonly ExcalidrawElement[],
  removedIds: Set<string>,
  incoming: ExcalidrawElement[],
): { dx: number; dy: number } => {
  if (!incoming.length) {
    return { dx: 0, dy: 0 };
  }
  const [nx1, ny1] = getCommonBounds(incoming);

  const removed = scene.filter((element) => removedIds.has(element.id));
  if (removed.length) {
    const [rx1, ry1] = getCommonBounds(removed);
    return { dx: rx1 - nx1, dy: ry1 - ny1 };
  }

  const remaining = scene.filter(
    (element) => !element.isDeleted && !removedIds.has(element.id),
  );
  if (!remaining.length) {
    return { dx: -nx1, dy: -ny1 };
  }
  const [, y1, x2] = getCommonBounds(remaining);
  return { dx: x2 + GAP - nx1, dy: y1 - ny1 };
};

/**
 * Applies what the agent decided to the live scene, in one update so it is a
 * single step in the undo history — the user can take the whole thing back
 * with one ⌘Z rather than unpicking it element by element.
 *
 * @returns the ids of everything it added, so the caller can select them.
 */
export const applyAgentOperations = (
  api: ExcalidrawImperativeAPI,
  operations: AgentOperations,
): string[] => {
  const scene = api.getSceneElements();
  const removedIds = new Set(operations.delete_ids ?? []);

  // straight from the server, so run them through restore: it fills in
  // anything the builder left out and normalises the bindings
  const incoming = restoreElements(
    (operations.elements ?? []) as ExcalidrawElement[],
    null,
  );
  const { dx, dy } = placementFor(scene, removedIds, incoming as any);

  const placed = incoming.map((element) =>
    newElementWith(element, { x: element.x + dx, y: element.y + dy }),
  );

  const updates = new Map(
    (operations.updates ?? []).map((update) => [update.id, update]),
  );
  // a shape's label is a bound text element, so renaming means editing that
  const labelTargets = new Map<string, string>();
  for (const update of operations.updates ?? []) {
    if (update.label != null) {
      labelTargets.set(update.id, update.label);
    }
  }

  const next = scene
    .filter((element) => !removedIds.has(element.id))
    .map((element) => {
      const update = updates.get(element.id);
      const boundLabel =
        (element as any).containerId != null
          ? labelTargets.get((element as any).containerId)
          : undefined;

      if (!update && boundLabel == null) {
        return element;
      }

      const changes: Record<string, unknown> = {};
      if (update?.backgroundColor) {
        changes.backgroundColor = update.backgroundColor;
      }
      if (update?.strokeColor && element.type !== "text") {
        changes.strokeColor = update.strokeColor;
      }
      if (update?.textColor && element.type === "text") {
        changes.strokeColor = update.textColor;
      }
      if (element.type === "text") {
        // renaming a shape edits the text bound to it; renaming a loose text
        // element edits it directly
        const text = boundLabel ?? (update ? update.label : undefined);
        if (text != null) {
          changes.text = text;
          changes.originalText = text;
        }
      }

      return Object.keys(changes).length
        ? newElementWith(element, changes as any)
        : element;
    });

  api.updateScene({
    elements: [...next, ...placed] as OrderedExcalidrawElement[],
    captureUpdate: CaptureUpdateAction.IMMEDIATELY,
  });

  return placed.map((element) => element.id);
};
