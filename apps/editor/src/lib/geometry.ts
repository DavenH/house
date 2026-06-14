import type {
  AnyRecord,
  ExteriorWallDrag,
  MassEdgeRef,
  OpeningDrag,
  SharedWallDrag,
  SpaceRect,
  WallDirection,
  WallLine
} from "./types";

export function snapToGrid(value: number) {
  return Math.round(value * 2) / 2;
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

export function openingAxisDelta(direction: WallDirection, dx: number, dy: number) {
  if (direction === "E") {
    return dx;
  }
  if (direction === "W") {
    return -dx;
  }
  if (direction === "S") {
    return dy;
  }
  return -dy;
}

export function openingDeltaVector(direction: WallDirection, offsetDelta: number) {
  if (direction === "E") {
    return { x: offsetDelta, y: 0 };
  }
  if (direction === "W") {
    return { x: -offsetDelta, y: 0 };
  }
  if (direction === "S") {
    return { x: 0, y: offsetDelta };
  }
  return { x: 0, y: -offsetDelta };
}

export function moveOpening(data: AnyRecord, openingDrag: OpeningDrag, offset: number) {
  const levelData = ((data.levels as AnyRecord)?.[openingDrag.level] ?? {}) as AnyRecord;
  const items = openingDrag.source === "connection" ? levelData.connections ?? [] : levelData.openings ?? [];
  if (openingDrag.source === "connection" && Array.isArray(items[openingDrag.index])) {
    items[openingDrag.index] = { between: [...items[openingDrag.index]] };
  }
  const opening = items[openingDrag.index] as AnyRecord | undefined;
  if (!opening) {
    return;
  }
  opening.offset = offset;
  delete opening.position;
  if (openingDrag.source === "opening") {
    opening.wall = openingDrag.wall;
    delete opening.space;
    delete opening.side;
  }
}

export function moveSharedWall(data: AnyRecord, wallDrag: SharedWallDrag, delta: number) {
  if (delta === 0) {
    return;
  }
  const [firstId, secondId] = wallDrag.spaces;
  const first = resolveSpaceRect(data, wallDrag.level, firstId);
  const second = resolveSpaceRect(data, wallDrag.level, secondId);
  if (!first || !second) {
    return;
  }
  const touchedDatums = new Set<string>();
  if (wallDrag.orientation === "vertical") {
    if (Math.abs(first.right - second.left) < 0.01) {
      updateSpaceEdge(data, wallDrag.level, firstId, "right", delta, touchedDatums);
      updateSpaceEdge(data, wallDrag.level, secondId, "left", delta, touchedDatums);
    } else {
      updateSpaceEdge(data, wallDrag.level, firstId, "left", delta, touchedDatums);
      updateSpaceEdge(data, wallDrag.level, secondId, "right", delta, touchedDatums);
    }
  } else if (Math.abs(first.bottom - second.top) < 0.01) {
    updateSpaceEdge(data, wallDrag.level, firstId, "bottom", delta, touchedDatums);
    updateSpaceEdge(data, wallDrag.level, secondId, "top", delta, touchedDatums);
  } else {
    updateSpaceEdge(data, wallDrag.level, firstId, "top", delta, touchedDatums);
    updateSpaceEdge(data, wallDrag.level, secondId, "bottom", delta, touchedDatums);
  }
}

export function moveExteriorWall(data: AnyRecord, wallDrag: ExteriorWallDrag, delta: number) {
  if (delta === 0) {
    return;
  }
  const touchedDatums = new Set<string>();
  for (const edgeRef of wallDrag.edgeRefs) {
    updateMassEdge(data, edgeRef, delta, touchedDatums);
  }
  updateSpacesAlongExteriorWall(data, wallDrag, delta, touchedDatums);
}

export function findMassEdgeRefs(
  levelId: string,
  line: WallLine,
  orientation: "vertical" | "horizontal",
  sourceData: AnyRecord
): MassEdgeRef[] {
  const refs: MassEdgeRef[] = [];
  const masses = (sourceData.masses ?? {}) as AnyRecord;
  for (const [massId, mass] of Object.entries(masses)) {
    if (!massAppliesToLevel(mass as AnyRecord, levelId)) {
      continue;
    }
    const rectEntries = massRectEntries(mass as AnyRecord);
    for (const entry of rectEntries) {
      const rect = rectSpecToRect(entry.rect, sourceData);
      if (!rect) {
        continue;
      }
      if (orientation === "vertical") {
        const x = line.x1;
        const top = Math.min(line.y1, line.y2);
        const bottom = Math.max(line.y1, line.y2);
        if (Math.abs(rect.left - x) < 0.02 && intervalsOverlap(rect.top, rect.bottom, top, bottom)) {
          refs.push({ massId, rectIndex: entry.index, edge: "left" });
        }
        if (Math.abs(rect.right - x) < 0.02 && intervalsOverlap(rect.top, rect.bottom, top, bottom)) {
          refs.push({ massId, rectIndex: entry.index, edge: "right" });
        }
      } else {
        const y = line.y1;
        const left = Math.min(line.x1, line.x2);
        const right = Math.max(line.x1, line.x2);
        if (Math.abs(rect.top - y) < 0.02 && intervalsOverlap(rect.left, rect.right, left, right)) {
          refs.push({ massId, rectIndex: entry.index, edge: "top" });
        }
        if (Math.abs(rect.bottom - y) < 0.02 && intervalsOverlap(rect.left, rect.right, left, right)) {
          refs.push({ massId, rectIndex: entry.index, edge: "bottom" });
        }
      }
    }
  }
  return refs;
}

export function resolveSpaceRect(data: AnyRecord, levelId: string, spaceId: string) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return null;
  }
  return rectSpecToRect(space.rect ?? space, data);
}

