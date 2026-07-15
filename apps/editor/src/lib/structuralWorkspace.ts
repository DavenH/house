import type { AnyRecord } from "./types";
import { resolveSpaceRect } from "./geometry";

export type StructuralPreset = "framing" | "loads" | "performance";
export type StructuralInputs = {
  level: string;
  systemId: string;
  schemeId: string;
  spacingIn: number | null;
  nominalDepthIn: number | null;
  actualWidthIn: number | null;
  modulusPsi: number | null;
  bendingPsi: number | null;
  shearPsi: number | null;
  deadLoadPsf: number | null;
  liveLoadPsf: number | null;
  deflectionLimit: number | null;
  unitCost: number | null;
  regionalCostMultiplier: number | null;
  wastePercent: number | null;
  steelCostPerFt: number | null;
  engineeredProductId: string;
  primaryMaterial: "steel" | "lvl";
  primarySection: string;
  lvlPlyCount: number | null;
};

export type StructuralMember = { id: string; mark: string; x1: number; y1: number; x2: number; y2: number; lengthFt: number };
export type PrimaryMember = { id: string; x1: number; y1: number; x2: number; y2: number; family: string | null; section: string | null };
export type StructuralSystem = {
  id: string; level: string; name: string; status: string; source: string;
  authored: boolean;
  kind: "floor" | "stair_opening";
  supports: { west: string; east: string };
  zoneRects: Array<{ left: number; top: number; right: number; bottom: number }>;
  voidRects: Array<{ left: number; top: number; right: number; bottom: number }>;
  schemeId: string;
  schemeName: string;
  framingFamily: string;
  primaryMembers: PrimaryMember[];
  coreRect: { x: number; y: number; width: number; height: number } | null;
  bounds: { x: number; y: number; width: number; height: number };
  direction: "x" | "y"; members: StructuralMember[]; spacingIn: number | null;
  governingFeatureLoadLb: number;
  missing: string[];
};
export type StructuralResult = {
  lineLoadPlf: number; pointLoadLb: number; maxMomentLbFt: number; maxShearLb: number; deflectionIn: number;
  bendingUtilization: number; shearUtilization: number; deflectionUtilization: number; governing: string;
} | null;
export type JoistCandidate = { depthIn: number; label: string; result: StructuralResult; passes: boolean };
export type AuthoredFeatureLoad = { id: string; label: string; massLb: number; x: number; y: number };

export const DEFAULT_STRUCTURAL_INPUTS: StructuralInputs = {
  level: "L2", systemId: "right-gable-floor", schemeId: "clear_span_solid_sawn", spacingIn: 16,
  nominalDepthIn: null, actualWidthIn: 1.5, modulusPsi: 1_400_000, bendingPsi: 875, shearPsi: 135,
  deadLoadPsf: 10, liveLoadPsf: 40, deflectionLimit: 360, unitCost: null, regionalCostMultiplier: 1, wastePercent: 10,
  steelCostPerFt: null, engineeredProductId: "", primaryMaterial: "steel", primarySection: "", lvlPlyCount: null
};

