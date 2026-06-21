import type { AnyRecord, ContainedWallDrag, OpeningDrag, Selection, SharedWallDrag, SpaceRect, WallLine } from "./types";
import { movedLine, movedPreviewRect, openingDeltaVector, wallLineFromRects } from "./geometry";
import { normalizeSvgKind } from "./planEditing";

const EXPORT_REMOVED_SELECTORS = [
  ".layer-hidden",
  ".wall-grip-dot",
  ".wall-grip-target",
  ".wall-select-target",
  ".opening-hit-target",
  ".space-select-target",
  ".stair-select-target",
  ".wall-drag-preview"
];

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

export function serializeCanvasSvgForExport(canvasElement: HTMLDivElement | undefined, fallbackSvg: string) {
  const clone = cleanSvgClone(canvasElement?.querySelector("svg"));
  if (!clone) {
    return fallbackSvg;
  }
  return new XMLSerializer().serializeToString(clone) + "\n";
}

export function serializePrintableFloorPages(canvasElement: HTMLDivElement | undefined, fallbackSvg: string, title: string) {
  const sourceSvg = canvasElement?.querySelector("svg");
  if (!sourceSvg) {
    return printableHtml(title, [`<div class="page"><div class="sheet">${fallbackSvg}</div></div>`]);
  }
  const shared = sharedSvgNodes(sourceSvg);
  const compass = sourceSvg.querySelector(":scope > g.compass");
  const pages = Array.from(sourceSvg.querySelectorAll(':scope > g[data-fp-kind="level"]'))
    .filter((level): level is SVGGElement => level instanceof SVGGElement)
    .map((level) => serializePrintableLevelSvg(level, shared, compass instanceof SVGGElement ? compass : null));
  if (!pages.length) {
    const full = cleanSvgClone(sourceSvg);
    return printableHtml(title, [`<div class="page"><div class="sheet">${full ? new XMLSerializer().serializeToString(full) : fallbackSvg}</div></div>`]);
  }
  return printableHtml(
    title,
    pages.map((page) => `<section class="page"><div class="sheet">${page}</div></section>`)
  );
}

function cleanSvgClone(sourceSvg: SVGSVGElement | null | undefined) {
  if (!sourceSvg) {
    return null;
  }
  const clone = sourceSvg.cloneNode(true) as SVGSVGElement;
  clone.classList.remove("selected-object");
  clone.removeAttribute("style");
  clone.removeAttribute("unselectable");
  clone.removeAttribute("draggable");
  clone.querySelectorAll(EXPORT_REMOVED_SELECTORS.join(",")).forEach((element) => element.remove());
  clone.querySelectorAll(".selected-object").forEach((element) => {
    element.classList.remove("selected-object");
  });
  clone.querySelectorAll("[unselectable],[draggable]").forEach((element) => {
    element.removeAttribute("unselectable");
    element.removeAttribute("draggable");
  });
  return clone;
}

function serializePrintableLevelSvg(level: SVGGElement, shared: string, compass: SVGGElement | null) {
  const bbox = transformedBBox(level);
  const padding = 64;
  const width = Math.ceil(bbox.width + padding * 2);
  const height = Math.ceil(bbox.height + padding * 2);
  const clone = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("viewBox", `${bbox.x - padding} ${bbox.y - padding} ${width} ${height}`);
  clone.setAttribute("preserveAspectRatio", "xMidYMid meet");
  clone.innerHTML = `<rect x="${bbox.x - padding}" y="${bbox.y - padding}" width="${width}" height="${height}" fill="#fff" />${shared}`;
  const levelClone = level.cloneNode(true) as SVGGElement;
  levelClone.querySelectorAll(EXPORT_REMOVED_SELECTORS.join(",")).forEach((element) => element.remove());
  clone.appendChild(levelClone);
  const compassClone = compass ? positionedCompassClone(compass, bbox) : null;
  if (compassClone) {
    clone.appendChild(compassClone);
  }
  return new XMLSerializer().serializeToString(clone);
}

