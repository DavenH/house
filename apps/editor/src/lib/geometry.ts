import type {
  AnyRecord,
  ContainedWallDrag,
  ExteriorWallDrag,
  MassEdgeRef,
  OpeningDrag,
  OverlayDrag,
  SharedWallDrag,
  SpaceEdge,
  SpaceEdgeDrag,
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
  if (openingDrag.source === "opening" && !openingDrag.preserveSpaceSide) {
    opening.wall = openingDrag.wall;
    delete opening.space;
    delete opening.side;
  }
}

export function moveOverlay(data: AnyRecord, overlayDrag: OverlayDrag, dx: number, dy: number) {
  const overlay = overlayForDrag(data, overlayDrag);
  if (!overlay || !Array.isArray(overlay.points)) {
    return;
  }
  if (overlayDrag.pointIndex !== null) {
    const start = overlayDrag.startPoints[overlayDrag.pointIndex];
    if (!start) {
      return;
    }
    overlay.points[overlayDrag.pointIndex] = [start[0] + dx, start[1] + dy];
    return;
  }
  if (overlayDrag.segmentIndex !== null) {
    const movement = overlaySegmentMovement(overlayDrag.startPoints, overlayDrag.segmentIndex, dx, dy);
    for (const index of movement.indices) {
      const start = overlayDrag.startPoints[index];
      if (start) {
        overlay.points[index] = [start[0] + movement.dx, start[1] + movement.dy];
      }
    }
    return;
  }
  overlay.points = overlayDrag.startPoints.map(([x, y]) => [x + dx, y + dy]);
}

function overlaySegmentMovement(points: Array<[number, number]>, segmentIndex: number, dx: number, dy: number) {
  const orientation = overlaySegmentOrientation(points, segmentIndex);
  if (!orientation) {
    return { indices: [segmentIndex, segmentIndex + 1], dx, dy };
  }
  const indices = overlayCollinearChainPointIndices(points, segmentIndex, orientation);
  if (orientation === "vertical") {
    return { indices, dx, dy: 0 };
  }
  return { indices, dx: 0, dy };
}

function overlaySegmentOrientation(points: Array<[number, number]>, segmentIndex: number) {
  const first = points[segmentIndex];
  const second = points[segmentIndex + 1];
  if (!first || !second) {
    return null;
  }
  if (Math.abs(first[0] - second[0]) < 0.001) {
    return "vertical" as const;
  }
  if (Math.abs(first[1] - second[1]) < 0.001) {
    return "horizontal" as const;
  }
  return null;
}

function overlayCollinearChainPointIndices(
  points: Array<[number, number]>,
  segmentIndex: number,
  orientation: "vertical" | "horizontal"
) {
  const axis = orientation === "vertical" ? 0 : 1;
  const coordinate = points[segmentIndex]?.[axis];
  let firstSegment = segmentIndex;
  let lastSegment = segmentIndex;
  while (firstSegment > 0 && segmentMatches(points, firstSegment - 1, axis, coordinate)) {
    firstSegment -= 1;
  }
  while (lastSegment < points.length - 2 && segmentMatches(points, lastSegment + 1, axis, coordinate)) {
    lastSegment += 1;
  }
  return Array.from({ length: lastSegment - firstSegment + 2 }, (_, index) => firstSegment + index);
}

function segmentMatches(points: Array<[number, number]>, segmentIndex: number, axis: number, coordinate: number | undefined) {
  if (coordinate === undefined) {
    return false;
  }
  const first = points[segmentIndex];
  const second = points[segmentIndex + 1];
  return Boolean(first && second && Math.abs(first[axis] - coordinate) < 0.001 && Math.abs(second[axis] - coordinate) < 0.001);
}

function overlayForDrag(data: AnyRecord, overlayDrag: OverlayDrag) {
  return ((data.levels as AnyRecord | undefined)?.[overlayDrag.level]?.overlays?.[overlayDrag.layer] ?? [])[
    overlayDrag.index
  ] as AnyRecord | undefined;
}