export function rectSpecToRect(rect: any, sourceData: AnyRecord): SpaceRect | null {
  if (Array.isArray(rect)) {
    const [x, y, w, h] = rect.map(Number);
    return { left: x, top: y, right: x + w, bottom: y + h, width: w, height: h };
  }
  if (rect && Array.isArray(rect.x) && Array.isArray(rect.y)) {
    const left = datumValue(sourceData, "x", rect.x[0]);
    const right = datumValue(sourceData, "x", rect.x[1]);
    const top = datumValue(sourceData, "y", rect.y[0]);
    const bottom = datumValue(sourceData, "y", rect.y[1]);
    if ([left, right, top, bottom].some((value) => value === null)) {
      return null;
    }
    return {
      left: left as number,
      top: top as number,
      right: right as number,
      bottom: bottom as number,
      width: (right as number) - (left as number),
      height: (bottom as number) - (top as number)
    };
  }
  return null;
}

export function intervalsOverlap(a1: number, a2: number, b1: number, b2: number) {
  return Math.min(a2, b2) - Math.max(a1, b1) > 0.01;
}

export function movedPreviewRect(
  rect: SpaceRect,
  other: SpaceRect,
  orientation: "vertical" | "horizontal",
  delta: number,
  first: boolean
): SpaceRect {
  const next = { ...rect };
  if (orientation === "vertical") {
    const firstTouchesLeftOfOther = first
      ? Math.abs(rect.right - other.left) < 0.01
      : Math.abs(other.right - rect.left) < 0.01;
    if (firstTouchesLeftOfOther) {
      next.right = rect.right + delta;
    } else {
      next.left = rect.left + delta;
    }
  } else {
    const firstTouchesAboveOther = first
      ? Math.abs(rect.bottom - other.top) < 0.01
      : Math.abs(other.bottom - rect.top) < 0.01;
    if (firstTouchesAboveOther) {
      next.bottom = rect.bottom + delta;
    } else {
      next.top = rect.top + delta;
    }
  }
  next.width = next.right - next.left;
  next.height = next.bottom - next.top;
  return next;
}

export function wallLineFromRects(
  orientation: "vertical" | "horizontal",
  firstRect: SpaceRect,
  secondRect: SpaceRect
): WallLine {
  const x =
    Math.abs(firstRect.right - secondRect.left) < 0.01
      ? firstRect.right
      : Math.abs(secondRect.right - firstRect.left) < 0.01
        ? firstRect.left
        : firstRect.right;
  const y =
    Math.abs(firstRect.bottom - secondRect.top) < 0.01
      ? firstRect.bottom
      : Math.abs(secondRect.bottom - firstRect.top) < 0.01
        ? firstRect.top
        : firstRect.bottom;
  if (orientation === "vertical") {
    return {
      x1: x,
      x2: x,
      y1: Math.max(firstRect.top, secondRect.top),
      y2: Math.min(firstRect.bottom, secondRect.bottom)
    };
  }
  return {
    x1: Math.max(firstRect.left, secondRect.left),
    x2: Math.min(firstRect.right, secondRect.right),
    y1: y,
    y2: y
  };
}

export function movedLine(line: WallLine, orientation: "vertical" | "horizontal", delta: number): WallLine {
  return orientation === "vertical"
    ? { x1: line.x1 + delta, y1: line.y1, x2: line.x2 + delta, y2: line.y2 }
    : { x1: line.x1, y1: line.y1 + delta, x2: line.x2, y2: line.y2 + delta };
}

function massAppliesToLevel(mass: AnyRecord, levelId: string) {
  if (mass.level === levelId) {
    return true;
  }
  return Array.isArray(mass.levels) && mass.levels.includes(levelId);
}

function massRectEntries(mass: AnyRecord): Array<{ index: number | null; rect: unknown }> {
  if (Array.isArray(mass.rects)) {
    return mass.rects.map((rect: unknown, index: number) => ({ index, rect }));
  }
  if (mass.rect) {
    return [{ index: null, rect: mass.rect }];
  }
  return [];
}

