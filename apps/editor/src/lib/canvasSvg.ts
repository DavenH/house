import type { AnyRecord, OpeningDrag, Selection, SharedWallDrag, SpaceRect, WallLine } from "./types";
import { movedLine, movedPreviewRect, openingDeltaVector, wallLineFromRects } from "./geometry";
import { normalizeSvgKind } from "./planEditing";

export function svgPoint(canvasElement: HTMLDivElement | undefined, event: PointerEvent | MouseEvent) {
  const svgElement = canvasElement?.querySelector("svg");
  if (!svgElement) {
    return { x: event.clientX, y: event.clientY };
  }
  const point = svgElement.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const matrix = svgElement.getScreenCTM();
  if (!matrix) {
    return { x: event.clientX, y: event.clientY };
  }
  const transformed = point.matrixTransform(matrix.inverse());
  return { x: transformed.x, y: transformed.y };
}

export function markSelectedInSvg(canvasElement: HTMLDivElement | undefined, selected: Selection) {
  if (!canvasElement) {
    return;
  }
  canvasElement.querySelectorAll(".selected-object").forEach((element) => {
    element.classList.remove("selected-object");
  });
  if (!selected.kind || !selected.id) {
    return;
  }
  const selector = `[data-fp-kind][data-fp-id="${cssEscape(selected.id)}"]`;
  canvasElement.querySelectorAll(selector).forEach((element) => {
    if (element instanceof SVGTextElement || element instanceof SVGTSpanElement) {
      return;
    }
    if (element.classList.contains("wall-select-target") || element.classList.contains("wall-grip-target")) {
      return;
    }
    if (element instanceof SVGGElement || element instanceof SVGSVGElement) {
      return;
    }
    const kind = (element as HTMLElement).dataset.fpKind ?? "";
    if (normalizeSvgKind(kind) === selected.kind) {
      element.classList.add("selected-object");
    }
  });
}

export function hardenCanvasTextSelection(canvasElement: HTMLDivElement | undefined) {
  if (!canvasElement) {
    return;
  }
  const svgElement = canvasElement.querySelector("svg");
  svgElement?.setAttribute("unselectable", "on");
  svgElement?.setAttribute("draggable", "false");
  svgElement?.style.setProperty("-webkit-user-select", "none", "important");
  svgElement?.style.setProperty("-moz-user-select", "none", "important");
  svgElement?.style.setProperty("user-select", "none", "important");
  canvasElement.querySelectorAll("text,tspan").forEach((element) => {
    element.setAttribute("pointer-events", "none");
    element.setAttribute("unselectable", "on");
    element.setAttribute("draggable", "false");
    (element as SVGElement).style.setProperty("-webkit-user-select", "none", "important");
    (element as SVGElement).style.setProperty("-moz-user-select", "none", "important");
    (element as SVGElement).style.setProperty("user-select", "none", "important");
  });
}

export function lineFromSvgElement(element: SVGGraphicsElement, scale: number): WallLine | null {
  if (!(element instanceof SVGLineElement)) {
    return null;
  }
  return {
    x1: Number(element.getAttribute("data-fp-model-x1") ?? element.getAttribute("x1") ?? 0) / scale,
    y1: Number(element.getAttribute("data-fp-model-y1") ?? element.getAttribute("y1") ?? 0) / scale,
    x2: Number(element.getAttribute("data-fp-model-x2") ?? element.getAttribute("x2") ?? 0) / scale,
    y2: Number(element.getAttribute("data-fp-model-y2") ?? element.getAttribute("y2") ?? 0) / scale
  };
}

export function previewOpeningSvg(
  canvasElement: HTMLDivElement | undefined,
  data: AnyRecord,
  openingDrag: OpeningDrag,
  offsetDelta: number
) {
  if (!canvasElement) {
    return;
  }
  const scale = Number(data.scale ?? 16);
  const vector = openingDeltaVector(openingDrag.direction, offsetDelta);
  const transform = `translate(${(vector.x * scale).toFixed(3)} ${(vector.y * scale).toFixed(3)})`;
  canvasElement
    .querySelectorAll(`[data-fp-kind="opening"][data-fp-id="${cssEscape(openingDrag.id)}"]`)
    .forEach((element) => {
      if (element instanceof SVGGraphicsElement) {
        element.setAttribute("transform", transform);
      }
    });
}