export function spaceSideOpeningOffsetBounds(
  direction: WallDirection,
  openingLine: WallLine,
  startOffset: number,
  width: number,
  spaceRect: SpaceRect,
  side: string,
  fallbackWallLength: number
) {
  const axisStart = direction === "E" || direction === "W" ? openingLine.x1 : openingLine.y1;
  const wallStart =
    direction === "E" || direction === "S"
      ? axisStart - startOffset
      : axisStart + startOffset;
  const spanStart = side === "north" || side === "south" ? spaceRect.left : spaceRect.top;
  const spanEnd = side === "north" || side === "south" ? spaceRect.right : spaceRect.bottom;
  let first: number;
  let second: number;
  if (direction === "E" || direction === "S") {
    first = spanStart - wallStart;
    second = spanEnd - width - wallStart;
  } else {
    first = wallStart - (spanStart + width);
    second = wallStart - spanEnd;
  }
  return {
    min: clamp(Math.min(first, second), 0, fallbackWallLength - width),
    max: clamp(Math.max(first, second), 0, fallbackWallLength - width)
  };
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
  const movedEdges = new Set<string>();
  if (wallDrag.orientation === "vertical") {
    if (Math.abs(first.right - second.left) < 0.01) {
      if (moveSharedDatumBoundary(data, wallDrag.level, firstId, "right", secondId, "left", delta, touchedDatums)) {
        return;
      }
      moveSpaceEdgeAndStackedMembers(data, wallDrag.level, firstId, "right", delta, touchedDatums, movedEdges);
      moveSpaceEdgeAndStackedMembers(data, wallDrag.level, secondId, "left", delta, touchedDatums, movedEdges);
    } else {
      if (moveSharedDatumBoundary(data, wallDrag.level, firstId, "left", secondId, "right", delta, touchedDatums)) {
        return;
      }
      moveSpaceEdgeAndStackedMembers(data, wallDrag.level, firstId, "left", delta, touchedDatums, movedEdges);
      moveSpaceEdgeAndStackedMembers(data, wallDrag.level, secondId, "right", delta, touchedDatums, movedEdges);
    }
  } else if (Math.abs(first.bottom - second.top) < 0.01) {
    if (moveSharedDatumBoundary(data, wallDrag.level, firstId, "bottom", secondId, "top", delta, touchedDatums)) {
      return;
    }
    moveSpaceEdgeAndStackedMembers(data, wallDrag.level, firstId, "bottom", delta, touchedDatums, movedEdges);
    moveSpaceEdgeAndStackedMembers(data, wallDrag.level, secondId, "top", delta, touchedDatums, movedEdges);
  } else {
    if (moveSharedDatumBoundary(data, wallDrag.level, firstId, "top", secondId, "bottom", delta, touchedDatums)) {
      return;
    }
    moveSpaceEdgeAndStackedMembers(data, wallDrag.level, firstId, "top", delta, touchedDatums, movedEdges);
    moveSpaceEdgeAndStackedMembers(data, wallDrag.level, secondId, "bottom", delta, touchedDatums, movedEdges);
  }
}

export function moveExteriorWall(data: AnyRecord, wallDrag: ExteriorWallDrag, delta: number) {
  if (delta === 0) {
    return;
  }
  const touchedDatums = new Set<string>();
  const movedEdges = new Set<string>();
  for (const edgeRef of wallDrag.edgeRefs) {
    updateMassEdge(data, edgeRef, delta, touchedDatums);
  }
  updateSpacesAlongExteriorWall(data, wallDrag, delta, touchedDatums, movedEdges);
}

export function moveContainedWall(data: AnyRecord, wallDrag: ContainedWallDrag, delta: number) {
  if (delta === 0) {
    return;
  }
  const touchedDatums = new Set<string>();
  const movedEdges = new Set<string>();
  moveSpaceEdgeAndStackedMembers(data, wallDrag.level, wallDrag.innerSpace, wallDrag.edge, delta, touchedDatums, movedEdges);
}