function updateMassEdge(data: AnyRecord, edgeRef: MassEdgeRef, delta: number, touchedDatums: Set<string>) {
  const mass = ((data.masses ?? {}) as AnyRecord)[edgeRef.massId];
  const rect =
    edgeRef.rectIndex === null
      ? mass?.rect
      : Array.isArray(mass?.rects)
        ? mass.rects[edgeRef.rectIndex]
        : null;
  if (!rect) {
    return;
  }
  const axis = edgeRef.edge === "left" || edgeRef.edge === "right" ? "x" : "y";
  const edgeIndex = edgeRef.edge === "left" || edgeRef.edge === "top" ? 0 : 1;
  if (Array.isArray(rect[axis])) {
    updateCellEdge(data, rect, axis, edgeIndex, delta, touchedDatums);
    return;
  }
  if (Array.isArray(rect)) {
    if (edgeRef.edge === "left") {
      rect[0] = snapToGrid(Number(rect[0]) + delta);
      rect[2] = snapToGrid(Number(rect[2]) - delta);
    } else if (edgeRef.edge === "right") {
      rect[2] = snapToGrid(Number(rect[2]) + delta);
    } else if (edgeRef.edge === "top") {
      rect[1] = snapToGrid(Number(rect[1]) + delta);
      rect[3] = snapToGrid(Number(rect[3]) - delta);
    } else {
      rect[3] = snapToGrid(Number(rect[3]) + delta);
    }
  }
}

function updateSpacesAlongExteriorWall(
  data: AnyRecord,
  wallDrag: ExteriorWallDrag,
  delta: number,
  touchedDatums: Set<string>
) {
  const levels = (data.levels ?? {}) as AnyRecord;
  for (const [levelId, levelData] of Object.entries(levels)) {
    for (const [spaceId] of Object.entries((levelData as AnyRecord).spaces ?? {})) {
      const rect = resolveSpaceRect(data, levelId, spaceId);
      if (!rect) {
        continue;
      }
      if (wallDrag.orientation === "vertical") {
        const x = wallDrag.line.x1;
        const top = Math.min(wallDrag.line.y1, wallDrag.line.y2);
        const bottom = Math.max(wallDrag.line.y1, wallDrag.line.y2);
        if (!intervalsOverlap(rect.top, rect.bottom, top, bottom)) {
          continue;
        }
        if (Math.abs(rect.left - x) < 0.01) {
          updateSpaceEdge(data, levelId, spaceId, "left", delta, touchedDatums);
        }
        if (Math.abs(rect.right - x) < 0.01) {
          updateSpaceEdge(data, levelId, spaceId, "right", delta, touchedDatums);
        }
      } else {
        const y = wallDrag.line.y1;
        const left = Math.min(wallDrag.line.x1, wallDrag.line.x2);
        const right = Math.max(wallDrag.line.x1, wallDrag.line.x2);
        if (!intervalsOverlap(rect.left, rect.right, left, right)) {
          continue;
        }
        if (Math.abs(rect.top - y) < 0.01) {
          updateSpaceEdge(data, levelId, spaceId, "top", delta, touchedDatums);
        }
        if (Math.abs(rect.bottom - y) < 0.01) {
          updateSpaceEdge(data, levelId, spaceId, "bottom", delta, touchedDatums);
        }
      }
    }
  }
}

function updateSpaceEdge(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: "left" | "right" | "top" | "bottom",
  delta: number,
  touchedDatums: Set<string>
) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return;
  }
  const axis = edge === "left" || edge === "right" ? "x" : "y";
  const datumIndex = edge === "left" || edge === "top" ? 0 : 1;
  if (Array.isArray(space[axis])) {
    updateCellEdge(data, space, axis, datumIndex, delta, touchedDatums);
    return;
  }
  if (Array.isArray(space.rect)) {
    if (edge === "left") {
      space.rect[0] = snapToGrid(Number(space.rect[0]) + delta);
      space.rect[2] = snapToGrid(Number(space.rect[2]) - delta);
    } else if (edge === "right") {
      space.rect[2] = snapToGrid(Number(space.rect[2]) + delta);
    } else if (edge === "top") {
      space.rect[1] = snapToGrid(Number(space.rect[1]) + delta);
      space.rect[3] = snapToGrid(Number(space.rect[3]) - delta);
    } else {
      space.rect[3] = snapToGrid(Number(space.rect[3]) + delta);
    }
  }
}

function updateCellEdge(
  data: AnyRecord,
  owner: AnyRecord,
  axis: "x" | "y",
  edgeIndex: number,
  delta: number,
  _touchedDatums: Set<string>
) {
  if (!Array.isArray(owner[axis])) {
    return;
  }
  const current = datumValue(data, axis, owner[axis][edgeIndex]);
  if (current !== null) {
    owner[axis][edgeIndex] = snapToGrid(current + delta);
  }
}

function datumValue(sourceData: AnyRecord, axis: "x" | "y", value: unknown): number | null {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const axisDatums = ((sourceData.datums ?? {}) as AnyRecord)[axis] ?? {};
    return typeof axisDatums[value] === "number" ? axisDatums[value] : null;
  }
  return null;
}
