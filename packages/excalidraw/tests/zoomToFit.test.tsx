import React from "react";

import { Excalidraw } from "../index";

import { API } from "./helpers/api";
import { fireEvent, render, unmountComponent } from "./test-utils";

unmountComponent();

const { h } = window;

const onScreen = ([x1, y1, x2, y2]: [number, number, number, number]) => {
  const { scrollX, scrollY, zoom } = h.state;
  return {
    left: (x1 + scrollX) * zoom.value,
    top: (y1 + scrollY) * zoom.value,
    right: (x2 + scrollX) * zoom.value,
    bottom: (y2 + scrollY) * zoom.value,
  };
};

describe("zoom to fit button", () => {
  beforeEach(async () => {
    localStorage.clear();
    await render(<Excalidraw />);
  });

  const button = () =>
    document.querySelector<HTMLButtonElement>(".zoom-to-fit-button");

  it("sits with the other zoom controls", () => {
    expect(document.querySelector(".zoom-actions")).toContainElement(button()!);
  });

  it("is offered only when there is something to fit", () => {
    expect(button()!.disabled).toBe(true);

    API.setElements([
      API.createElement({
        type: "rectangle",
        x: 0,
        y: 0,
        width: 50,
        height: 50,
      }),
    ]);
    expect(button()!.disabled).toBe(false);
  });

  it("brings an element that scrolled far off-screen back into view", () => {
    API.setElements([
      API.createElement({
        type: "rectangle",
        x: 9000,
        y: 9000,
        width: 200,
        height: 200,
      }),
    ]);
    API.setAppState({
      width: 1200,
      height: 800,
      scrollX: 0,
      scrollY: 0,
      zoom: { value: 4 as any },
    });

    fireEvent.click(button()!);

    const screen = onScreen([9000, 9000, 9200, 9200]);
    expect(screen.left).toBeGreaterThanOrEqual(0);
    expect(screen.top).toBeGreaterThanOrEqual(0);
    expect(screen.right).toBeLessThanOrEqual(h.state.width);
    expect(screen.bottom).toBeLessThanOrEqual(h.state.height);
  });

  it("centres the drawing on both axes", () => {
    API.setElements([
      API.createElement({
        type: "rectangle",
        x: -400,
        y: 2000,
        width: 900,
        height: 300,
      }),
    ]);
    API.setAppState({ width: 1200, height: 800, scrollX: 0, scrollY: 0 });

    fireEvent.click(button()!);

    const screen = onScreen([-400, 2000, 500, 2300]);
    // equal air on the left and right, and on the top and bottom
    expect(screen.left).toBeCloseTo(h.state.width - screen.right, 0);
    expect(screen.top).toBeCloseTo(h.state.height - screen.bottom, 0);
  });

  it("fills the screen with a small drawing instead of leaving it at 100%", () => {
    API.setElements([
      API.createElement({
        type: "rectangle",
        x: 0,
        y: 0,
        width: 200,
        height: 100,
      }),
    ]);
    API.setAppState({ width: 1200, height: 800, scrollX: 0, scrollY: 0 });

    fireEvent.click(button()!);

    // it grew rather than sitting at 1:1 in the middle of a large screen
    expect(h.state.zoom.value).toBeGreaterThan(1);
  });

  it("uses the width it has, rather than rounding the zoom down to a step", () => {
    API.setElements([
      API.createElement({
        type: "rectangle",
        x: 0,
        y: 0,
        width: 4000,
        height: 3000,
      }),
    ]);
    API.setAppState({ width: 1200, height: 800, scrollX: 0, scrollY: 0 });

    fireEvent.click(button()!);

    const screen = onScreen([0, 0, 4000, 3000]);
    // snapping 0.26 down to 0.2 used to waste a third of the viewport
    expect(screen.bottom - screen.top).toBeGreaterThan(h.state.height * 0.85);
  });
});