export function moveSpaceEdgeForDrag(data: AnyRecord, spaceDrag: SpaceEdgeDrag, coordinate: number) {
  const space = ((data.levels as AnyRecord)?.[spaceDrag.level]?.spaces ?? {})[spaceDrag.id] as AnyRecord | undefined;
  if (!space) {
    return;
  }
  const axis = spaceEdgeAxis(spaceDrag.edge);
  const edgeIndex = spaceEdgeIndex(spaceDrag.edge);
  if (Array.isArray(space[axis])) {
    space[axis][edgeIndex] = coordinate;
    return;
  }
  if (!Array.isArray(space.rect)) {
    return;
  }
  if (spaceDrag.edge === "left") {
    const right = spaceDrag.startRect.right;
    space.rect[0] = coordinate;
    space.rect[2] = right - coordinate;
  } else if (spaceDrag.edge === "right") {
    space.rect[2] = coordinate - spaceDrag.startRect.left;
  } else if (spaceDrag.edge === "top") {
    const bottom = spaceDrag.startRect.bottom;
    space.rect[1] = coordinate;
    space.rect[3] = bottom - coordinate;
  } else {
    space.rect[3] = coordinate - spaceDrag.startRect.top;
  }
}

export function assignSpaceEdgeDatum(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  coordinate: number,
  snapTolerance = 0.25
) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return;
  }
  const axis = spaceEdgeAxis(edge);
  const edgeIndex = spaceEdgeIndex(edge);
  const datumName = nearestDatumName(data, axis, coordinate, snapTolerance) ?? createDatum(data, axis, suggestedDatumName(spaceId, edge), coordinate);
  if (Array.isArray(space[axis])) {
    space[axis][edgeIndex] = datumName;
    return;
  }
  if (Array.isArray(space.rect)) {
    const rect = rectSpecToRect(space.rect, data);
    if (!rect) {
      return;
    }
    space.x = [edge === "left" ? datumName : createDatum(data, "x", `${spaceId}_w`, rect.left), edge === "right" ? datumName : createDatum(data, "x", `${spaceId}_e`, rect.right)];
    space.y = [edge === "top" ? datumName : createDatum(data, "y", `${spaceId}_n`, rect.top), edge === "bottom" ? datumName : createDatum(data, "y", `${spaceId}_s`, rect.bottom)];
    delete space.rect;
  }
}

export function spaceEdgeCoordinate(rect: SpaceRect, edge: SpaceEdge) {
  if (edge === "left") {
    return rect.left;
  }
  if (edge === "right") {
    return rect.right;
  }
  if (edge === "top") {
    return rect.top;
  }
  return rect.bottom;
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
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  const sourceData = wallDrag.snapshot ?? data;
  const levels = (sourceData.levels ?? {}) as AnyRecord;
  for (const [levelId, levelData] of Object.entries(levels)) {
    for (const [spaceId] of Object.entries((levelData as AnyRecord).spaces ?? {})) {
      const rect = resolveSpaceRect(sourceData, levelId, spaceId);
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
          moveSpaceEdgeAndStackedMembers(data, levelId, spaceId, "left", delta, touchedDatums, movedEdges);
          moveAdjacentEdges(data, levelId, spaceId, rect, "left", delta, touchedDatums, movedEdges);
        }
        if (Math.abs(rect.right - x) < 0.01) {
          moveSpaceEdgeAndStackedMembers(data, levelId, spaceId, "right", delta, touchedDatums, movedEdges);
          moveAdjacentEdges(data, levelId, spaceId, rect, "right", delta, touchedDatums, movedEdges);
        }
      } else {
        const y = wallDrag.line.y1;
        const left = Math.min(wallDrag.line.x1, wallDrag.line.x2);
        const right = Math.max(wallDrag.line.x1, wallDrag.line.x2);
        if (!intervalsOverlap(rect.left, rect.right, left, right)) {
          continue;
        }
        if (Math.abs(rect.top - y) < 0.01) {
          moveSpaceEdgeAndStackedMembers(data, levelId, spaceId, "top", delta, touchedDatums, movedEdges);
          moveAdjacentEdges(data, levelId, spaceId, rect, "top", delta, touchedDatums, movedEdges);
        }
        if (Math.abs(rect.bottom - y) < 0.01) {
          moveSpaceEdgeAndStackedMembers(data, levelId, spaceId, "bottom", delta, touchedDatums, movedEdges);
          moveAdjacentEdges(data, levelId, spaceId, rect, "bottom", delta, touchedDatums, movedEdges);
        }
      }
    }
  }
}