export type LumberPrice = { depthIn: number; lengthFt: number; priceCad: number; grade: string };
export const CANADIAN_LUMBER_PRICES: LumberPrice[] = [
  { depthIn: 8, lengthFt: 8, priceCad: 21.84, grade: "Premium 2 or better" },
  { depthIn: 8, lengthFt: 10, priceCad: 27.31, grade: "Premium 2 or better" },
  { depthIn: 8, lengthFt: 12, priceCad: 31.58, grade: "Premium 2 or better" },
  { depthIn: 8, lengthFt: 16, priceCad: 39.75, grade: "Premium 2 or better" },
  { depthIn: 10, lengthFt: 8, priceCad: 26.80, grade: "Premium 2 or better" },
  { depthIn: 10, lengthFt: 10, priceCad: 33.45, grade: "Premium 2 or better" },
  { depthIn: 10, lengthFt: 12, priceCad: 40.34, grade: "Premium 2 or better" },
  { depthIn: 10, lengthFt: 16, priceCad: 49.84, grade: "Premium 2 or better" },
  { depthIn: 12, lengthFt: 12, priceCad: 54.44, grade: "Premium 2 or better" },
  { depthIn: 12, lengthFt: 16, priceCad: 72.98, grade: "Premium 2 or better" }
];
export type EngineeredJoistPrice = { id: string; product: string; depthIn: number; lengthFt: number; priceCad: number };
export const CANADIAN_ENGINEERED_JOIST_PRICES: EngineeredJoistPrice[] = [
  { id: "pji40-9.5", product: "PJI40", depthIn: 9.5, lengthFt: 14, priceCad: 41.03 },
  { id: "pji40-9.5", product: "PJI40", depthIn: 9.5, lengthFt: 16, priceCad: 46.91 },
  { id: "pji40-9.5", product: "PJI40", depthIn: 9.5, lengthFt: 20, priceCad: 58.62 },
  { id: "pji40-9.5", product: "PJI40", depthIn: 9.5, lengthFt: 24, priceCad: 70.34 },
  { id: "pji210-11.875", product: "PJI40 / TJI210", depthIn: 11.875, lengthFt: 18, priceCad: 57.93 },
  { id: "pji210-11.875", product: "PJI40 / TJI210", depthIn: 11.875, lengthFt: 20, priceCad: 64.37 },
  { id: "pji360-11.875", product: "PJI80 / TJI360", depthIn: 11.875, lengthFt: 20, priceCad: 84.55 },
  { id: "pji360-11.875", product: "PJI80 / TJI360", depthIn: 11.875, lengthFt: 22, priceCad: 92.98 },
  { id: "pji360-11.875", product: "PJI80 / TJI360", depthIn: 11.875, lengthFt: 24, priceCad: 101.45 }
];
export const CANADIAN_LVL_PRICES = [
  { lengthFt: 10, priceCad: 81.95 }, { lengthFt: 14, priceCad: 114.74 }, { lengthFt: 18, priceCad: 147.52 },
  { lengthFt: 20, priceCad: 163.91 }, { lengthFt: 22, priceCad: 180.30 }
];

export const LOAD_PRESET_SOURCE = "Canadian Wood Council residential guidance: 40 psf live, 10 psf dead, L/360";
export const MATERIAL_ASSUMPTION_SOURCE = "Project material properties";
export const SOLID_SAWN_CANDIDATES = [
  { depthIn: 7.25, label: "7¼ in" }, { depthIn: 9.25, label: "9¼ in" },
  { depthIn: 11.25, label: "11¼ in" }, { depthIn: 13.25, label: "13¼ in" },
  { depthIn: 15.25, label: "15¼ in" }
];

