import { describe, expect, it } from "vitest";
import * as yaml from "js-yaml";
import { estimateCosts, materialCostsFromPlan, materialCostsToYaml } from "./costEstimator";
import type { AnyRecord } from "./types";
import masterSouthYaml from "../../../../artifacts/floorplans/master-south.yaml?raw";
import sharedCostsYaml from "../../../../artifacts/floorplans/shared-costs.yaml?raw";
import sharedStructuralYaml from "../../../../artifacts/floorplans/shared-structural.yaml?raw";

const yamlFixtures: Record<string, string> = {
  "artifacts/floorplans/master-south.yaml": masterSouthYaml,
  "artifacts/floorplans/shared-costs.yaml": sharedCostsYaml,
  "artifacts/floorplans/shared-structural.yaml": sharedStructuralYaml
};

function deepMerge(base: AnyRecord, leaf: AnyRecord): AnyRecord {
  const out: AnyRecord = { ...base };
  for (const [key, value] of Object.entries(leaf)) {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      out[key] &&
      typeof out[key] === "object" &&
      !Array.isArray(out[key])
    ) {
      out[key] = deepMerge(out[key] as AnyRecord, value as AnyRecord);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function loadResolvedYaml(path: string, seen = new Set<string>()): AnyRecord {
  if (seen.has(path)) {
    throw new Error(`Cyclic YAML import: ${path}`);
  }
  const raw = yaml.load(yamlFixtures[path]) as AnyRecord;
  let merged: AnyRecord = {};
  const imports = raw.imports ? Array.isArray(raw.imports) ? raw.imports : [raw.imports] : [];
  for (const item of imports) {
    merged = deepMerge(merged, loadResolvedYaml(`artifacts/floorplans/${String(item)}`, new Set([...seen, path])));
  }
  const leaf = { ...raw };
  delete leaf.imports;
  return deepMerge(merged, leaf);
}

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
  it("loads material costs from plan costing material defaults", () => {
    const materials = materialCostsFromPlan({
      costing: {
        materials: {
          concrete: { label: "Concrete", unit: "yd3", unit_cost: 250 },
          custom_fasteners: { label: "Custom fasteners", unit: "box", unit_cost: 12.5 }
        }
      }
    });

    expect(materials.find((material) => material.id === "concrete")?.unitCost).toBe(250);
    expect(materials.find((material) => material.id === "custom_fasteners")).toEqual({
      id: "custom_fasteners",
      label: "Custom fasteners",
      unit: "box",
      unitCost: 12.5
    });
    expect(materialCostsToYaml(materials).concrete).toEqual({
      label: "Concrete",
      unit: "yd3",
      unit_cost: 250
    });
  });

  it("estimates first-pass concrete, rebar, walls, and roofing quantities", () => {
    const estimate = estimateCosts(simplePlan());
    const summary: Record<string, { value: number }> = {};
    for (const item of estimate.summary) {
      summary[item.label] = item;
    }

    expect(summary["Concrete pad area"].value).toBeCloseTo(120);
    expect(summary["Pad insulation area"].value).toBeCloseTo(288);
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
    const padInsulation = estimate.quantities.find((item) => item.id === "pad_insulation");
    expect(padInsulation?.group).toBe("pad");
    expect(padInsulation?.notes).toContain("Under-slab");
    expect(estimate.total).toBeGreaterThan(0);
  });

  it("updates quantities when datum-backed mass dimensions move", () => {
    const base = estimateCosts(simplePlan(10));
    const wider = estimateCosts(simplePlan(14));
    const basePad = base.summary.find((item) => item.label === "Concrete pad area")?.value ?? 0;
    const widerPad = wider.summary.find((item) => item.label === "Concrete pad area")?.value ?? 0;

    expect(widerPad).toBeGreaterThan(basePad);
  });

  it("uses face-level roof and exterior wall quantities for master south", () => {
    const data = loadResolvedYaml("artifacts/floorplans/master-south.yaml");
    const estimate = estimateCosts(data, undefined, materialCostsFromPlan(data));
    const byId = estimate.quantities.reduce<Record<string, (typeof estimate.quantities)[number]>>((result, item) => {
      result[item.id] = item;
      return result;
    }, {});
    const summary = estimate.summary.reduce<Record<string, (typeof estimate.summary)[number]>>((result, item) => {
      result[item.label] = item;
      return result;
    }, {});

    expect(byId.roofing_area.quantity).toBeCloseTo(2708, 0);
    expect(byId.exterior_cladding.quantity).toBeCloseTo(3472, 0);
    expect(summary["Exterior wall area"].value).toBeCloseTo(3156, 0);
    expect(byId.roofing_area.quantity).toBeLessThan(3500);
    expect(byId.exterior_cladding.quantity).toBeLessThan(4500);
    expect(byId.roofing_area.breakdown?.some((line) => line.includes("main_gable"))).toBe(true);
    expect(byId.exterior_cladding.breakdown?.some((line) => line.includes("Open-gable triangular"))).toBe(true);
  });
});
