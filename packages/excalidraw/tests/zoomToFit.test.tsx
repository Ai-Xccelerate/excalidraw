import React from "react";

import { Excalidraw } from "../index";

import { API } from "./helpers/api";
import { fireEvent, render, unmountComponent } from "./test-utils";

unmountComponent();

const { h } = window;

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
    API.setAppState({ scrollX: 0, scrollY: 0, zoom: { value: 4 as any } });

    fireEvent.click(button()!);

    // the scene has no measured size under jsdom, so "on screen" is checked
    // the way the action defines it: the content's centre on the viewport's
    const { scrollX, scrollY, zoom, width, height } = h.state;
    const centreX = (9000 + 200 / 2 + scrollX) * zoom.value;
    const centreY = (9000 + 200 / 2 + scrollY) * zoom.value;
    expect(centreX).toBeCloseTo(width / 2, 0);
    expect(centreY).toBeCloseTo(height / 2, 0);
    // and zoomed out far enough to actually hold it
    expect(zoom.value).toBeLessThan(4);
  });
});