export function moveFeatureSvg(
  canvasElement: HTMLDivElement | undefined,
  data: AnyRecord,
  levelId: string,
  id: string,
  at: [number, number]
) {
  const scale = Number(data.scale ?? 16);
  const feature = ((data.levels as AnyRecord)?.[levelId]?.features ?? {})[id] as AnyRecord | undefined;
  if (!feature || !canvasElement) {
    return;
  }
  const [width, height] = featureSize(data, feature);
  const x = (at[0] - width / 2) * scale;
  const y = (at[1] - height / 2) * scale;
  canvasElement
    .querySelectorAll(`[data-fp-kind="feature"][data-fp-id="${cssEscape(id)}"]`)
    .forEach((element) => {
      if (element instanceof SVGRectElement) {
        element.setAttribute("x", x.toFixed(3));
        element.setAttribute("y", y.toFixed(3));
      } else if (element instanceof SVGTextElement) {
        element.setAttribute("x", (at[0] * scale).toFixed(3));
        element.setAttribute("y", ((at[1] - height / 2 - 0.35) * scale).toFixed(3));
      }
    });
  const clearance = featureClearance(data, feature);
  if (clearance) {
    canvasElement
      .querySelectorAll(`[data-fp-kind="feature-clearance"][data-fp-id="${cssEscape(id)}"]`)
      .forEach((element) => {
        if (element instanceof SVGRectElement) {
          element.setAttribute("x", (x - clearance * scale).toFixed(3));
          element.setAttribute("y", (y - clearance * scale).toFixed(3));
          element.setAttribute("width", ((width + clearance * 2) * scale).toFixed(3));
          element.setAttribute("height", ((height + clearance * 2) * scale).toFixed(3));
        }
      });
  }
}

export function previewSharedWallSvg(
  canvasElement: HTMLDivElement | undefined,
  wallDrag: SharedWallDrag,
  delta: number,
  scale: number
) {
  if (!canvasElement) {
    return;
  }
  const [firstId, secondId] = wallDrag.spaces;
  const [firstRect, secondRect] = wallDrag.startRects;
  const firstNext = movedPreviewRect(firstRect, secondRect, wallDrag.orientation, delta, true);
  const secondNext = movedPreviewRect(secondRect, firstRect, wallDrag.orientation, delta, false);
  updateSpaceSvg(canvasElement, firstId, firstNext, scale);
  updateSpaceSvg(canvasElement, secondId, secondNext, scale);
  updateWallLineSvg(canvasElement, wallDrag, firstNext, secondNext, scale);
  updateWallPreviewSvg(canvasElement, wallDrag.id, wallLineFromRects(wallDrag.orientation, firstNext, secondNext), scale);
}

export function previewExteriorWallSvg(
  canvasElement: HTMLDivElement | undefined,
  wallId: string,
  line: WallLine,
  orientation: "vertical" | "horizontal",
  delta: number,
  scale: number
) {
  if (!canvasElement) {
    return;
  }
  updateWallPreviewSvg(canvasElement, wallId, movedLine(line, orientation, delta), scale);
}

export function removeWallDragPreview(canvasElement: HTMLDivElement | undefined) {
  canvasElement?.querySelectorAll(".wall-drag-preview").forEach((element) => element.remove());
}

