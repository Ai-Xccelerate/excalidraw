import { restoreElements } from "@excalidraw/excalidraw/data/restore";
import { isArrowElement, isTextElement } from "@excalidraw/element";
import { arrayToMap } from "@excalidraw/common";

import type {
  ExcalidrawArrowElement,
  ExcalidrawElement,
} from "@excalidraw/element/types";

import flowchart from "./fixtures/mcp-flowchart.json";

/** The MCP tools build scenes on the server (server/diagrams.py), so the two
 * sides have to agree on the element schema. This restores a scene captured
 * from that builder the way opening the drawing would. */
describe("diagrams drawn over MCP", () => {
  const restored = restoreElements(
    flowchart as unknown as ExcalidrawElement[],
    null,
  );
  const elementsMap = arrayToMap(restored);

  it("survives restore without dropping anything", () => {
    expect(restored.length).toBe(flowchart.length);
    expect(restored.some((element) => element.isDeleted)).toBe(false);
  });

  it("keeps every label bound to its shape", () => {
    const labels = restored.filter(
      (element) => isTextElement(element) && element.containerId,
    );
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) {
      const container = elementsMap.get((label as any).containerId);
      expect(container).toBeDefined();
      expect(
        container!.boundElements?.some((bound) => bound.id === label.id),
      ).toBe(true);
    }
  });

  it("keeps the arrows bound to the boxes they connect", () => {
    const arrows = restored.filter((element) => isArrowElement(element));
    expect(arrows.length).toBe(3);
    for (const element of arrows) {
      const arrow = element as ExcalidrawArrowElement;
      expect(elementsMap.get(arrow.startBinding!.elementId)).toBeDefined();
      expect(elementsMap.get(arrow.endBinding!.elementId)).toBeDefined();
      // the binding schema the editor writes today: a ratio on the shape
      expect(arrow.startBinding!.fixedPoint).toHaveLength(2);
      expect(arrow.startBinding!.mode).toBe("orbit");
    }
  });

  it("carries the requested font through to the labels", () => {
    const label = restored.find(
      (element) => isTextElement(element) && element.text === "Start",
    );
    // "normal" in the preferences is Nunito (6) in the editor
    expect((label as any).fontFamily).toBe(6);
  });
});
