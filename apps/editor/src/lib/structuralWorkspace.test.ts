import { describe, expect, it } from "vitest";
import { availableStructuralSystems, calculateJoist, compileStructuralSystem, DEFAULT_STRUCTURAL_INPUTS, sizeJoistCandidates, structuralMaterialSubtotal } from "./structuralWorkspace";

const plan = {
  structural: { systems: [{ id: "bay", name: "Test bay", level: "L2", spaces: ["a", "b"], direction: "x", status: "concept" }] },
  levels: { L2: { spaces: { a: { rect: [10, 4, 8, 10] }, b: { rect: [10, 14, 8, 6] } } } }
};

describe("structural workspace", () => {
  it("derives member geometry only from an authored system and spacing", () => {
    const system = compileStructuralSystem(plan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay" });
    expect(system?.bounds).toEqual({ x: 10, y: 4, width: 8, height: 16 });
    expect(system?.members).toHaveLength(13);
    expect(system?.members[0].lengthFt).toBe(8);
    expect(system?.source).toContain("structural.systems.bay");
  });

  it("does not calculate with missing assumptions", () => {
    const system = compileStructuralSystem(plan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay" });
    expect(calculateJoist(system, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay" })).toBeNull();
  });

  it("reproduces a simple-span uniform-load screening calculation", () => {
    const inputs = { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay", nominalDepthIn: 9.25, actualWidthIn: 1.5, modulusPsi: 1_400_000, bendingPsi: 875, shearPsi: 135, deadLoadPsf: 15, liveLoadPsf: 40, deflectionLimit: 360 };
    const result = calculateJoist(compileStructuralSystem(plan, inputs), inputs);
    expect(result?.lineLoadPlf).toBeCloseTo(73.333, 2);
    expect(result?.maxMomentLbFt).toBeCloseTo(586.667, 2);
    expect(result?.maxShearLb).toBeCloseTo(293.333, 2);
    expect(result?.deflectionIn).toBeGreaterThan(0);
  });

  it("selects the shallowest candidate passing every implemented check", () => {
    const inputs = { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay" };
    const candidates = sizeJoistCandidates(compileStructuralSystem(plan, inputs), inputs);
    const recommended = candidates.find((candidate) => candidate.passes);
    expect(recommended).toBeTruthy();
    expect(candidates.slice(0, candidates.indexOf(recommended!)).every((candidate) => !candidate.passes)).toBe(true);
  });

  it("distributes an authored feature mass to intersecting joists", () => {
    const loadedPlan = structuredClone(plan);
    (loadedPlan.levels.L2 as any).features = { safe: { at: [12, 8], size: [3, 3], structural_mass_lb: 900 } };
    const inputs = { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay", nominalDepthIn: 11.25 };
    const system = compileStructuralSystem(loadedPlan, inputs);
    expect(system?.governingFeatureLoadLb).toBe(300);
    expect(calculateJoist(system, inputs)?.pointLoadLb).toBe(300);
  });

  it("prices selected solid-sawn framing from purchasable stock lengths", () => {
    const inputs = { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "bay", nominalDepthIn: 11.25, unitCost: 2, wastePercent: 10, regionalCostMultiplier: 1.2 };
    const system = compileStructuralSystem(plan, inputs);
    const price = structuralMaterialSubtotal(system, inputs);
    expect(price?.boardFeet).toBe(146.25);
    expect(price?.total).toBeCloseTo(934.1904);
  });

  it("lists mass-defined zones without inventing framing for them", () => {
    const massPlan = { ...plan, datums: { x: { west: 0, east: 20 }, y: { north: 0, south: 30 } }, masses: { house: { levels: ["L2"], rects: [{ id: "other_gable", x: ["west", "east"], y: ["north", "south"] }] } } };
    const discovered = availableStructuralSystems(massPlan).find((system) => system.source_mass === "other_gable");
    expect(discovered?.status).toBe("unresolved");
    const system = compileStructuralSystem(massPlan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: discovered!.id });
    expect(system?.members).toHaveLength(0);
    expect(system?.authored).toBe(false);
  });

  it("clips joists to an L-shaped union instead of framing through its void", () => {
    const lPlan = {
      structural: { systems: [{ id: "l", level: "L2", kind: "floor", spaces: ["west", "south"], direction: "y" }] },
      levels: { L2: { spaces: { west: { rect: [0, 0, 6, 15] }, south: { rect: [6, 10, 12, 5] } } } }
    };
    const system = compileStructuralSystem(lPlan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "l" });
    expect(system?.members.some((member) => member.x1 > 6 && member.y1 < 10)).toBe(false);
    expect(Math.max(...(system?.members.map((member) => member.lengthFt) ?? []))).toBe(15);
  });

  it("uses the mass footprint instead of treating unnamed room area as a floor void", () => {
    const gablePlan = {
      datums: { x: { west: 0, east: 18, room: 5 }, y: { north: 0, south: 20 } },
      masses: { house: { levels: ["L2"], rects: [{ id: "gable", x: ["west", "east"], y: ["north", "south"] }] } },
      structural: { systems: [{ id: "gable-floor", level: "L2", kind: "floor", source_mass: "gable", spaces: ["named"], direction: "x" }] },
      levels: { L2: { spaces: { named: { x: ["room", "east"], y: ["north", "south"] } } } }
    };
    const system = compileStructuralSystem(gablePlan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "gable-floor" });
    expect(system?.members.every((member) => member.lengthFt === 18)).toBe(true);
  });

  it("compiles spine and radial alternatives from the selected framing scheme", () => {
    const schemePlan = {
      datums: { x: { west: 0, east: 18 }, y: { north: 0, south: 20 } },
      masses: { house: { levels: ["L2"], rects: [{ id: "gable", x: ["west", "east"], y: ["north", "south"] }] } },
      structural: {
        systems: [{ id: "gable-floor", level: "L2", kind: "floor", source_mass: "gable", direction: "x" }],
        scheme_sets: { gable: { schemes: {
          spine: { name: "Spine", framing_family: "solid_sawn_or_engineered_wood", joist_direction: "x", structural_core: { center: [9, 10], size: [2, 4] }, primary_members: [{ id: "beam", from: [9, 0], to: [9, 20] }] },
          radial: { name: "Radial", framing_family: "solid_sawn_or_engineered_wood", joist_regions: null, primary_members: [{ id: "a", from: [9, 10], to: [0, 0] }, { id: "b", from: [9, 10], to: [18, 0] }, { id: "c", from: [9, 10], to: [0, 20] }, { id: "d", from: [9, 10], to: [18, 20] }] }
        } } }
      }, levels: { L2: { spaces: {} } }
    };
    const spine = compileStructuralSystem(schemePlan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "gable-floor", schemeId: "spine" });
    expect(Math.max(...(spine?.members.map((member) => member.lengthFt) ?? []))).toBe(9);
    expect(spine?.coreRect).toEqual({ x: 8, y: 8, width: 2, height: 4 });
    const radial = compileStructuralSystem(schemePlan, { ...DEFAULT_STRUCTURAL_INPUTS, systemId: "gable-floor", schemeId: "radial" });
    expect(radial?.primaryMembers).toHaveLength(4);
    expect(radial?.members).toHaveLength(0);
  });
});