function positionedCompassClone(compass: SVGGElement, pageBox: { x: number; y: number; width: number; height: number }) {
  const compassBox = transformedBBox(compass);
  const clone = compass.cloneNode(true) as SVGGElement;
  const scale = 0.72;
  const margin = 12;
  const targetX = pageBox.x + pageBox.width - compassBox.width * scale - margin;
  const targetY = pageBox.y - compassBox.height * scale + margin;
  clone.setAttribute(
    "transform",
    `translate(${(targetX - compassBox.x * scale).toFixed(3)} ${(targetY - compassBox.y * scale).toFixed(3)}) scale(${scale})`
  );
  return clone;
}

function transformedBBox(element: SVGGraphicsElement) {
  const bbox = element.getBBox();
  const matrix = element.transform.baseVal.consolidate()?.matrix;
  if (!matrix) {
    return bbox;
  }
  const points = [
    new DOMPoint(bbox.x, bbox.y).matrixTransform(matrix),
    new DOMPoint(bbox.x + bbox.width, bbox.y).matrixTransform(matrix),
    new DOMPoint(bbox.x + bbox.width, bbox.y + bbox.height).matrixTransform(matrix),
    new DOMPoint(bbox.x, bbox.y + bbox.height).matrixTransform(matrix)
  ];
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return {
    x,
    y,
    width: Math.max(...xs) - x,
    height: Math.max(...ys) - y
  };
}

function sharedSvgNodes(sourceSvg: SVGSVGElement) {
  return Array.from(sourceSvg.children)
    .filter((child) => child.tagName.toLowerCase() === "defs" || child.tagName.toLowerCase() === "style")
    .map((child) => new XMLSerializer().serializeToString(child))
    .join("\n");
}

function printableHtml(title: string, pages: string[]) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    @page { size: letter landscape; margin: 0; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #e8e2d8; color: #222; font-family: Arial, Helvetica, sans-serif; }
    .page { min-height: 100vh; padding: 0.25in; display: flex; align-items: center; justify-content: center; }
    .page:last-child { page-break-after: auto; break-after: auto; }
    .sheet { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: white; }
    svg { display: block; width: 100%; height: 100%; max-width: 100%; max-height: calc(100vh - 1.2in); }
    @media print {
      body { background: white; }
      .page { width: 11in; height: 8.5in; min-height: 0; margin: 0; padding: 0.35in; overflow: hidden; break-inside: avoid; page-break-inside: avoid; }
      .page + .page { break-before: page; page-break-before: always; }
      .sheet { width: 100%; height: 100%; }
      svg { width: 100%; height: 100%; max-width: 100%; max-height: 100%; }
    }
  </style>
</head>
<body>
${pages.join("\n")}
</body>
</html>
`;
}

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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
  const levelSelector = selected.level ? `[data-fp-level="${cssEscape(selected.level)}"]` : "";
  const selector = `[data-fp-kind][data-fp-id="${cssEscape(selected.id)}"]${levelSelector}`;
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
    .querySelectorAll(
      `[data-fp-kind="opening"][data-fp-id="${cssEscape(openingDrag.id)}"][data-fp-level="${cssEscape(openingDrag.level)}"]`
    )
    .forEach((element) => {
      if (element instanceof SVGGraphicsElement) {
        element.setAttribute("transform", transform);
      }
    });
}

export function previewOverlaySvg(
  canvasElement: HTMLDivElement | undefined,
  levelId: string,
  id: string,
  points: Array<[number, number]>,
  scale: number
) {
  if (!canvasElement) {
    return;
  }
  const path = canvasElement.querySelector(
    `path.overlay-line[data-fp-id="${cssEscape(id)}"][data-fp-level="${cssEscape(levelId)}"]`
  );
  if (path instanceof SVGPathElement) {
    path.setAttribute("d", overlayPath(points, scale));
  }
  canvasElement
    .querySelectorAll(`circle.overlay-node[data-fp-id="${cssEscape(id)}"][data-fp-level="${cssEscape(levelId)}"]`)
    .forEach((element) => {
      if (!(element instanceof SVGCircleElement)) {
        return;
      }
      const index = Number(element.getAttribute("data-fp-point-index") ?? NaN);
      const point = points[index];
      if (!point) {
        return;
      }
      element.setAttribute("cx", (point[0] * scale).toFixed(3));
      element.setAttribute("cy", (point[1] * scale).toFixed(3));
    });
  canvasElement
    .querySelectorAll(`line.overlay-segment-target[data-fp-id="${cssEscape(id)}"][data-fp-level="${cssEscape(levelId)}"]`)
    .forEach((element) => {
      if (!(element instanceof SVGLineElement)) {
        return;
      }
      const index = Number(element.getAttribute("data-fp-segment-index") ?? NaN);
      const first = points[index];
      const second = points[index + 1];
      if (!first || !second) {
        return;
      }
      element.setAttribute("x1", (first[0] * scale).toFixed(3));
      element.setAttribute("y1", (first[1] * scale).toFixed(3));
      element.setAttribute("x2", (second[0] * scale).toFixed(3));
      element.setAttribute("y2", (second[1] * scale).toFixed(3));
    });
}

function overlayPath(points: Array<[number, number]>, scale: number) {
  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${(x * scale).toFixed(3)} ${(y * scale).toFixed(3)}`)
    .join(" ");
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
  if (["piano", "spiral_stair"].includes(feature.kind)) {
    moveFeatureGraphicsSvg(canvasElement, id, at, scale);
  }
  canvasElement
    .querySelectorAll(`[data-fp-kind="feature"][data-fp-id="${cssEscape(id)}"]`)
    .forEach((element) => {
      if (["piano", "spiral_stair"].includes(feature.kind) && !(element instanceof SVGTextElement)) {
        return;
      }
      if (element instanceof SVGRectElement) {
        element.setAttribute("x", x.toFixed(3));
        element.setAttribute("y", y.toFixed(3));
        rotateAroundCurrentCenter(element, at, scale);
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
        if (element instanceof SVGGraphicsElement && element.hasAttribute("data-fp-model-cx")) {
          moveByModelCenter(element, at, scale);
          return;
        }
        if (element instanceof SVGRectElement) {
          element.setAttribute("x", (x - clearance * scale).toFixed(3));
          element.setAttribute("y", (y - clearance * scale).toFixed(3));
          element.setAttribute("width", ((width + clearance * 2) * scale).toFixed(3));
          element.setAttribute("height", ((height + clearance * 2) * scale).toFixed(3));
        }
      });
  }
}