export function compileStructuralSystem(data: AnyRecord, input: StructuralInputs): StructuralSystem | null {
  const authored = availableStructuralSystems(data).find((item) => String(item.id) === input.systemId) ?? availableStructuralSystems(data)[0];
  if (!authored) return null;
  const level = String(authored.level ?? input.level);
  const scheme = schemeForSystem(data, authored, input.schemeId);
  const spaces = Array.isArray(authored.spaces) ? authored.spaces.map(String) : [];
  const massBounds = authored.source_mass ? findMassBounds(data, level, String(authored.source_mass)) : null;
  const rects = (massBounds ? [massBounds] : spaces.map((id) => resolveSpaceRect(data, level, id)).filter(Boolean)) as Array<{ left: number; top: number; right: number; bottom: number; width: number; height: number }>;
  if (authored.bounds) rects.push(authored.bounds as { left: number; top: number; right: number; bottom: number; width: number; height: number });
  const voidRects = (Array.isArray(authored.void_spaces) ? authored.void_spaces.map(String) : []).map((id) => resolveSpaceRect(data, level, id)).filter(Boolean) as Array<{ left: number; top: number; right: number; bottom: number }>;
  if (!rects.length) return null;
  const x = Math.min(...rects.map((r) => r.left));
  const y = Math.min(...rects.map((r) => r.top));
  const right = Math.max(...rects.map((r) => r.right));
  const bottom = Math.max(...rects.map((r) => r.bottom));
  const direction = (scheme?.joist_direction ?? authored.direction) === "y" ? "y" : "x";
  const kind = authored.kind === "stair_opening" ? "stair_opening" : "floor";
  const framingFamily = String(scheme?.framing_family ?? "solid_sawn");
  const primaryMembers = primaryMembersFromScheme(scheme);
  const coreRect = coreRectFromScheme(scheme);
  const splitLines = scheme?.primary_members ? primaryMembers.filter((member) => direction === "x" ? Math.abs(member.x1 - member.x2) < 1e-6 : Math.abs(member.y1 - member.y2) < 1e-6).map((member) => direction === "x" ? member.x1 : member.y1) : [];
  const generateJoists = !scheme || scheme.joist_regions !== null;
  const isAuthored = authored.authored !== false;
  const spacingIn = positive(input.spacingIn);
  const members: StructuralMember[] = [];
  if (isAuthored && kind === "floor" && spacingIn && generateJoists) {
    const crossLength = direction === "x" ? bottom - y : right - x;
    const count = Math.floor(crossLength * 12 / spacingIn) + 1;
    for (let index = 0; index < count; index += 1) {
      const cross = Math.min(crossLength, index * spacingIn / 12);
      const coordinate = direction === "x" ? y + cross : x + cross;
      const intervals = splitFramingIntervals(framingIntervals(rects, voidRects, direction, coordinate), splitLines);
      for (const [segment, interval] of intervals.entries()) {
        members.push(direction === "x"
          ? { id: `joist-${index + 1}-${segment + 1}`, mark: "FJ-1", x1: interval[0], y1: coordinate, x2: interval[1], y2: coordinate, lengthFt: interval[1] - interval[0] }
          : { id: `joist-${index + 1}-${segment + 1}`, mark: "FJ-1", x1: coordinate, y1: interval[0], x2: coordinate, y2: interval[1], lengthFt: interval[1] - interval[0] });
      }
    }
    const lastCross = direction === "x" ? members[members.length - 1]?.y1 : members[members.length - 1]?.x1;
    const finalCross = direction === "x" ? bottom : right;
    if (lastCross !== undefined && lastCross < finalCross - 1e-6) {
      for (const [segment, interval] of splitFramingIntervals(framingIntervals(rects, voidRects, direction, finalCross), splitLines).entries()) {
        members.push(direction === "x"
          ? { id: `joist-final-${segment + 1}`, mark: "FJ-1", x1: interval[0], y1: finalCross, x2: interval[1], y2: finalCross, lengthFt: interval[1] - interval[0] }
          : { id: `joist-final-${segment + 1}`, mark: "FJ-1", x1: finalCross, y1: interval[0], x2: finalCross, y2: interval[1], lengthFt: interval[1] - interval[0] });
      }
    }
  }
  const missing: string[] = [];
  if (!isAuthored) {
    missing.push("Framing direction", "Supports", "Member family", "Openings and connections");
  } else {
    if (!spacingIn) missing.push("Joist spacing");
    if (!positive(input.nominalDepthIn) || !positive(input.actualWidthIn)) missing.push("Member section");
    if (!positive(input.modulusPsi) || !positive(input.bendingPsi) || !positive(input.shearPsi)) missing.push("Material design properties");
    if (!positive(input.deadLoadPsf) || !positive(input.liveLoadPsf)) missing.push("Floor loads");
    if (!positive(input.deflectionLimit)) missing.push("Deflection limit");
  }
  const governingFeatureLoadLb = governingFeatureLoad(data, level, { x, y, width: right - x, height: bottom - y }, direction, members);
  const supports = (authored.supports ?? {}) as AnyRecord;
  return { id: String(authored.id), level, name: String(authored.name ?? authored.id), status: String(authored.status ?? "concept"), source: authored.authored === false ? `Plan mass: ${authored.source_mass}` : `Plan: structural.systems.${authored.id}`, authored: authored.authored !== false, kind, supports: { west: String(supports.west?.kind ?? supports.north?.kind ?? "unresolved"), east: String(supports.east?.kind ?? supports.south?.kind ?? "unresolved") }, zoneRects: rects.map((rect) => ({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom })), voidRects: voidRects.map((rect) => ({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom })), schemeId: String(scheme?.id ?? "default"), schemeName: String(scheme?.name ?? "Default framing"), framingFamily, primaryMembers, coreRect, bounds: { x, y, width: right - x, height: bottom - y }, direction, members, spacingIn, governingFeatureLoadLb, missing };
}

