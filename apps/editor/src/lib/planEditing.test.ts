import { describe, expect, it } from "vitest";
import { setFeatureAt, setFeatureAtCoordinate } from "./planEditing";
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
