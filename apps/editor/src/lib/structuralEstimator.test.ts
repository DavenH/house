import { describe, expect, it } from "vitest";
import { estimateStructuralPrep } from "./structuralEstimator";
import type { AnyRecord } from "./types";

function structuralPlan(): AnyRecord {
  return {
    datums: { x: { w: 0, e: 20 }, y: { n: 0, s: 12 } },
    roof: { pitch: "8:12", eave_margin: 2 },
    structural: {
      materials: {
        brick_masonry: { density_pcf: 120 }
      },
      design_loads: {
        floor_live_psf: 40,
        roof_dead_psf: 15,
        roof_snow_psf: null,
        wind_psf: null,
        soil_bearing_psf: null
      },
      rafters: { spacing_in: 16, purchase_length_threshold_ft: 8 },
      bearing: {
        point_loads: [
          { id: "chimney", kind: "masonry_mass", level: "L1", at: [5, 4], size: [4, 2], height_ft: 16, material: "brick_masonry" }
        ],
        line_loads: [
          { id: "tower", kind: "masonry_perimeter", level: "L1", space: "tower", height_ft: 24, wall_thickness_in: 8, material: "brick_masonry" }
        ]
      }
    },
    masses: {
      body: {
        levels: ["L1"],
        rect: { id: "main", x: ["w", "e"], y: ["n", "s"], roof: { mode: "open_gable", ridge: "x" } }
      }
    },
    levels: {
      L1: {
        spaces: {
          tower: { x: [12, 18], y: [4, 10] }
        }
      }
    }
  };
}

describe("estimateStructuralPrep", () => {
  it("estimates configured masonry loads and rafter purchase flags", () => {
    const estimate = estimateStructuralPrep(structuralPlan());

    expect(estimate.pointLoads[0].id).toBe("chimney");
    expect(estimate.pointLoads[0].loadLb).toBeCloseTo(15360);
    expect(estimate.pointLoads[0].pressurePsf).toBeCloseTo(1920);
    expect(estimate.lineLoads[0].id).toBe("tower");
    expect(estimate.lineLoads[0].loadPlf).toBeCloseTo(1920);
    expect(estimate.rafters[0].purchaseRequired).toBe(true);
    expect(estimate.missingInputs).toEqual(["roof_snow_psf", "wind_psf", "soil_bearing_psf"]);
  });
});