export function calculateJoist(system: StructuralSystem | null, input: StructuralInputs): StructuralResult {
  if (!system || system.kind !== "floor" || system.framingFamily !== "solid_sawn" && system.framingFamily !== "solid_sawn_or_engineered_wood" || !system.spacingIn || !positive(input.nominalDepthIn) || !positive(input.actualWidthIn) || !positive(input.modulusPsi) || !positive(input.bendingPsi) || !positive(input.shearPsi) || !positive(input.deadLoadPsf) || !positive(input.liveLoadPsf) || !positive(input.deflectionLimit)) return null;
  const spanFt = Math.max(0, ...system.members.map((member) => member.lengthFt));
  if (!spanFt) return null;
  const spacingFt = system.spacingIn / 12;
  const lineLoadPlf = (input.deadLoadPsf! + input.liveLoadPsf!) * spacingFt;
  const pointLoadLb = system.governingFeatureLoadLb;
  const maxMomentLbFt = lineLoadPlf * spanFt ** 2 / 8 + pointLoadLb * spanFt / 4;
  const maxShearLb = lineLoadPlf * spanFt / 2 + pointLoadLb / 2;
  const b = input.actualWidthIn!, d = input.nominalDepthIn!;
  const sectionModulus = b * d ** 2 / 6;
  const inertia = b * d ** 3 / 12;
  const bendingUtilization = maxMomentLbFt * 12 / (input.bendingPsi! * sectionModulus);
  const shearStress = 1.5 * maxShearLb / (b * d);
  const shearUtilization = shearStress / input.shearPsi!;
  const w = lineLoadPlf / 12, lengthIn = spanFt * 12;
  const deflectionIn = 5 * w * lengthIn ** 4 / (384 * input.modulusPsi! * inertia) + pointLoadLb * lengthIn ** 3 / (48 * input.modulusPsi! * inertia);
  const deflectionUtilization = deflectionIn / (lengthIn / input.deflectionLimit!);
  const checks: Array<[string, number]> = [["Bending", bendingUtilization], ["Shear", shearUtilization], ["Deflection", deflectionUtilization]];
  const governing = checks.sort((a, b) => b[1] - a[1])[0][0];
  return { lineLoadPlf, pointLoadLb, maxMomentLbFt, maxShearLb, deflectionIn, bendingUtilization, shearUtilization, deflectionUtilization, governing };
}

export function sizeJoistCandidates(system: StructuralSystem | null, input: StructuralInputs): JoistCandidate[] {
  return SOLID_SAWN_CANDIDATES.map((candidate) => {
    const result = calculateJoist(system, { ...input, nominalDepthIn: candidate.depthIn });
    const passes = Boolean(result && result.bendingUtilization <= 1 && result.shearUtilization <= 1 && result.deflectionUtilization <= 1);
    return { ...candidate, result, passes };
  });
}

