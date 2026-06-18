import { describe, expect, it } from "vitest";
import { moveOpening, moveSharedWall, resolveSpaceRect, spaceSideOpeningOffsetBounds } from "./geometry";
import type { AnyRecord, OpeningDrag, SharedWallDrag, SpaceRect } from "./types";

function rect(left: number, top: number, right: number, bottom: number): SpaceRect {
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

describe("moveSharedWall", () => {
  it("keeps stacked stair spaces and their connected neighbors synchronized", () => {
    const data: AnyRecord = {
      datums: {
        x: { left_e: 21, stair_e: 30 },
        y: { main_n: 7.5, stair_s: 18, public_split: 22, entry_s: 28 }
      },
      levels: {
        L1: {
          spaces: {
            stair: { x: ["left_e", "stair_e"], y: ["main_n", "stair_s"] },
            hall: { x: ["left_e", "stair_e"], y: ["stair_s", "public_split"] }
          }
        },
        L2: {
          spaces: {
            stair: { x: ["left_e", "stair_e"], y: ["main_n", "stair_s"] },
            upper_hall: { x: ["left_e", "stair_e"], y: ["stair_s", "entry_s"] }
          }
        }
      },
      stacks: [{ id: "stair_stack", members: ["L1.stair", "L2.stair"], same: ["x", "y", "w", "h"] }]
    };
    const drag: SharedWallDrag = {
      type: "wall",
      id: "stair__hall_wall",
      level: "L1",
      startPoint: { x: 0, y: 0 },
      orientation: "horizontal",
      spaces: ["stair", "hall"],
      startRects: [rect(21, 7.5, 30, 18), rect(21, 18, 30, 22)],
      snapshot: structuredClone(data)
    };

    moveSharedWall(data, drag, 1);

    expect(data.datums.y.stair_s).toBe(19);
    expect(resolveSpaceRect(data, "L1", "stair")?.height).toBe(11.5);
    expect(resolveSpaceRect(data, "L2", "stair")?.height).toBe(11.5);
    expect(resolveSpaceRect(data, "L1", "hall")?.top).toBe(19);
    expect(resolveSpaceRect(data, "L2", "upper_hall")?.top).toBe(19);
  });

  it("moves a shared datum instead of detaching one side of a datum-backed wall", () => {
    const data: AnyRecord = {
      datums: {
        x: { west: 1, storage_e: 8, left_w: 8, left_e: 21 },
        y: { main_n: 7.5, gable_n: 2, bath_s: 15, entry_s: 28 }
      },
      levels: {
        L1: {
          spaces: {
            laundry: { x: ["west", "storage_e"], y: ["main_n", "bath_s"] },
            bathroom: { x: ["left_w", "left_e"], y: ["gable_n", "bath_s"] },
            library: { x: ["west", "left_e"], y: ["bath_s", "entry_s"] }
          }
        }
      }
    };
    const drag: SharedWallDrag = {
      type: "wall",
      id: "bathroom__library_wall",
      level: "L1",
      startPoint: { x: 0, y: 0 },
      orientation: "horizontal",
      spaces: ["bathroom", "library"],
      startRects: [rect(8, 2, 21, 15), rect(1, 15, 21, 28)],
      snapshot: structuredClone(data)
    };

    moveSharedWall(data, drag, -1);

    expect(data.datums.y.bath_s).toBe(14);
    expect(data.levels.L1.spaces.bathroom.y).toEqual(["gable_n", "bath_s"]);
    expect(data.levels.L1.spaces.library.y).toEqual(["bath_s", "entry_s"]);
    expect(data.levels.L1.spaces.laundry.y).toEqual(["main_n", "bath_s"]);
    expect(resolveSpaceRect(data, "L1", "bathroom")?.bottom).toBe(14);
    expect(resolveSpaceRect(data, "L1", "library")?.top).toBe(14);
    expect(resolveSpaceRect(data, "L1", "laundry")?.bottom).toBe(14);
  });
});

describe("moveOpening", () => {
  it("preserves space-side openings instead of rewriting them to generated wall ids", () => {
    const data: AnyRecord = {
      levels: {
        L1: {
          openings: [{ id: "bath_window", space: "bathroom", side: "north", offset: 2, width: 5, kind: "window" }]
        }
      }
    };
    const drag: OpeningDrag = {
      type: "opening",
      id: "bath_window",
      level: "L1",
      index: 0,
      source: "opening",
      preserveSpaceSide: true,
      startPoint: { x: 0, y: 0 },
      wall: "exterior_5",
      direction: "E",
      orientation: "horizontal",
      startOffset: 2,
      offsetMin: 0,
      offsetMax: 8,
      width: 5,
      wallLength: 13,
      snapshot: structuredClone(data)
    };

    moveOpening(data, drag, 4);

    expect(data.levels.L1.openings[0]).toEqual({
      id: "bath_window",
      space: "bathroom",
      side: "north",
      offset: 4,
      width: 5,
      kind: "window"
    });
  });

  it("uses room-span bounds for west-facing space-side openings", () => {
    const bounds = spaceSideOpeningOffsetBounds(
      "N",
      { x1: 1, y1: 18, x2: 1, y2: 11 },
      19,
      7,
      { left: 1, right: 13, top: 10, bottom: 18, width: 12, height: 8 },
      "west",
      30
    );

    expect(bounds).toEqual({ min: 19, max: 20 });
  });
});
