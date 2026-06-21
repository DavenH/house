import { describe, expect, it } from "vitest";
import {
  findConnectionOpeningInLevel,
  findOverlayInLevel,
  findOpening,
  findOpeningInLevel,
  setFeatureAt,
  setFeatureAtCoordinate
} from "./planEditing";
import type { AnyRecord } from "./types";

describe("stacked feature editing", () => {
  it("syncs cx for stacked hearth/chimney features", () => {
    const data: AnyRecord = {
      levels: {
        L1: { features: { hearth: { at: [32.5, 15.5], size: [3, 5] } } },
        L2: { features: { hearth: { at: [32.5, 17], size: [1.5, 4] } } }
      },
      stacks: [{ id: "hearth_stack", members: ["L1.hearth", "L2.hearth"], same: ["cx"] }]
    };

    setFeatureAt(data, "L1", "hearth", [32, 15.5]);

    expect(data.levels.L1.features.hearth.at).toEqual([32, 15.5]);
    expect(data.levels.L2.features.hearth.at).toEqual([32, 17]);
  });

  it("syncs cx when editing the numeric x coordinate", () => {
    const data: AnyRecord = {
      levels: {
        L1: { features: { hearth: { at: [32.5, 15.5] } } },
        L2: { features: { hearth: { at: [32.5, 17] } } }
      },
      stacks: [{ id: "hearth_stack", members: ["L1.hearth", "L2.hearth"], same: ["cx"] }]
    };

    setFeatureAtCoordinate(data, "L2", "hearth", 0, 33);

    expect(data.levels.L1.features.hearth.at[0]).toBe(33);
    expect(data.levels.L2.features.hearth.at[0]).toBe(33);
  });
});

describe("opening lookup", () => {
  it("can resolve duplicate rendered opening ids within the clicked level", () => {
    const data: AnyRecord = {
      levels: {
        L1: {
          openings: [{ id: "north_window", offset: 1 }],
          connections: [{ id: "shared_door", between: ["hall", "office"], offset: 2 }]
        },
        L2: {
          openings: [{ id: "north_window", offset: 3 }],
          connections: [{ id: "shared_door", between: ["hall", "bedroom"], offset: 4 }]
        }
      }
    };

    expect(findOpening(data, "north_window")).toEqual({ kind: "opening", level: "L1", id: "north_window", index: 0 });
    expect(findOpeningInLevel(data, "L2", "north_window")).toEqual({
      kind: "opening",
      level: "L2",
      id: "north_window",
      index: 0
    });
    expect(findConnectionOpeningInLevel(data, "L2", "shared_door")).toEqual({
      kind: "connection",
      level: "L2",
      id: "shared_door",
      index: 0
    });
  });
});

describe("overlay lookup", () => {
  it("finds overlay entries by level and id", () => {
    const data: AnyRecord = {
      levels: {
        L1: {
          overlays: {
            plumbing: [{ id: "cold_main", points: [[1, 2], [3, 2]] }],
            electrical: [{ id: "circuit", points: [[4, 5], [6, 5]] }]
          }
        }
      }
    };

    expect(findOverlayInLevel(data, "L1", "circuit")).toEqual({
      item: data.levels.L1.overlays.electrical[0],
      layer: "electrical",
      index: 0
    });
  });
});