export function structuralMaterialSubtotal(system: StructuralSystem | null, input: StructuralInputs) {
  if (!system?.members.length || !positive(input.regionalCostMultiplier) || input.wastePercent === null || input.wastePercent < 0) return null;
  let purchases: Array<{ priceCad: number } | undefined>;
  if (system.framingFamily === "engineered_wood_i_joist") {
    if (!input.engineeredProductId) return null;
    const catalog = CANADIAN_ENGINEERED_JOIST_PRICES.filter((item) => item.id === input.engineeredProductId).sort((a, b) => a.lengthFt - b.lengthFt);
    purchases = system.members.map((member) => catalog.find((item) => item.lengthFt >= member.lengthFt));
  } else {
    if (!positive(input.nominalDepthIn)) return null;
    const nominalDepth = [8, 10, 12].find((depth) => Math.abs(depth - input.nominalDepthIn!) <= 1) ?? input.nominalDepthIn!;
    const catalog = CANADIAN_LUMBER_PRICES.filter((item) => item.depthIn === nominalDepth).sort((a, b) => a.lengthFt - b.lengthFt);
    purchases = system.members.map((member) => catalog.find((item) => item.lengthFt >= member.lengthFt));
  }
  if (purchases.some((item) => !item)) return null;
  const multiplier = input.regionalCostMultiplier!;
  const lumber = purchases.reduce((sum, item) => sum + item!.priceCad, 0) * multiplier * (1 + input.wastePercent / 100);
  const primaryLengthFt = system.primaryMembers.reduce((sum, member) => sum + Math.hypot(member.x2 - member.x1, member.y2 - member.y1), 0);
  let primary = 0;
  if (primaryLengthFt && input.primaryMaterial === "steel") {
    if (!input.primarySection.trim() || !positive(input.steelCostPerFt)) return null;
    primary = primaryLengthFt * input.steelCostPerFt! * multiplier;
  } else if (primaryLengthFt) {
    if (!positive(input.lvlPlyCount)) return null;
    const stock = [...CANADIAN_LVL_PRICES].sort((a, b) => a.lengthFt - b.lengthFt);
    const beams = system.primaryMembers.map((member) => stock.find((item) => item.lengthFt >= Math.hypot(member.x2 - member.x1, member.y2 - member.y1)));
    if (beams.some((item) => !item)) return null;
    primary = beams.reduce((sum, item) => sum + item!.priceCad, 0) * input.lvlPlyCount! * multiplier;
  }
  return { boardFeet: input.actualWidthIn && input.nominalDepthIn ? input.actualWidthIn * input.nominalDepthIn * system.members.reduce((sum, member) => sum + member.lengthFt, 0) / 12 : 0, lumber, primary, primaryLengthFt, total: lumber + primary };
}

export function authoredFeatureLoads(data: AnyRecord, system: StructuralSystem | null): AuthoredFeatureLoad[] {
  if (!system) return [];
  const features = (((data.levels as AnyRecord | undefined)?.[system.level] as AnyRecord | undefined)?.features ?? {}) as AnyRecord;
  const loads: AuthoredFeatureLoad[] = [];
  for (const [id, raw] of Object.entries(features)) {
    const feature = raw as AnyRecord;
    const massLb = Number(feature.structural_mass_lb);
    const at = Array.isArray(feature.at) ? feature.at : null;
    if (!Number.isFinite(massLb) || massLb <= 0 || !at) continue;
    const x = Number(at[0]), y = Number(at[1]);
    const b = system.bounds;
    if (x < b.x || x > b.x + b.width || y < b.y || y > b.y + b.height) continue;
    loads.push({ id, label: String(feature.label || id), massLb, x, y });
  }
  return loads;
}

function governingFeatureLoad(data: AnyRecord, level: string, bounds: StructuralSystem["bounds"], direction: "x" | "y", members: StructuralMember[]) {
  if (!members.length) return 0;
  const features = (((data.levels as AnyRecord | undefined)?.[level] as AnyRecord | undefined)?.features ?? {}) as AnyRecord;
  const loads = new Array(members.length).fill(0) as number[];
  for (const raw of Object.values(features)) {
    const feature = raw as AnyRecord;
    const mass = Number(feature.structural_mass_lb);
    if (!Number.isFinite(mass) || mass <= 0 || !Array.isArray(feature.at)) continue;
    const at = feature.at.map(Number), size = Array.isArray(feature.size) ? feature.size.map(Number) : [0, 0];
    const extent = direction === "x" ? size[1] : size[0];
    const start = (direction === "x" ? at[1] : at[0]) - extent / 2;
    const end = start + extent;
    const intersecting = members.map((member, index) => ({ index, cross: direction === "x" ? member.y1 : member.x1 })).filter(({ cross }) => cross >= start && cross <= end);
    const receivers = intersecting.length ? intersecting : members.map((member, index) => ({ index, cross: direction === "x" ? member.y1 : member.x1 })).sort((a, b) => Math.abs(a.cross - start) - Math.abs(b.cross - start)).slice(0, 1);
    for (const receiver of receivers) loads[receiver.index] += mass / receivers.length;
  }
  return Math.max(0, ...loads);
}

export function structuralSystems(data: AnyRecord): AnyRecord[] {
  const structural = (data.structural ?? {}) as AnyRecord;
  return Array.isArray(structural.systems) ? structural.systems as AnyRecord[] : [];
}