function moveFeatureGraphicsSvg(canvasElement: HTMLDivElement, id: string, at: [number, number], scale: number) {
  canvasElement
    .querySelectorAll(`[data-fp-kind="feature"][data-fp-id="${cssEscape(id)}"]`)
    .forEach((element) => {
      if (element instanceof SVGGraphicsElement && !(element instanceof SVGTextElement)) {
        moveByModelCenter(element, at, scale);
      }
    });
}

function moveByModelCenter(element: SVGGraphicsElement, at: [number, number], scale: number) {
  const modelCx = Number(element.getAttribute("data-fp-model-cx") ?? at[0] * scale);
  const modelCy = Number(element.getAttribute("data-fp-model-cy") ?? at[1] * scale);
  const dx = at[0] * scale - modelCx;
  const dy = at[1] * scale - modelCy;
  const rotation = Number(element.getAttribute("data-fp-rotation") ?? 0);
  const rotate = rotation ? ` rotate(${rotation.toFixed(3)} ${modelCx.toFixed(3)} ${modelCy.toFixed(3)})` : "";
  element.setAttribute("transform", `translate(${dx.toFixed(3)} ${dy.toFixed(3)})${rotate}`);
}

function rotateAroundCurrentCenter(element: SVGGraphicsElement, at: [number, number], scale: number) {
  const rotation = Number(element.getAttribute("data-fp-rotation") ?? 0);
  if (!rotation) {
    element.removeAttribute("transform");
    return;
  }
  const cx = at[0] * scale;
  const cy = at[1] * scale;
  element.setAttribute("transform", `rotate(${rotation.toFixed(3)} ${cx.toFixed(3)} ${cy.toFixed(3)})`);
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
  updateSpaceSvg(canvasElement, wallDrag.level, firstId, firstNext, scale);
  updateSpaceSvg(canvasElement, wallDrag.level, secondId, secondNext, scale);
  updateWallLineSvg(canvasElement, wallDrag, firstNext, secondNext, scale);
  updateWallPreviewSvg(canvasElement, wallDrag.level, wallDrag.id, wallLineFromRects(wallDrag.orientation, firstNext, secondNext), scale);
}

