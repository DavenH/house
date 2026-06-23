import { describe, expect, it } from "vitest";
import { estimateCosts } from "./costEstimator";
import type { AnyRecord } from "./types";

function simplePlan(east = 10): AnyRecord {
  return {
    datums: { x: { w: 0, mid: 5, e: east }, y: { n: 0, s: 8 } },
    masses: {
      body: { levels: ["L1"], rect: { x: ["w", "e"], y: ["n", "s"] } }
    },
    levels: {
      L1: {
        derive_partitions: true,
        spaces: {
          left: { x: ["w", "mid"], y: ["n", "s"] },
          right: { x: ["mid", "e"], y: ["n", "s"] }
        },
        openings: [{ id: "front_window", space: "left", side: "north", width: 2, kind: "window" }],
        connections: [{ between: ["left", "right"], width: 3, kind: "door" }]
      }
    },
    foundations: {
      F1: {
        source_level: "L1",
        masses: ["body"],
        pad_rebar_spacing: 4,
        pad_rebar_edge_cover: 2 / 12
      }
    },
    costing: {
      exterior_wall: {
        icf: {
          block: { length_ft: 4, height_ft: 1 },
          concrete_thickness_in: 6,
          insulation_thickness_in: 2.5,
          waste_percent: 10
        },
        cladding: { type: "fieldstone", thickness_in: 4, waste_percent: 5 }
      },
      plumbing: { pex_per_wet_space_ft: 50 }
    },
    roof: { pitch: "0:12" }
  };
}

describe("estimateCosts", () => {
  it("estimates first-pass concrete, rebar, walls, and roofing quantities", () => {
    const estimate = estimateCosts(simplePlan());
    const summary: Record<string, { value: number }> = {};
    for (const item of estimate.summary) {
      summary[item.label] = item;
    }

    expect(summary["Concrete pad area"].value).toBeCloseTo(120);
    expect(summary["Pad insulation area"].value).toBeCloseTo(168);
    expect(summary["Concrete volume"].value).toBeCloseTo((120 * (4 / 12) + 40 * 2 * 1) / 27);
    expect(summary["Roofing area"].value).toBeCloseTo(88);
    expect(summary["Interior wall area"].value).toBeCloseTo(102);
    expect(summary["Interior doors"].value).toBe(1);
    expect(summary["Exterior wall area"].value).toBeCloseTo(352);
    expect(summary["Exterior wall thickness"].value).toBeCloseTo(15);
    expect(summary["ICF blocks"].value).toBe(97);
    expect(summary["Window area"].value).toBeCloseTo(8);
    expect(summary["Flooring area"].value).toBeCloseTo(86.4);
    expect(summary["PEX length"].value).toBe(0);
    expect(summary["Rebar length"].value).toBeGreaterThan(100);
    expect(estimate.quantities.find((item) => item.id === "pad_insulation")?.group).toBe("pad");
    expect(estimate.total).toBeGreaterThan(0);
  });

  it("updates quantities when datum-backed mass dimensions move", () => {
    const base = estimateCosts(simplePlan(10));
    const wider = estimateCosts(simplePlan(14));
    const basePad = base.summary.find((item) => item.label === "Concrete pad area")?.value ?? 0;
    const widerPad = wider.summary.find((item) => item.label === "Concrete pad area")?.value ?? 0;

    expect(widerPad).toBeGreaterThan(basePad);
  });
});