export function availableStructuralSystems(data: AnyRecord): AnyRecord[] {
  const authored: AnyRecord[] = structuralSystems(data).map((system) => ({ ...system, authored: true }));
  const claimed = new Set(authored.map((system) => `${system.level}:${system.source_mass ?? ""}`));
  const levels = Object.keys((data.levels as AnyRecord | undefined) ?? {});
  const masses = (data.masses ?? {}) as AnyRecord;
  const discovered: AnyRecord[] = [];
  for (const [massId, rawMass] of Object.entries(masses)) {
    const mass = rawMass as AnyRecord;
    const specs = Array.isArray(mass.rects) ? mass.rects : mass.rect ? [mass.rect] : [];
    for (const [index, rawSpec] of specs.entries()) {
      const spec = rawSpec as AnyRecord;
      const massLevels = Array.isArray(spec.levels) ? spec.levels : Array.isArray(mass.levels) ? mass.levels : levels;
      for (const level of massLevels.map(String)) {
        const id = String(spec.id ?? `${massId}-${index + 1}`);
        if (claimed.has(`${level}:${id}`)) continue;
        const bounds = rectSpecBounds(data, level, spec);
        if (!bounds) continue;
        discovered.push({ id: `unresolved:${level}:${id}`, name: `${humanize(id)} floor`, level, status: "unresolved", authored: false, bounds, direction: "x", source_mass: id });
      }
    }
  }
  return [...authored, ...discovered];
}

export function availableStructuralSchemes(data: AnyRecord, systemId: string) {
  const system = structuralSystems(data).find((item) => String(item.id) === systemId);
  if (!system?.source_mass) return [];
  const set = ((((data.structural ?? {}) as AnyRecord).scheme_sets ?? {}) as AnyRecord)[String(system.source_mass)] as AnyRecord | undefined;
  const schemes = (set?.schemes ?? {}) as AnyRecord;
  return Object.entries(schemes).map(([id, raw]) => ({ id, name: String((raw as AnyRecord).name ?? humanize(id)), status: String((raw as AnyRecord).status ?? "concept") }));
}

function schemeForSystem(data: AnyRecord, system: AnyRecord, schemeId: string) {
  if (!system.source_mass) return null;
  const set = ((((data.structural ?? {}) as AnyRecord).scheme_sets ?? {}) as AnyRecord)[String(system.source_mass)] as AnyRecord | undefined;
  const schemes = (set?.schemes ?? {}) as AnyRecord;
  const raw = schemes[schemeId] as AnyRecord | undefined;
  return raw ? { ...raw, id: schemeId } as AnyRecord : null;
}

function primaryMembersFromScheme(scheme: AnyRecord | null): PrimaryMember[] {
  if (!scheme || !Array.isArray(scheme.primary_members)) return [];
  const members: PrimaryMember[] = [];
  for (const raw of scheme.primary_members as AnyRecord[]) {
    if (!Array.isArray(raw.from) || !Array.isArray(raw.to)) continue;
    members.push({ id: String(raw.id), x1: Number(raw.from[0]), y1: Number(raw.from[1]), x2: Number(raw.to[0]), y2: Number(raw.to[1]), family: raw.family == null ? null : String(raw.family), section: raw.section == null ? null : String(raw.section) });
  }
  return members;
}
function coreRectFromScheme(scheme: AnyRecord | null) {
  const core = scheme?.structural_core as AnyRecord | undefined;
  if (!core || !Array.isArray(core.size)) return null;
  const width = Number(core.size[0]), height = Number(core.size[1]);
  if (Array.isArray(core.center)) return { x: Number(core.center[0]) - width / 2, y: Number(core.center[1]) - height / 2, width, height };
  if (Array.isArray(core.at)) return { x: Number(core.at[0]), y: Number(core.at[1]), width, height };
  return null;
}

