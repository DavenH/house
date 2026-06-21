import { rectSpecToRect } from "./geometry";
import type { AnyRecord, WallLine } from "./types";

export type SpaceSideRef = {
  space: string;
  side: "north" | "east" | "south" | "west";
};

const GENERATED_EXTERIOR_WALL_ID = /^exterior_\d+$/;

export function openingReferenceForWall(
  data: AnyRecord,
  levelId: string,
  wallId: string,
  line: WallLine | null
): { wall: string } | SpaceSideRef {
  if (!line || GENERATED_EXTERIOR_WALL_ID.test(wallId)) {
    return { wall: wallId };
  }
  return inferSpaceSideForWallLine(data, levelId, line) ?? { wall: wallId };
}

export function inferSpaceSideForWallLine(data: AnyRecord, levelId: string, line: WallLine): SpaceSideRef | null {
  const level = ((data.levels as AnyRecord | undefined)?.[levelId] ?? {}) as AnyRecord;
  const spaces = (level.spaces ?? {}) as AnyRecord;
  const horizontal = Math.abs(line.y1 - line.y2) < 0.01;
  const vertical = Math.abs(line.x1 - line.x2) < 0.01;
  if (!horizontal && !vertical) {
    return null;
  }

  let best: (SpaceSideRef & { overlap: number }) | null = null;
  for (const [spaceId, spaceData] of Object.entries(spaces)) {
    const rect = rectSpecToRect((spaceData as AnyRecord).rect ?? spaceData, data);
    if (!rect) {
      continue;
    }
    let candidate: SpaceSideRef | null = null;
    let overlap = 0;
    if (horizontal) {
      const y = line.y1;
      const left = Math.min(line.x1, line.x2);
      const right = Math.max(line.x1, line.x2);
      if (Math.abs(rect.top - y) < 0.02) {
        candidate = { space: spaceId, side: "north" };
      } else if (Math.abs(rect.bottom - y) < 0.02) {
        candidate = { space: spaceId, side: "south" };
      }
      overlap = intervalOverlap(rect.left, rect.right, left, right);
    } else {
      const x = line.x1;
      const top = Math.min(line.y1, line.y2);
      const bottom = Math.max(line.y1, line.y2);
      if (Math.abs(rect.left - x) < 0.02) {
        candidate = { space: spaceId, side: "west" };
      } else if (Math.abs(rect.right - x) < 0.02) {
        candidate = { space: spaceId, side: "east" };
      }
      overlap = intervalOverlap(rect.top, rect.bottom, top, bottom);
    }
    if (candidate && overlap > 0.01 && (!best || overlap > best.overlap)) {
      best = { ...candidate, overlap };
    }
  }
  return best ? { space: best.space, side: best.side } : null;
}

export function stabilizeGeneratedExteriorWallOpenings(
  data: AnyRecord,
  levelId: string,
  wallLineForId: (wallId: string) => WallLine | null
) {
  const openings = ((data.levels as AnyRecord | undefined)?.[levelId]?.openings ?? []) as AnyRecord[];
  let changed = false;
  for (const opening of openings) {
    if (
      typeof opening.wall !== "string" ||
      !GENERATED_EXTERIOR_WALL_ID.test(opening.wall) ||
      opening.space ||
      opening.side
    ) {
      continue;
    }
    const line = wallLineForId(opening.wall);
    if (!line) {
      continue;
    }
    const stableRef = inferSpaceSideForWallLine(data, levelId, line);
    if (!stableRef) {
      continue;
    }
    opening.space = stableRef.space;
    opening.side = stableRef.side;
    delete opening.wall;
    changed = true;
  }
  return changed;
}

function intervalOverlap(a1: number, a2: number, b1: number, b2: number) {
  return Math.min(a2, b2) - Math.max(a1, b1);
}