function moveSharedDatumBoundary(
  data: AnyRecord,
  levelId: string,
  firstSpaceId: string,
  firstEdge: SpaceEdge,
  secondSpaceId: string,
  secondEdge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>
) {
  const firstDatum = edgeDatumRef(data, levelId, firstSpaceId, firstEdge);
  const secondDatum = edgeDatumRef(data, levelId, secondSpaceId, secondEdge);
  if (!firstDatum || firstDatum !== secondDatum) {
    return false;
  }
  const axis = firstEdge === "left" || firstEdge === "right" ? "x" : "y";
  return updateDatum(data, axis, firstDatum, delta, touchedDatums);
}

function edgeDatumRef(data: AnyRecord, levelId: string, spaceId: string, edge: SpaceEdge) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return null;
  }
  const axis = edge === "left" || edge === "right" ? "x" : "y";
  const index = edge === "left" || edge === "top" ? 0 : 1;
  const value = Array.isArray(space[axis]) ? space[axis][index] : null;
  return typeof value === "string" ? value : null;
}

function moveSpaceEdgeAndStackedMembers(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  if (!moveSpaceEdge(data, levelId, spaceId, edge, delta, touchedDatums, movedEdges)) {
    return;
  }
  moveConstrainedStackMembers(data, levelId, spaceId, edge, delta, touchedDatums, movedEdges);
}

function moveSpaceEdge(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  const key = `${levelId}.${spaceId}.${edge}`;
  if (movedEdges.has(key)) {
    return false;
  }
  movedEdges.add(key);
  return updateSpaceEdge(data, levelId, spaceId, edge, delta, touchedDatums);
}

function moveConstrainedStackMembers(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  const sourceRef = `${levelId}.${spaceId}`;
  for (const stack of (data.stacks ?? []) as AnyRecord[]) {
    const members = Array.isArray(stack.members) ? stack.members : [];
    if (!members.includes(sourceRef) || !stackConstrainsEdge(stack, edge)) {
      continue;
    }
    for (const member of members) {
      if (member === sourceRef || typeof member !== "string" || !member.includes(".")) {
        continue;
      }
      const [targetLevel, targetSpace] = member.split(".", 2);
      moveStackedSpaceEdgeAndNeighbors(data, targetLevel, targetSpace, edge, delta, touchedDatums, movedEdges);
    }
  }
}

function moveStackedSpaceEdgeAndNeighbors(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  const before = resolveSpaceRect(data, levelId, spaceId);
  if (!before || !moveSpaceEdge(data, levelId, spaceId, edge, delta, touchedDatums, movedEdges)) {
    return;
  }
  moveAdjacentEdges(data, levelId, spaceId, before, edge, delta, touchedDatums, movedEdges);
}

function moveAdjacentEdges(
  data: AnyRecord,
  levelId: string,
  movedSpaceId: string,
  before: SpaceRect,
  movedEdge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>,
  movedEdges: Set<string>
) {
  const spaces = (((data.levels as AnyRecord)?.[levelId] ?? {}) as AnyRecord).spaces ?? {};
  for (const [spaceId] of Object.entries(spaces)) {
    if (spaceId === movedSpaceId) {
      continue;
    }
    const rect = resolveSpaceRect(data, levelId, spaceId);
    if (!rect || !sharesMovedBoundary(before, rect, movedEdge)) {
      continue;
    }
    moveSpaceEdgeAndStackedMembers(
      data,
      levelId,
      spaceId,
      oppositeEdge(movedEdge),
      delta,
      touchedDatums,
      movedEdges
    );
  }
}

function sharesMovedBoundary(before: SpaceRect, rect: SpaceRect, edge: SpaceEdge) {
  if (edge === "bottom") {
    return Math.abs(rect.top - before.bottom) < 0.01 && intervalsOverlap(rect.left, rect.right, before.left, before.right);
  }
  if (edge === "top") {
    return Math.abs(rect.bottom - before.top) < 0.01 && intervalsOverlap(rect.left, rect.right, before.left, before.right);
  }
  if (edge === "right") {
    return Math.abs(rect.left - before.right) < 0.01 && intervalsOverlap(rect.top, rect.bottom, before.top, before.bottom);
  }
  return Math.abs(rect.right - before.left) < 0.01 && intervalsOverlap(rect.top, rect.bottom, before.top, before.bottom);
}

