import React from "react";
import { reseed } from "@excalidraw/common";
import { getConnectors } from "@excalidraw/element";
import { arrayToMap } from "@excalidraw/common";

import type { ExcalidrawArrowElement } from "@excalidraw/element/types";

import { Excalidraw } from "../index";

import { API } from "./helpers/api";
import { Pointer } from "./helpers/ui";
import { render, unmountComponent } from "./test-utils";

unmountComponent();

const { h } = window;
const mouse = new Pointer("mouse");

const eastConnector = (element: ReturnType<typeof API.createElement>) =>
  getConnectors(
    API.getElement(element) as any,
    h.scene.getNonDeletedElementsMap(),
    h.state.zoom,
  ).find((connector) => connector.side === "e")!;

describe("connector handles", () => {
  beforeEach(async () => {
    localStorage.clear();
    reseed(7);
    await render(<Excalidraw />);
    mouse.reset();
  });

  it("draws an arrow bound to the shape when dragged out of a connector", () => {
    const rect = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 100,
      height: 100,
    });
    API.setElements([rect]);
    API.setSelectedElements([rect]);

    const { handle } = eastConnector(rect);

    mouse.downAt(handle[0], handle[1]);
    mouse.moveTo(handle[0] + 120, handle[1]);
    mouse.up();

    const arrow = h.elements.find(
      (element) => element.type === "arrow",
    ) as ExcalidrawArrowElement;

    expect(arrow).toBeDefined();
    expect(arrow.startBinding?.elementId).toBe(rect.id);
    // pinned to the middle of the right-hand side
    expect(arrow.startBinding?.fixedPoint[0]).toBeCloseTo(1, 1);
    expect(arrow.startBinding?.fixedPoint[1]).toBeCloseTo(0.5, 1);
    expect(
      API.getElement(rect).boundElements?.some(
        (bound) => bound.id === arrow.id,
      ),
    ).toBe(true);
  });

  it("binds the far end to a shape the arrow is dropped on", () => {
    const rect = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 100,
      height: 100,
    });
    const target = API.createElement({
      type: "rectangle",
      x: 260,
      y: 0,
      width: 100,
      height: 100,
    });
    API.setElements([rect, target]);
    API.setSelectedElements([rect]);

    const { handle } = eastConnector(rect);

    mouse.downAt(handle[0], handle[1]);
    mouse.moveTo(250, 50);
    mouse.up();

    const arrow = h.elements.find(
      (element) => element.type === "arrow",
    ) as ExcalidrawArrowElement;

    expect(arrow.startBinding?.elementId).toBe(rect.id);
    expect(arrow.endBinding?.elementId).toBe(target.id);
    // landed on the target's left-hand connector, not an arbitrary spot
    expect(arrow.endBinding?.fixedPoint[0]).toBeCloseTo(0, 1);
    expect(arrow.endBinding?.fixedPoint[1]).toBeCloseTo(0.5, 1);
  });

  it("leaves a plain click near a connector alone", () => {
    const rect = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 100,
      height: 100,
    });
    API.setElements([rect]);
    API.setSelectedElements([rect]);

    const { handle } = eastConnector(rect);

    mouse.downAt(handle[0], handle[1]);
    mouse.up();

    expect(h.elements.filter((element) => element.type === "arrow")).toEqual(
      [],
    );
  });

  it("does not offer connectors on more than one selected element", () => {
    const rect1 = API.createElement({
      type: "rectangle",
      x: 0,
      y: 0,
      width: 100,
      height: 100,
    });
    const rect2 = API.createElement({
      type: "rectangle",
      x: 300,
      y: 0,
      width: 100,
      height: 100,
    });
    API.setElements([rect1, rect2]);
    API.setSelectedElements([rect1, rect2]);

    const { handle } = getConnectors(
      API.getElement(rect1) as any,
      arrayToMap(h.elements),
      h.state.zoom,
    ).find((connector) => connector.side === "e")!;

    mouse.downAt(handle[0], handle[1]);
    mouse.moveTo(handle[0] + 120, handle[1]);
    mouse.up();

    expect(h.elements.filter((element) => element.type === "arrow")).toEqual(
      [],
    );
  });
});