export function cssEscape(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function updateSpaceSvg(canvasElement: HTMLDivElement, id: string, rect: SpaceRect, scale: number) {
  canvasElement
    .querySelectorAll(`[data-fp-kind="space"][data-fp-id="${cssEscape(id)}"]`)
    .forEach((element) => {
      if (element instanceof SVGRectElement) {
        element.setAttribute("x", (rect.left * scale).toFixed(3));
        element.setAttribute("y", (rect.top * scale).toFixed(3));
        element.setAttribute("width", Math.max(0.01, rect.width * scale).toFixed(3));
        element.setAttribute("height", Math.max(0.01, rect.height * scale).toFixed(3));
      }
    });
}

function updateWallLineSvg(
  canvasElement: HTMLDivElement,
  wallDrag: SharedWallDrag,
  firstRect: SpaceRect,
  secondRect: SpaceRect,
  scale: number
) {
  const wallElements = canvasElement.querySelectorAll(
    `[data-fp-kind="wall"][data-fp-id="${cssEscape(wallDrag.id)}"]`
  );
  const x =
    Math.abs(firstRect.right - secondRect.left) < 0.01
      ? firstRect.right
      : Math.abs(secondRect.right - firstRect.left) < 0.01
        ? firstRect.left
        : null;
  const y =
    Math.abs(firstRect.bottom - secondRect.top) < 0.01
      ? firstRect.bottom
      : Math.abs(secondRect.bottom - firstRect.top) < 0.01
        ? firstRect.top
        : null;
  const overlapLeft = Math.max(firstRect.left, secondRect.left);
  const overlapRight = Math.min(firstRect.right, secondRect.right);
  const overlapTop = Math.max(firstRect.top, secondRect.top);
  const overlapBottom = Math.min(firstRect.bottom, secondRect.bottom);
  wallElements.forEach((element) => {
    if (!(element instanceof SVGLineElement)) {
      return;
    }
    if (wallDrag.orientation === "vertical" && x !== null) {
      element.setAttribute("x1", (x * scale).toFixed(3));
      element.setAttribute("x2", (x * scale).toFixed(3));
      element.setAttribute("y1", (overlapTop * scale).toFixed(3));
      element.setAttribute("y2", (overlapBottom * scale).toFixed(3));
    } else if (wallDrag.orientation === "horizontal" && y !== null) {
      element.setAttribute("y1", (y * scale).toFixed(3));
      element.setAttribute("y2", (y * scale).toFixed(3));
      element.setAttribute("x1", (overlapLeft * scale).toFixed(3));
      element.setAttribute("x2", (overlapRight * scale).toFixed(3));
    }
  });
}

function updateWallPreviewSvg(canvasElement: HTMLDivElement, wallId: string, line: WallLine, scale: number) {
  const preview = ensureWallPreviewLine(canvasElement, wallId);
  if (!preview) {
    return;
  }
  preview.setAttribute("x1", (line.x1 * scale).toFixed(3));
  preview.setAttribute("y1", (line.y1 * scale).toFixed(3));
  preview.setAttribute("x2", (line.x2 * scale).toFixed(3));
  preview.setAttribute("y2", (line.y2 * scale).toFixed(3));
}

function ensureWallPreviewLine(canvasElement: HTMLDivElement, wallId: string): SVGLineElement | null {
  const existing = canvasElement.querySelector(`.wall-drag-preview[data-preview-for="${cssEscape(wallId)}"]`);
  if (existing instanceof SVGLineElement) {
    return existing;
  }
  const anchor = canvasElement.querySelector(`.wall-grip-target[data-fp-id="${cssEscape(wallId)}"]`);
  const parent = anchor?.parentElement;
  if (!parent) {
    return null;
  }
  const preview = document.createElementNS("http://www.w3.org/2000/svg", "line");
  preview.classList.add("wall-drag-preview");
  preview.setAttribute("data-preview-for", wallId);
  parent.appendChild(preview);
  return preview;
}

function featureSize(data: AnyRecord, feature: AnyRecord): [number, number] {
  if (Array.isArray(feature.size)) {
    return [Number(feature.size[0] ?? 4), Number(feature.size[1] ?? 4)];
  }
  const catalogFeature = ((data.catalog ?? {}) as AnyRecord)[feature.kind ?? ""];
  if (Array.isArray(catalogFeature?.size)) {
    return [Number(catalogFeature.size[0] ?? 4), Number(catalogFeature.size[1] ?? 4)];
  }
  return [4, 4];
}

function featureClearance(data: AnyRecord, feature: AnyRecord): number {
  const catalogFeature = ((data.catalog ?? {}) as AnyRecord)[feature.kind ?? ""];
  return Number(
    feature.clearance?.around ??
      feature.clearance?.walls ??
      catalogFeature?.clearance?.around ??
      catalogFeature?.clearance?.walls ??
      0
  );
}