function oppositeEdge(edge: SpaceEdge): SpaceEdge {
  if (edge === "bottom") {
    return "top";
  }
  if (edge === "top") {
    return "bottom";
  }
  if (edge === "right") {
    return "left";
  }
  return "right";
}

function stackConstrainsEdge(stack: AnyRecord, edge: SpaceEdge) {
  const same = Array.isArray(stack.same) ? stack.same : [];
  if (same.includes("bbox")) {
    return true;
  }
  if (edge === "left") {
    return same.includes("x") || same.includes("w");
  }
  if (edge === "right") {
    return same.includes("w");
  }
  if (edge === "top") {
    return same.includes("y") || same.includes("h");
  }
  return same.includes("h");
}

function updateSpaceEdge(
  data: AnyRecord,
  levelId: string,
  spaceId: string,
  edge: SpaceEdge,
  delta: number,
  touchedDatums: Set<string>
) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return false;
  }
  const axis = edge === "left" || edge === "right" ? "x" : "y";
  const datumIndex = edge === "left" || edge === "top" ? 0 : 1;
  if (Array.isArray(space[axis])) {
    updateCellEdge(data, space, axis, datumIndex, delta, touchedDatums);
    return true;
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
    return true;
  }
  return false;
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
  const currentRef = owner[axis][edgeIndex];
  if (typeof currentRef === "string" && updateDatum(data, axis, currentRef, delta, _touchedDatums)) {
    return;
  }
  const current = datumValue(data, axis, currentRef);
  if (current !== null) {
    owner[axis][edgeIndex] = snapToGrid(current + delta);
  }
}

function updateDatum(
  data: AnyRecord,
  axis: "x" | "y",
  datumId: string,
  delta: number,
  touchedDatums: Set<string>
) {
  const key = `${axis}.${datumId}`;
  if (touchedDatums.has(key)) {
    return true;
  }
  const axisDatums = ((data.datums ?? {}) as AnyRecord)[axis] ?? {};
  if (typeof axisDatums[datumId] !== "number") {
    return false;
  }
  axisDatums[datumId] = snapToGrid(Number(axisDatums[datumId]) + delta);
  touchedDatums.add(key);
  return true;
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

function spaceEdgeAxis(edge: SpaceEdge): "x" | "y" {
  return edge === "left" || edge === "right" ? "x" : "y";
}

function spaceEdgeIndex(edge: SpaceEdge): 0 | 1 {
  return edge === "left" || edge === "top" ? 0 : 1;
}

function nearestDatumName(data: AnyRecord, axis: "x" | "y", coordinate: number, tolerance: number) {
  const datums = ((data.datums ?? {}) as AnyRecord)[axis] ?? {};
  let best: { name: string; distance: number } | null = null;
  for (const [name, value] of Object.entries(datums)) {
    if (typeof value !== "number") {
      continue;
    }
    const distance = Math.abs(value - coordinate);
    if (distance <= tolerance && (!best || distance < best.distance)) {
      best = { name, distance };
    }
  }
  return best?.name ?? null;
}

function createDatum(data: AnyRecord, axis: "x" | "y", preferredName: string, coordinate: number) {
  data.datums ??= {};
  data.datums[axis] ??= {};
  const datums = data.datums[axis] as AnyRecord;
  const base = cleanDatumName(preferredName);
  let name = base;
  let index = 2;
  while (Object.prototype.hasOwnProperty.call(datums, name)) {
    name = `${base}_${index}`;
    index += 1;
  }
  datums[name] = snapToGrid(coordinate);
  return name;
}

function suggestedDatumName(spaceId: string, edge: SpaceEdge) {
  const suffix = edge === "left" ? "w" : edge === "right" ? "e" : edge === "top" ? "n" : "s";
  return `${spaceId}_${suffix}`;
}

function cleanDatumName(value: string) {
  return (
    value
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean)
      .join("_") || "datum"
  );
}