export function previewContainedWallSvg(
  canvasElement: HTMLDivElement | undefined,
  wallDrag: ContainedWallDrag,
  delta: number,
  scale: number
) {
  if (!canvasElement) {
    return;
  }
  const next = { ...wallDrag.startRect };
  if (wallDrag.edge === "left") {
    next.left += delta;
  } else if (wallDrag.edge === "right") {
    next.right += delta;
  } else if (wallDrag.edge === "top") {
    next.top += delta;
  } else {
    next.bottom += delta;
  }
  next.width = next.right - next.left;
  next.height = next.bottom - next.top;
  updateSpaceSvg(canvasElement, wallDrag.level, wallDrag.innerSpace, next, scale);
  updateWallPreviewSvg(canvasElement, wallDrag.level, wallDrag.id, movedLine(wallDrag.line, wallDrag.orientation, delta), scale);
}

export function previewExteriorWallSvg(
  canvasElement: HTMLDivElement | undefined,
  levelId: string,
  wallId: string,
  line: WallLine,
  orientation: "vertical" | "horizontal",
  delta: number,
  scale: number
) {
  if (!canvasElement) {
    return;
  }
  updateWallPreviewSvg(canvasElement, levelId, wallId, movedLine(line, orientation, delta), scale);
}

export function removeWallDragPreview(canvasElement: HTMLDivElement | undefined) {
  canvasElement?.querySelectorAll(".wall-drag-preview").forEach((element) => element.remove());
}

export function cssEscape(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function updateSpaceSvg(canvasElement: HTMLDivElement, levelId: string, id: string, rect: SpaceRect, scale: number) {
  canvasElement
    .querySelectorAll(`[data-fp-kind="space"][data-fp-id="${cssEscape(id)}"][data-fp-level="${cssEscape(levelId)}"]`)
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
    `[data-fp-kind="wall"][data-fp-id="${cssEscape(wallDrag.id)}"][data-fp-level="${cssEscape(wallDrag.level)}"]`
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

function updateWallPreviewSvg(canvasElement: HTMLDivElement, levelId: string, wallId: string, line: WallLine, scale: number) {
  const preview = ensureWallPreviewLine(canvasElement, levelId, wallId);
  if (!preview) {
    return;
  }
  preview.setAttribute("x1", (line.x1 * scale).toFixed(3));
  preview.setAttribute("y1", (line.y1 * scale).toFixed(3));
  preview.setAttribute("x2", (line.x2 * scale).toFixed(3));
  preview.setAttribute("y2", (line.y2 * scale).toFixed(3));
}

function ensureWallPreviewLine(canvasElement: HTMLDivElement, levelId: string, wallId: string): SVGLineElement | null {
  const existing = canvasElement.querySelector(
    `.wall-drag-preview[data-preview-for="${cssEscape(wallId)}"][data-fp-level="${cssEscape(levelId)}"]`
  );
  if (existing instanceof SVGLineElement) {
    return existing;
  }
  const anchor = canvasElement.querySelector(
    `.wall-grip-target[data-fp-id="${cssEscape(wallId)}"][data-fp-level="${cssEscape(levelId)}"]`
  );
  const parent = anchor?.parentElement;
  if (!parent) {
    return null;
  }
  const preview = document.createElementNS("http://www.w3.org/2000/svg", "line");
  preview.classList.add("wall-drag-preview");
  preview.setAttribute("data-preview-for", wallId);
  preview.setAttribute("data-fp-level", levelId);
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
  return Math.max(clearanceValue(feature.clearance), clearanceValue(catalogFeature?.clearance));
}

function clearanceValue(clearance: AnyRecord | undefined): number {
  if (!clearance) {
    return 0;
  }
  return Math.max(
    Number(clearance.around ?? 0),
    Number(clearance.walls ?? 0),
    Number(clearance.left ?? 0),
    Number(clearance.right ?? 0),
    Number(clearance.top ?? 0),
    Number(clearance.bottom ?? 0),
    Number(clearance.foot ?? 0)
  );
}
