import React from "react";

import { Excalidraw } from "@excalidraw/excalidraw";
import { API } from "@excalidraw/excalidraw/tests/helpers/api";
import { createUndoAction } from "@excalidraw/excalidraw/actions/actionHistory";
import { Pointer, UI } from "@excalidraw/excalidraw/tests/helpers/ui";
import {
  act,
  render,
  unmountComponent,
} from "@excalidraw/excalidraw/tests/test-utils";

import { applyAgentOperations } from "../agent/applyOperations";

import type { AgentOperations } from "../data/backend";

unmountComponent();

const { h } = window;
const mouse = new Pointer("mouse");

const apply = (operations: AgentOperations) =>
  act(() => {
    applyAgentOperations(h.app as any, operations);
  });

const noop: AgentOperations["summary"] = {
  created: 0,
  connected: 0,
  updated: 0,
  deleted: 0,
};

const drawn = (x = 0, y = 0) => [
  {
    id: "new-box",
    type: "rectangle",
    x,
    y,
    width: 120,
    height: 60,
    angle: 0,
    strokeColor: "#1e1e1e",
    backgroundColor: "#d3f9d8",
    fillStyle: "solid",
    strokeWidth: 2,
    strokeStyle: "solid",
    roughness: 1,
    opacity: 100,
    groupIds: [],
    frameId: null,
    roundness: null,
    seed: 1,
    version: 1,
    versionNonce: 1,
    isDeleted: false,
    boundElements: [],
    updated: 1,
    link: null,
    locked: false,
  },
];

describe("applying what the agent decided", () => {
  beforeEach(async () => {
    localStorage.clear();
    await render(<Excalidraw />);
  });

  it("adds new elements beside what is already there, never on top of it", () => {
    const existing = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 200,
      height: 100,
    });
    API.setElements([existing]);

    apply({
      elements: drawn(),
      updates: [],
      delete_ids: [],
      summary: { ...noop, created: 1 },
    });

    const added = h.elements.find((element) => element.id !== existing.id)!;
    expect(added.x).toBeGreaterThanOrEqual(existing.x + existing.width);
  });

  it("puts a replacement where the thing it replaced was", () => {
    const old = API.createElement({
      type: "rectangle",
      x: 640,
      y: 480,
      width: 200,
      height: 100,
    });
    API.setElements([old]);

    apply({
      elements: drawn(),
      updates: [],
      delete_ids: [old.id],
      summary: { ...noop, created: 1, deleted: 1 },
    });

    const live = h.elements.filter((element) => !element.isDeleted);
    expect(live).toHaveLength(1);
    expect(live[0].x).toBe(640);
    expect(live[0].y).toBe(480);
  });

  it("renames a shape by editing the text bound to it", () => {
    const box = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 200,
      height: 100,
    });
    const label = API.createElement({
      type: "text",
      x: 10,
      y: 10,
      text: "Old name",
      containerId: box.id,
    });
    API.updateElement(box, { boundElements: [{ id: label.id, type: "text" }] });
    API.setElements([box, label]);

    apply({
      elements: [],
      updates: [{ id: box.id, label: "New name", backgroundColor: "#ffc9c9" }],
      delete_ids: [],
      summary: { ...noop, updated: 1 },
    });

    const updatedBox = h.elements.find((element) => element.id === box.id)!;
    const updatedLabel = h.elements.find((element) => element.id === label.id)!;
    expect(updatedBox.backgroundColor).toBe("#ffc9c9");
    expect((updatedLabel as any).text).toBe("New name");
  });

  it("lands as one undo step, so the whole change can be taken back at once", () => {
    // drawn through the UI so the history has a real state to come back to
    UI.clickTool("rectangle");
    mouse.downAt(0, 0);
    mouse.moveTo(100, 100);
    mouse.up();
    const existing = h.elements[0];

    const stepsBefore = h.history.undoStack.length;

    // a draw and a delete, in one instruction
    apply({
      elements: drawn(400, 0),
      updates: [],
      delete_ids: [existing.id],
      summary: { ...noop, created: 1, deleted: 1 },
    });

    expect(h.elements.filter((element) => !element.isDeleted)).toHaveLength(1);
    // one instruction, one thing to undo — not one per element it touched
    expect(h.history.undoStack.length).toBe(stepsBefore + 1);
  });
});
