import React from "react";
import {
  STICKY_NOTE_PICKS,
  COLOR_PALETTE,
  ROUNDNESS,
} from "@excalidraw/common";
import {
  isStickyNoteElement,
  STICKY_NOTE_DEFAULT_SIZE,
} from "@excalidraw/element";

import { Excalidraw } from "../index";

import { API } from "./helpers/api";
import { Pointer, UI } from "./helpers/ui";
import { render, unmountComponent } from "./test-utils";

unmountComponent();

const { h } = window;
const mouse = new Pointer("mouse");

describe("sticky note tool", () => {
  beforeEach(async () => {
    localStorage.clear();
    await render(<Excalidraw />);
    mouse.reset();
  });

  const drawNote = () => {
    UI.clickTool("stickynote" as any);
    mouse.downAt(100, 100);
    mouse.moveTo(260, 250);
    mouse.up();
    return h.elements[h.elements.length - 1];
  };

  it("draws paper: filled, no border, soft corners", () => {
    const note = drawNote();

    expect(note.type).toBe("rectangle");
    expect(isStickyNoteElement(note)).toBe(true);
    // the whole point: no outline around the note
    expect(note.strokeColor).toBe(COLOR_PALETTE.transparent);
    expect(note.backgroundColor).toBe(STICKY_NOTE_PICKS[0]);
    expect(note.fillStyle).toBe("solid");
    expect(note.roundness?.type).toBe(ROUNDNESS.ADAPTIVE_RADIUS);
  });

  it("keeps a note on paper colours rather than the last element background", () => {
    API.setAppState({ currentItemBackgroundColor: "transparent" });
    // transparent would make the note invisible, so it falls back to yellow
    expect(drawNote().backgroundColor).toBe(STICKY_NOTE_PICKS[0]);

    API.setAppState({ currentItemBackgroundColor: STICKY_NOTE_PICKS[3] });
    expect(drawNote().backgroundColor).toBe(STICKY_NOTE_PICKS[3]);
  });

  it("is still a rectangle, so text binds to it", () => {
    const note = drawNote();
    mouse.doubleClickAt(180, 175);

    const text = h.elements.find((element) => element.type === "text");
    expect(text).toBeDefined();
    expect((text as any).containerId).toBe(note.id);
  });

  it("stamps a default-size note on a click, ready to resize", () => {
    UI.clickTool("stickynote" as any);
    mouse.clickAt(300, 300);

    const note = h.elements[h.elements.length - 1];
    expect(isStickyNoteElement(note)).toBe(true);
    expect(note.width).toBe(STICKY_NOTE_DEFAULT_SIZE);
    expect(note.height).toBe(STICKY_NOTE_DEFAULT_SIZE);
    // centred on where it was placed
    expect(note.x + note.width / 2).toBeCloseTo(300, 0);
    expect(note.y + note.height / 2).toBeCloseTo(300, 0);
    // and it is the selected element, so the resize handles are right there
    expect(API.getSelectedElement().id).toBe(note.id);
  });

  it("still throws away a stray click with an ordinary shape tool", () => {
    UI.clickTool("rectangle");
    mouse.clickAt(600, 600);

    expect(h.elements.filter((element) => !element.isDeleted)).toEqual([]);
  });

  it("does not leak its styling into the next rectangle", () => {
    drawNote();

    UI.clickTool("rectangle");
    mouse.downAt(400, 100);
    mouse.moveTo(500, 200);
    mouse.up();

    const rectangle = h.elements[h.elements.length - 1];
    expect(isStickyNoteElement(rectangle)).toBe(false);
    expect(rectangle.strokeColor).not.toBe(COLOR_PALETTE.transparent);
  });
});
