import { describe, expect, it } from "vitest";
import {
  inferSpaceSideForWallLine,
  openingReferenceForWall,
  stabilizeGeneratedExteriorWallOpenings
} from "./exteriorOpenings";
import type { AnyRecord, WallLine } from "./types";

describe("exterior opening stabilization", () => {
  it("infers the adjacent space side for a perimeter wall line", () => {
    const data = planData();

    expect(inferSpaceSideForWallLine(data, "L1", { x1: 63, y1: 28, x2: 54, y2: 28 })).toEqual({
      space: "dining",
      side: "south"
    });
    expect(inferSpaceSideForWallLine(data, "L1", { x1: 8, y1: 3, x2: 21, y2: 3 })).toEqual({
      space: "bathroom",
      side: "north"
    });
  });

  it("converts generated exterior wall openings to stable space-side openings", () => {
    const data = planData();
    const wallLines: Record<string, WallLine> = {
      exterior_5: { x1: 63, y1: 28, x2: 54, y2: 28 }
    };

    const changed = stabilizeGeneratedExteriorWallOpenings(data, "L1", (wallId) => wallLines[wallId] ?? null);

    expect(changed).toBe(true);
    expect(data.levels.L1.openings[0]).toEqual({
      id: "dining_south_window",
      offset: 3,
      width: 5,
      kind: "window",
      space: "dining",
      side: "south"
    });
  });

  it("keeps direct add-window references on generated exterior wall ids", () => {
    const data = planData();
    const line = { x1: 32, y1: 22.5, x2: 32, y2: 30 };

    expect(openingReferenceForWall(data, "L1", "exterior_15", line)).toEqual({
      wall: "exterior_15"
    });
  });
});

function planData(): AnyRecord {
  return {
    levels: {
      L1: {
        spaces: {
          bathroom: { rect: [8, 3, 13, 10] },
          dining: { rect: [54, 17.5, 9, 10.5] }
        },
        openings: [{ id: "dining_south_window", wall: "exterior_5", offset: 3, width: 5, kind: "window" }]
      }
    }
  };
}