function rectSpecBounds(data: AnyRecord, level: string, spec: AnyRecord) {
  if (!Array.isArray(spec.x) || !Array.isArray(spec.y)) return null;
  const global = (data.datums ?? {}) as AnyRecord;
  const local = ((((data.levels as AnyRecord | undefined)?.[level] as AnyRecord | undefined)?.datums ?? {}) as AnyRecord);
  const value = (raw: unknown, axis: "x" | "y") => typeof raw === "number" ? raw : Number((local[axis] ?? {})[String(raw)] ?? (global[axis] ?? {})[String(raw)]);
  const x1 = value(spec.x[0], "x"), x2 = value(spec.x[1], "x"), y1 = value(spec.y[0], "y"), y2 = value(spec.y[1], "y");
  if (![x1, x2, y1, y2].every(Number.isFinite)) return null;
  const left = Math.min(x1, x2), right = Math.max(x1, x2), top = Math.min(y1, y2), bottom = Math.max(y1, y2);
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}
function findMassBounds(data: AnyRecord, level: string, rectId: string) {
  const masses = (data.masses ?? {}) as AnyRecord;
  for (const rawMass of Object.values(masses)) {
    const mass = rawMass as AnyRecord;
    const specs = Array.isArray(mass.rects) ? mass.rects : mass.rect ? [mass.rect] : [];
    for (const rawSpec of specs) {
      const spec = rawSpec as AnyRecord;
      if (String(spec.id ?? "") !== rectId) continue;
      const specLevels = Array.isArray(spec.levels) ? spec.levels : Array.isArray(mass.levels) ? mass.levels : null;
      if (specLevels && !specLevels.map(String).includes(level)) continue;
      return rectSpecBounds(data, level, spec);
    }
  }
  return null;
}
function humanize(value: string) { return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function framingIntervals(rects: Array<{ left: number; top: number; right: number; bottom: number }>, voidRects: Array<{ left: number; top: number; right: number; bottom: number }>, direction: "x" | "y", coordinate: number): Array<[number, number]> {
  const intervals = rects
    .filter((rect) => direction === "x" ? coordinate >= rect.top - 1e-6 && coordinate <= rect.bottom + 1e-6 : coordinate >= rect.left - 1e-6 && coordinate <= rect.right + 1e-6)
    .map((rect): [number, number] => direction === "x" ? [rect.left, rect.right] : [rect.top, rect.bottom])
    .sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const interval of intervals) {
    const last = merged[merged.length - 1];
    if (!last || interval[0] > last[1] + 1e-6) merged.push([...interval]);
    else last[1] = Math.max(last[1], interval[1]);
  }
  const cuts = voidRects
    .filter((rect) => direction === "x" ? coordinate > rect.top + 1e-6 && coordinate < rect.bottom - 1e-6 : coordinate > rect.left + 1e-6 && coordinate < rect.right - 1e-6)
    .map((rect): [number, number] => direction === "x" ? [rect.left, rect.right] : [rect.top, rect.bottom]);
  let result = merged;
  for (const cut of cuts) {
    const next: Array<[number, number]> = [];
    for (const segment of result) next.push(...subtractInterval(segment, cut));
    result = next;
  }
  return result;
}
function subtractInterval(segment: [number, number], cut: [number, number]): Array<[number, number]> {
  if (cut[1] <= segment[0] || cut[0] >= segment[1]) return [segment];
  const result: Array<[number, number]> = [];
  if (cut[0] > segment[0]) result.push([segment[0], Math.min(cut[0], segment[1])]);
  if (cut[1] < segment[1]) result.push([Math.max(cut[1], segment[0]), segment[1]]);
  return result.filter(([start, end]) => end - start > 1e-6);
}
function splitFramingIntervals(intervals: Array<[number, number]>, splitLines: number[]) {
  let result = intervals;
  for (const split of splitLines) {
    const next: Array<[number, number]> = [];
    for (const interval of result) {
      if (split > interval[0] + 1e-6 && split < interval[1] - 1e-6) next.push([interval[0], split], [split, interval[1]]);
      else next.push(interval);
    }
    result = next;
  }
  return result;
}
function positive(value: number | null) { return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null; }

export function feetInches(feet: number) {
  let inches = Math.round(feet * 12); const sign = inches < 0 ? "−" : ""; inches = Math.abs(inches);
  return `${sign}${Math.floor(inches / 12)}'-${inches % 12}\"`;
}
