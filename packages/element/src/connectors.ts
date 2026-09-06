import { pointDistance, pointFrom, pointRotateRads } from "@excalidraw/math";

import type { GlobalPoint } from "@excalidraw/math";
import type { Zoom } from "@excalidraw/excalidraw/types";

import { getGlobalFixedPointForBindableElement } from "./binding";
import { elementCenterPoint } from "./bounds";
import { isBindableElement, isFrameLikeElement } from "./typeChecks";

import type {
  ElementsMap,
  ExcalidrawBindableElement,
  ExcalidrawElement,
  FixedPoint,
} from "./types";

export type ConnectorSide = "n" | "e" | "s" | "w";

export type Connector = {
  side: ConnectorSide;
  /** where the arrow binds — on the element's outline */
  point: GlobalPoint;
  /** where the dot is drawn — pushed out so it clears the selection border */
  handle: GlobalPoint;
  /** ratio-based binding coordinate, as stored on the arrow's binding */
  fixedPoint: FixedPoint;
};

const CONNECTOR_FIXED_POINTS: Record<ConnectorSide, FixedPoint> = {
  n: [0.5, 0],
  e: [1, 0.5],
  s: [0.5, 1],
  w: [0, 0.5],
};

/** how far outside the outline the dot is drawn, in px at 100% zoom */
const CONNECTOR_HANDLE_OFFSET = 18;
/** radius of the dot, in px at 100% zoom */
export const CONNECTOR_HANDLE_RADIUS = 4;
/** how close the pointer has to be to grab a dot, in px at 100% zoom */
const CONNECTOR_HANDLE_HIT_RADIUS = 7;
/** how far the pointer has to travel before a press on a dot draws an arrow */
export const CONNECTOR_DRAG_THRESHOLD = 4;

export const canHaveConnectors = (
  element: ExcalidrawElement,
): element is ExcalidrawBindableElement =>
  isBindableElement(element, false) && !isFrameLikeElement(element);

export const getConnectors = (
  element: ExcalidrawBindableElement,
  elementsMap: ElementsMap,
  zoom: Zoom,
): Connector[] => {
  const center = elementCenterPoint(element, elementsMap);
  const offset = CONNECTOR_HANDLE_OFFSET / zoom.value;

  return (Object.keys(CONNECTOR_FIXED_POINTS) as ConnectorSide[]).map(
    (side) => {
      const fixedPoint = CONNECTOR_FIXED_POINTS[side];
      const point = getGlobalFixedPointForBindableElement(
        fixedPoint,
        element,
        elementsMap,
      );
      // offset along the unrotated axis, then rotate with the element so the
      // dots stay on the same sides of a rotated shape
      const unrotated = pointFrom<GlobalPoint>(
        element.x + element.width * fixedPoint[0],
        element.y + element.height * fixedPoint[1],
      );
      const handle = pointRotateRads(
        pointFrom<GlobalPoint>(
          unrotated[0] + (side === "e" ? offset : side === "w" ? -offset : 0),
          unrotated[1] + (side === "s" ? offset : side === "n" ? -offset : 0),
        ),
        center,
        element.angle,
      );

      return { side, point, handle, fixedPoint };
    },
  );
};

export const getConnectorAtPoint = (
  scenePoint: GlobalPoint,
  element: ExcalidrawBindableElement,
  elementsMap: ElementsMap,
  zoom: Zoom,
): Connector | null => {
  const threshold = CONNECTOR_HANDLE_HIT_RADIUS / zoom.value;

  return (
    getConnectors(element, elementsMap, zoom).find(
      (connector) => pointDistance(scenePoint, connector.handle) <= threshold,
    ) ?? null
  );
};
