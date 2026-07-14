import type { AnyRecord, SpaceRect } from "./types";
import { resolveSpaceRect } from "./geometry";

export type CostAssumptions = {
  exteriorWallHeightFt: number;
  interiorWallHeightFt: number;
  defaultOpeningHeightFt: number;
  defaultWindowHeightFt: number;
  defaultDoorHeightFt: number;
  slabThicknessIn: number;
  footingWidthFt: number;
  footingDepthIn: number;
  padWallMarginFt: number;
  padInsulationMarginFt: number;
  padInsulationRMin: number;
  padInsulationRMax: number;
  footingCenterOffsetFt: number;
  padRebarSpacingFt: number;
  padRebarEdgeCoverIn: number;
  footingRebarRuns: number;
  roofWastePercent: number;
  flooringWastePercent: number;
  defaultPexPerWetSpaceFt: number;
  defaultRoofPitchRise: number;
  defaultRoofPitchRun: number;
};

export type MaterialCost = {
  id: string;
  label: string;
  unit: string;
  unitCost: number;
};

export type QuantityEstimate = {
  id: string;
  group: "pad" | "walls" | "framing" | "interior" | "roof" | "services";
  label: string;
  materialId: string;
  quantity: number;
  unit: string;
  notes: string;
  breakdown?: string[];
};

export type CostEstimate = {
  assumptions: CostAssumptions;
  materials: MaterialCost[];
  quantities: QuantityEstimate[];
  summary: Array<{ label: string; value: number; unit: string }>;
  total: number;
};

type Rect = SpaceRect;
type Segment = { orientation: "horizontal" | "vertical"; fixed: number; start: number; end: number };
type Side = "north" | "east" | "south" | "west";
type RoofMass = {
  id: string;
  rect: Rect;
  roof: AnyRecord;
  pitch: number;
  eaveHeight: number;
  eaveMargin: number;
  eaveSides: Side[];
  ridge: "x" | "y";
  start: "open" | "hip";
  end: "open" | "hip";
};

const SIDES: Side[] = ["north", "east", "south", "west"];

export const DEFAULT_COST_ASSUMPTIONS: CostAssumptions = {
  exteriorWallHeightFt: 10,
  interiorWallHeightFt: 9,
  defaultOpeningHeightFt: 7,
  defaultWindowHeightFt: 4,
  defaultDoorHeightFt: 7,
  slabThicknessIn: 4,
  footingWidthFt: 2,
  footingDepthIn: 12,
  padWallMarginFt: 1,
  padInsulationMarginFt: 4,
  padInsulationRMin: 15,
  padInsulationRMax: 20,
  footingCenterOffsetFt: 0.5,
  padRebarSpacingFt: 2,
  padRebarEdgeCoverIn: 2,
  footingRebarRuns: 2,
  roofWastePercent: 10,
  flooringWastePercent: 8,
  defaultPexPerWetSpaceFt: 60,
  defaultRoofPitchRise: 8,
  defaultRoofPitchRun: 12
};

export const DEFAULT_MATERIAL_COSTS: MaterialCost[] = [
  { id: "concrete", label: "Concrete", unit: "yd3", unitCost: 220 },
  { id: "pad_insulation", label: "Pad insulation", unit: "sq ft", unitCost: 3.5 },
  { id: "rebar", label: "Rebar", unit: "ft", unitCost: 0.85 },
  { id: "roofing", label: "Roofing assembly", unit: "sq ft", unitCost: 4.5 },
  { id: "interior_framing", label: "Interior framing lumber", unit: "sq ft wall", unitCost: 2.25 },
  { id: "interior_drywall", label: "Interior wall board", unit: "sq ft face", unitCost: 1.15 },
  { id: "icf_block", label: "ICF blocks", unit: "block", unitCost: 28 },
  { id: "exterior_cladding", label: "Exterior cladding", unit: "sq ft", unitCost: 16 },
  { id: "windows", label: "Windows", unit: "sq ft", unitCost: 70 },
  { id: "exterior_doors", label: "Exterior doors", unit: "each", unitCost: 1800 },
  { id: "interior_doors", label: "Interior doors", unit: "each", unitCost: 350 },
  { id: "flooring", label: "Flooring", unit: "sq ft", unitCost: 8 },
  { id: "pex_pipe", label: "PEX pipe", unit: "ft", unitCost: 0.8 }
];

export function materialCostsFromPlan(
  data: AnyRecord,
  fallback: MaterialCost[] = DEFAULT_MATERIAL_COSTS
): MaterialCost[] {
  const rawMaterials = ((data.costing as AnyRecord | undefined)?.materials ?? {}) as unknown;
  const fallbackById = new Map(fallback.map((material) => [material.id, material]));
  const materialById = new Map<string, MaterialCost>(fallback.map((material) => [material.id, { ...material }]));
  const materialOrder = fallback.map((material) => material.id);

  if (Array.isArray(rawMaterials)) {
    for (const rawMaterial of rawMaterials) {
      if (!isRecord(rawMaterial)) {
        continue;
      }
      const id = String(rawMaterial.id ?? "");
      if (!id) {
        continue;
      }
      const fallbackMaterial = fallbackById.get(id);
      materialById.set(id, materialFromRecord(id, rawMaterial, fallbackMaterial));
      if (!materialOrder.includes(id)) {
        materialOrder.push(id);
      }
    }
  } else if (isRecord(rawMaterials)) {
    for (const [id, rawMaterial] of Object.entries(rawMaterials)) {
      if (!isRecord(rawMaterial)) {
        continue;
      }
      const fallbackMaterial = fallbackById.get(id);
      materialById.set(id, materialFromRecord(id, rawMaterial, fallbackMaterial));
      if (!materialOrder.includes(id)) {
        materialOrder.push(id);
      }
    }
  }

  return materialOrder.map((id) => materialById.get(id)).filter((material): material is MaterialCost => Boolean(material));
}

export function materialCostsToYaml(materials: MaterialCost[]): AnyRecord {
  const out: AnyRecord = {};
  for (const material of materials) {
    out[material.id] = {
      label: material.label,
      unit: material.unit,
      unit_cost: material.unitCost
    };
  }
  return out;
}

export function estimateCosts(
  data: AnyRecord,
  assumptions: CostAssumptions = DEFAULT_COST_ASSUMPTIONS,
  materials: MaterialCost[] = materialCostsFromPlan(data)
): CostEstimate {
  const firstLevelId = Object.keys((data.levels as AnyRecord | undefined) ?? {})[0] ?? "L1";
  const sourceLevelId = foundationSourceLevel(data) ?? firstLevelId;
  const sourceRects = foundationSourceRects(data, sourceLevelId);
  const padMargin = foundationNumber(data, "pad_wall_margin", assumptions.padWallMarginFt);
  const footingOffset = foundationNumber(data, "footing_center_offset", assumptions.footingCenterOffsetFt);
  const footingWidth = foundationNumber(data, "footing_width", assumptions.footingWidthFt);
  const insulationMargin = foundationNumber(data, "insulation_margin", assumptions.padInsulationMarginFt);
  const rebarSpacing = foundationNumber(data, "pad_rebar_spacing", assumptions.padRebarSpacingFt);
  const rebarCover = foundationNumber(data, "pad_rebar_edge_cover", assumptions.padRebarEdgeCoverIn / 12);
  const padRects = sourceRects.map((rect) => expandRect(rect, padMargin));
  const insulationRects = sourceRects.map((rect) => expandRect(rect, insulationMargin));
  const footingRects = sourceRects.map((rect) => expandRect(rect, footingOffset));
  const foundationPadArea = unionArea(padRects);
  const padInsulationArea = unionArea(insulationRects);
  const padInsulationApronArea = Math.max(0, padInsulationArea - foundationPadArea);
  const footingLength = boundarySegments(footingRects).reduce((total, segment) => total + segment.end - segment.start, 0);
  const padRebarLength = scanlineLength(padRects, rebarSpacing, rebarCover);
  const footingRebarLength = footingLength * assumptions.footingRebarRuns;
  const interior = interiorWallStats(data, assumptions);
  const exteriorAssembly = exteriorWallAssemblyConfig(data, assumptions);
  const exterior = exteriorWallStats(data, assumptions);
  const icfBlockArea = exteriorAssembly.icf.blockLengthFt * exteriorAssembly.icf.blockHeightFt;
  const icfBlockCount = icfBlockArea > 0 ? Math.ceil((exterior.netArea / icfBlockArea) * (1 + exteriorAssembly.icf.wastePercent / 100)) : 0;
  const icfCoreConcreteYd3 = exterior.netArea * (exteriorAssembly.icf.concreteThicknessIn / 12) / 27;
  const claddingArea = exterior.netArea * (1 + exteriorAssembly.cladding.wastePercent / 100);
  const flooringArea = floorAreaEstimate(data) * (1 + assumptions.flooringWastePercent / 100);
  const pexLength = plumbingPexLength(data, assumptions);
  const roof = roofStats(data, assumptions);
  const roofArea = roof.areaWithWaste;
  const concreteVolumeYd3 =
    (foundationPadArea * (assumptions.slabThicknessIn / 12) + footingLength * footingWidth * (assumptions.footingDepthIn / 12)) / 27;

  const quantities: QuantityEstimate[] = [
    {
      id: "concrete_pad_and_footings",
      group: "pad",
      label: "Concrete pad + footings",
      materialId: "concrete",
      quantity: concreteVolumeYd3,
      unit: "yd3",
      notes: `${formatNumber(foundationPadArea)} sq ft slab, ${formatNumber(footingLength)} ft footing`,
      breakdown: [
        `Slab volume: ${formatNumber(foundationPadArea)} sq ft x ${formatNumber(assumptions.slabThicknessIn)} in / 12`,
        `Footing volume: ${formatNumber(footingLength)} ft x ${formatNumber(footingWidth)} ft x ${formatNumber(assumptions.footingDepthIn)} in / 12`,
        "Total converted from cubic feet to cubic yards"
      ]
    },
    {
      id: "pad_insulation",
      group: "pad",
      label: "Pad insulation",
      materialId: "pad_insulation",
      quantity: padInsulationArea,
      unit: "sq ft",
      notes: `Under-slab plus ${formatNumber(insulationMargin)} ft perimeter apron, R${formatNumber(assumptions.padInsulationRMin)}-R${formatNumber(assumptions.padInsulationRMax)}`,
      breakdown: [
        `Under-slab insulation covers the ${formatNumber(foundationPadArea)} sq ft concrete pad footprint`,
        `Source mass union expanded by ${formatNumber(insulationMargin)} ft`,
        `Perimeter apron beyond pad: ${formatNumber(padInsulationApronArea)} sq ft`,
        `Total insulation board area: ${formatNumber(foundationPadArea)} sq ft under slab + ${formatNumber(padInsulationApronArea)} sq ft apron`
      ]
    },
    {
      id: "pad_and_footing_rebar",
      group: "pad",
      label: "Pad grid + footing rebar",
      materialId: "rebar",
      quantity: padRebarLength + footingRebarLength,
      unit: "ft",
      notes: `${formatNumber(padRebarLength)} ft grid, ${formatNumber(footingRebarLength)} ft footing`,
      breakdown: [
        `Pad grid scanlines at ${formatNumber(rebarSpacing)} ft spacing with ${formatNumber(rebarCover * 12)} in edge cover`,
        `Footing rebar: ${formatNumber(footingLength)} ft footing x ${formatNumber(assumptions.footingRebarRuns)} runs`
      ]
    },
    {
      id: "roofing_area",
      group: "roof",
      label: "Roofing material",
      materialId: "roofing",
      quantity: roofArea,
      unit: "sq ft",
      notes: `Visible roof faces, ${assumptions.roofWastePercent}% waste`,
      breakdown: roof.breakdown
    },
    {
      id: "interior_framing",
      group: "framing",
      label: "Interior framing lumber",
      materialId: "interior_framing",
      quantity: interior.netOneSideArea,
      unit: "sq ft wall",
      notes: `${formatNumber(interior.length)} ft derived/explicit interior partitions`,
      breakdown: [
        `One-side gross area: ${formatNumber(interior.length)} ft x ${formatNumber(assumptions.interiorWallHeightFt)} ft`,
        "Interior openings subtract one face from framing quantity"
      ]
    },
    {
      id: "interior_wall_board",
      group: "interior",
      label: "Interior wall board",
      materialId: "interior_drywall",
      quantity: interior.netBothSidesArea,
      unit: "sq ft face",
      notes: "Both faces, openings subtracted",
      breakdown: [
        `Both-side gross area: ${formatNumber(interior.length)} ft x ${formatNumber(assumptions.interiorWallHeightFt)} ft x 2`,
        "Interior openings subtract both wall-board faces"
      ]
    },
    {
      id: "interior_doors",
      group: "interior",
      label: "Interior doors",
      materialId: "interior_doors",
      quantity: interior.doorCount,
      unit: "each",
      notes: `${formatNumber(interior.doorArea)} sq ft interior door openings`,
      breakdown: ["Counted from interior door/opening records"]
    },
    {
      id: "icf_blocks",
      group: "walls",
      label: "ICF blocks",
      materialId: "icf_block",
      quantity: icfBlockCount,
      unit: "block",
      notes: `${formatNumber(exterior.netArea)} sq ft net wall, ${formatNumber(exteriorAssembly.icf.wastePercent)}% waste`,
      breakdown: [
        `Exterior wall net face area: ${formatNumber(exterior.netArea)} sq ft`,
        `ICF block face area: ${formatNumber(exteriorAssembly.icf.blockLengthFt)} ft x ${formatNumber(exteriorAssembly.icf.blockHeightFt)} ft`,
        `${formatNumber(exteriorAssembly.icf.wastePercent)}% waste, rounded up to whole blocks`
      ]
    },
    {
      id: "icf_core_concrete",
      group: "walls",
      label: "ICF core concrete",
      materialId: "concrete",
      quantity: icfCoreConcreteYd3,
      unit: "yd3",
      notes: `${formatNumber(exteriorAssembly.icf.concreteThicknessIn)}" concrete core`,
      breakdown: [
        `${formatNumber(exterior.netArea)} sq ft net exterior wall area x ${formatNumber(exteriorAssembly.icf.concreteThicknessIn)} in / 12`,
        "Converted from cubic feet to cubic yards"
      ]
    },
    {
      id: "exterior_cladding",
      group: "walls",
      label: `${titleCase(exteriorAssembly.cladding.type)} cladding`,
      materialId: "exterior_cladding",
      quantity: claddingArea,
      unit: "sq ft",
      notes: `${formatNumber(exteriorAssembly.cladding.thicknessIn)}" thick, ${formatNumber(exteriorAssembly.cladding.wastePercent)}% waste`,
      breakdown: exterior.breakdown
    },
    {
      id: "window_area",
      group: "walls",
      label: "Windows",
      materialId: "windows",
      quantity: exterior.windowArea,
      unit: "sq ft",
      notes: `${formatNumber(exterior.windowCount)} exterior windows`,
      breakdown: ["Sum of exterior window widths x configured/default window heights"]
    },
    {
      id: "exterior_doors",
      group: "walls",
      label: "Exterior doors",
      materialId: "exterior_doors",
      quantity: exterior.doorCount,
      unit: "each",
      notes: `${formatNumber(exterior.doorArea)} sq ft exterior door area`,
      breakdown: ["Counted from exterior door opening records"]
    },
    {
      id: "flooring",
      group: "interior",
      label: "Flooring",
      materialId: "flooring",
      quantity: flooringArea,
      unit: "sq ft",
      notes: `Floor area plus ${assumptions.flooringWastePercent}% waste`,
      breakdown: [
        "Union of authored spaces on each level",
        `${formatNumber(assumptions.flooringWastePercent)}% flooring waste`
      ]
    },
    {
      id: "pex_pipe",
      group: "services",
      label: "PEX pipe",
      materialId: "pex_pipe",
      quantity: pexLength,
      unit: "ft",
      notes: "First-pass wet-space plumbing allowance",
      breakdown: ["Explicit pex_length_ft if configured, otherwise wet-space count x per-wet-space allowance"]
    }
  ];
  const materialById: Record<string, MaterialCost> = {};
  for (const material of materials) {
    materialById[material.id] = material;
  }
  const total = quantities.reduce((sum, quantity) => sum + quantity.quantity * (materialById[quantity.materialId]?.unitCost ?? 0), 0);
  return {
    assumptions: {
      ...assumptions,
      exteriorWallHeightFt: exteriorAssembly.heightFt,
      footingWidthFt: footingWidth,
      padInsulationMarginFt: insulationMargin,
      padInsulationRMin: assumptions.padInsulationRMin,
      padInsulationRMax: assumptions.padInsulationRMax,
      padRebarSpacingFt: rebarSpacing,
      padRebarEdgeCoverIn: rebarCover * 12
    },
    materials,
    quantities,
    total,
    summary: [
      { label: "Concrete pad area", value: foundationPadArea, unit: "sq ft" },
      { label: "Pad insulation area", value: padInsulationArea, unit: "sq ft" },
      { label: "Concrete volume", value: concreteVolumeYd3, unit: "yd3" },
      { label: "Rebar length", value: padRebarLength + footingRebarLength, unit: "ft" },
      { label: "Roofing area", value: roofArea, unit: "sq ft" },
      { label: "Interior wall area", value: interior.netBothSidesArea, unit: "sq ft" },
      { label: "Interior doors", value: interior.doorCount, unit: "doors" },
      { label: "Exterior wall area", value: exterior.netArea, unit: "sq ft" },
      { label: "Exterior wall thickness", value: exteriorAssembly.totalThicknessIn, unit: "in" },
      { label: "ICF blocks", value: icfBlockCount, unit: "blocks" },
      { label: "Window area", value: exterior.windowArea, unit: "sq ft" },
      { label: "Flooring area", value: flooringArea, unit: "sq ft" },
      { label: "PEX length", value: pexLength, unit: "ft" }
    ]
  };
}

function materialFromRecord(id: string, rawMaterial: AnyRecord, fallback?: MaterialCost): MaterialCost {
  const rawUnitCost = rawMaterial.unit_cost ?? rawMaterial.unitCost;
  const unitCost = Number(rawUnitCost ?? fallback?.unitCost ?? 0);
  return {
    id,
    label: String(rawMaterial.label ?? fallback?.label ?? titleCase(id.split("_").join(" "))),
    unit: String(rawMaterial.unit ?? fallback?.unit ?? "each"),
    unitCost: Number.isFinite(unitCost) ? unitCost : fallback?.unitCost ?? 0
  };
}

function isRecord(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function floorAreaEstimate(data: AnyRecord): number {
  let total = 0;
  for (const [levelId, rawLevel] of Object.entries((data.levels as AnyRecord | undefined) ?? {})) {
    const level = rawLevel as AnyRecord;
    const rects = Object.keys((level.spaces as AnyRecord | undefined) ?? {})
      .map((spaceId) => resolveSpaceRect(data, levelId, spaceId))
      .filter(Boolean) as Rect[];
    total += unionArea(rects);
  }
  return total;
}

function foundationSourceLevel(data: AnyRecord): string | null {
  const foundations = data.foundations as AnyRecord | undefined;
  const first = foundations ? Object.values(foundations)[0] as AnyRecord | undefined : undefined;
  return typeof first?.source_level === "string" ? first.source_level : null;
}

function foundationNumber(data: AnyRecord, field: string, fallback: number): number {
  const foundations = data.foundations as AnyRecord | undefined;
  const first = foundations ? Object.values(foundations)[0] as AnyRecord | undefined : undefined;
  const value = Number(first?.[field]);
  return Number.isFinite(value) ? value : fallback;
}

function foundationSourceRects(data: AnyRecord, levelId: string): Rect[] {
  const foundations = data.foundations as AnyRecord | undefined;
  const foundation = foundations ? Object.values(foundations)[0] as AnyRecord | undefined : undefined;
  const directRects = rectSpecs(foundation);
  if (directRects.length) {
    return directRects.map((spec) => resolveRectSpec(data, levelId, spec)).filter(Boolean) as Rect[];
  }
  const selected = new Set(Array.isArray(foundation?.masses) ? foundation.masses.map(String) : Object.keys((data.masses as AnyRecord | undefined) ?? {}));
  return massRectsForLevel(data, levelId).filter((item) => selected.has(item.massId)).map((item) => item.rect);
}

function massRectsForLevel(data: AnyRecord, levelId: string): Array<{ massId: string; rect: Rect; spec: AnyRecord }> {
  const masses = (data.masses ?? {}) as AnyRecord;
  const rects: Array<{ massId: string; rect: Rect; spec: AnyRecord }> = [];
  for (const [massId, rawMass] of Object.entries(masses)) {
    const mass = rawMass as AnyRecord;
    if (!massAppliesToLevel(mass, levelId)) {
      continue;
    }
    for (const spec of rectSpecs(mass)) {
      if (!rectSpecAppliesToLevel(spec, mass, levelId)) {
        continue;
      }
      const rect = resolveRectSpec(data, levelId, spec);
      if (rect) {
        rects.push({ massId, rect, spec });
      }
    }
  }
  return rects;
}

function rectSpecs(source: AnyRecord | undefined): AnyRecord[] {
  if (!source) {
    return [];
  }
  const specs = Array.isArray(source.rects) ? [...source.rects] : [];
  if (source.rect) {
    specs.push(source.rect);
  }
  return specs.filter((spec) => spec && typeof spec === "object") as AnyRecord[];
}

function massAppliesToLevel(mass: AnyRecord, levelId: string) {
  if (Array.isArray(mass.levels)) {
    return mass.levels.includes(levelId);
  }
  if (mass.level !== undefined) {
    return mass.level === levelId;
  }
  return true;
}

function rectSpecAppliesToLevel(spec: AnyRecord, mass: AnyRecord, levelId: string) {
  if (Array.isArray(spec.levels)) {
    return spec.levels.includes(levelId);
  }
  if (spec.level !== undefined) {
    return spec.level === levelId;
  }
  return massAppliesToLevel(mass, levelId);
}

function resolveRectSpec(data: AnyRecord, levelId: string, spec: AnyRecord): Rect | null {
  const datums = mergedDatums(data, levelId);
  const rect = spec.rect ?? spec;
  if (Array.isArray(rect)) {
    return {
      left: value(rect[0], datums.x),
      top: value(rect[1], datums.y),
      right: value(rect[0], datums.x) + Number(rect[2] ?? 0),
      bottom: value(rect[1], datums.y) + Number(rect[3] ?? 0),
      width: Number(rect[2] ?? 0),
      height: Number(rect[3] ?? 0)
    };
  }
  if (Array.isArray(rect.x) && Array.isArray(rect.y)) {
    const x0 = value(rect.x[0], datums.x);
    const x1 = value(rect.x[1], datums.x);
    const y0 = value(rect.y[0], datums.y);
    const y1 = value(rect.y[1], datums.y);
    return makeRect(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1));
  }
  return null;
}

function mergedDatums(data: AnyRecord, levelId: string) {
  const level = ((data.levels as AnyRecord | undefined)?.[levelId] ?? {}) as AnyRecord;
  return {
    x: { ...((data.datums as AnyRecord | undefined)?.x ?? {}), ...(level.datums?.x ?? {}) },
    y: { ...((data.datums as AnyRecord | undefined)?.y ?? {}), ...(level.datums?.y ?? {}) }
  };
}

function value(raw: unknown, datums: AnyRecord): number {
  const numeric = Number(raw);
  if (Number.isFinite(numeric)) {
    return numeric;
  }
  return Number(datums[String(raw)] ?? 0);
}

function makeRect(left: number, top: number, right: number, bottom: number): Rect {
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function expandRect(rect: Rect, amount: number): Rect {
  return makeRect(rect.left - amount, rect.top - amount, rect.right + amount, rect.bottom + amount);
}

function unionArea(rects: Rect[]): number {
  const xs = uniqueSorted(rectCoordinates(rects, "x"));
  const ys = uniqueSorted(rectCoordinates(rects, "y"));
  let area = 0;
  for (const [left, right] of pairs(xs)) {
    for (const [top, bottom] of pairs(ys)) {
      const center = { x: (left + right) / 2, y: (top + bottom) / 2 };
      if (rects.some((rect) => contains(rect, center.x, center.y))) {
        area += (right - left) * (bottom - top);
      }
    }
  }
  return area;
}

function boundarySegments(rects: Rect[]): Segment[] {
  const xs = uniqueSorted(rectCoordinates(rects, "x"));
  const ys = uniqueSorted(rectCoordinates(rects, "y"));
  const covered = new Set<string>();
  for (let xi = 0; xi < xs.length - 1; xi += 1) {
    for (let yi = 0; yi < ys.length - 1; yi += 1) {
      const x = (xs[xi] + xs[xi + 1]) / 2;
      const y = (ys[yi] + ys[yi + 1]) / 2;
      if (rects.some((rect) => contains(rect, x, y))) {
        covered.add(`${xi},${yi}`);
      }
    }
  }
  const segments: Segment[] = [];
  for (const cell of covered) {
    const [xi, yi] = cell.split(",").map(Number);
    const left = xs[xi];
    const right = xs[xi + 1];
    const top = ys[yi];
    const bottom = ys[yi + 1];
    if (!covered.has(`${xi},${yi - 1}`)) segments.push({ orientation: "horizontal", fixed: top, start: left, end: right });
    if (!covered.has(`${xi},${yi + 1}`)) segments.push({ orientation: "horizontal", fixed: bottom, start: left, end: right });
    if (!covered.has(`${xi - 1},${yi}`)) segments.push({ orientation: "vertical", fixed: left, start: top, end: bottom });
    if (!covered.has(`${xi + 1},${yi}`)) segments.push({ orientation: "vertical", fixed: right, start: top, end: bottom });
  }
  return mergeSegments(segments);
}

function mergeSegments(segments: Segment[]): Segment[] {
  const groups = new Map<string, Segment[]>();
  for (const segment of segments) {
    const key = `${segment.orientation}:${roundKey(segment.fixed)}`;
    groups.set(key, [...(groups.get(key) ?? []), segment]);
  }
  const merged: Segment[] = [];
  for (const group of groups.values()) {
    const sorted = [...group].sort((a, b) => a.start - b.start);
    for (const segment of sorted) {
      const last = merged[merged.length - 1];
      if (last && last.orientation === segment.orientation && near(last.fixed, segment.fixed) && segment.start <= last.end + 1e-6) {
        last.end = Math.max(last.end, segment.end);
      } else {
        merged.push({ ...segment });
      }
    }
  }
  return merged;
}

function scanlineLength(rects: Rect[], spacing: number, edgeCover: number): number {
  if (!rects.length || spacing <= 0) {
    return 0;
  }
  const bounds = makeRect(
    Math.min(...rects.map((rect) => rect.left)),
    Math.min(...rects.map((rect) => rect.top)),
    Math.max(...rects.map((rect) => rect.right)),
    Math.max(...rects.map((rect) => rect.bottom))
  );
  let total = 0;
  for (let x = Math.ceil(bounds.left / spacing) * spacing; x <= bounds.right + 1e-6; x += spacing) {
    total += scanSegments(rects, "vertical", x).reduce((sum, [start, end]) => sum + Math.max(0, end - start - edgeCover * 2), 0);
  }
  for (let y = Math.ceil(bounds.top / spacing) * spacing; y <= bounds.bottom + 1e-6; y += spacing) {
    total += scanSegments(rects, "horizontal", y).reduce((sum, [start, end]) => sum + Math.max(0, end - start - edgeCover * 2), 0);
  }
  return total;
}

function scanSegments(rects: Rect[], axis: "horizontal" | "vertical", fixed: number): Array<[number, number]> {
  const intervals = rects
    .filter((rect) => axis === "vertical" ? fixed >= rect.left && fixed <= rect.right : fixed >= rect.top && fixed <= rect.bottom)
    .map((rect) => axis === "vertical" ? [rect.top, rect.bottom] as [number, number] : [rect.left, rect.right] as [number, number]);
  return mergeIntervals(intervals);
}

function interiorWallStats(data: AnyRecord, assumptions: CostAssumptions) {
  let length = 0;
  let openingsArea = 0;
  let doorArea = 0;
  let doorCount = 0;
  for (const [levelId, rawLevel] of Object.entries((data.levels as AnyRecord | undefined) ?? {})) {
    const level = rawLevel as AnyRecord;
    const spaces = Object.keys(level.spaces ?? {});
    if (level.derive_partitions !== false) {
      for (let i = 0; i < spaces.length; i += 1) {
        for (let j = i + 1; j < spaces.length; j += 1) {
          const shared = sharedBoundary(resolveSpaceRect(data, levelId, spaces[i]), resolveSpaceRect(data, levelId, spaces[j]));
          if (shared) {
            length += shared.length;
          }
        }
      }
    }
    for (const partition of level.partitions ?? []) {
      length += partitionLength(data, levelId, partition);
    }
    for (const opening of [...(level.connections ?? []), ...(level.openings ?? [])]) {
      const item = Array.isArray(opening) ? { between: opening } : opening;
      if (item.between || (typeof item.wall === "string" && item.wall.includes("__"))) {
        const area = Number(item.width ?? 3) * assumptions.defaultOpeningHeightFt;
        openingsArea += area * 2;
        if (isInteriorDoor(item)) {
          doorArea += area;
          doorCount += 1;
        }
      }
    }
  }
  const grossOneSideArea = length * assumptions.interiorWallHeightFt;
  const grossBothSidesArea = grossOneSideArea * 2;
  return {
    length,
    netOneSideArea: Math.max(0, grossOneSideArea - openingsArea / 2),
    netBothSidesArea: Math.max(0, grossBothSidesArea - openingsArea),
    doorArea,
    doorCount
  };
}

function isInteriorDoor(opening: AnyRecord): boolean {
  const kind = String(opening.kind ?? "door");
  return kind === "door";
}

function exteriorWallStats(data: AnyRecord, assumptions: CostAssumptions) {
  const masses = uniqueRoofMasses(data, assumptions);
  const rects = masses.map((mass) => mass.rect);
  let rectangularArea = 0;
  let gableArea = 0;
  let openingsArea = 0;
  let windowArea = 0;
  let windowCount = 0;
  let doorArea = 0;
  let doorCount = 0;

  for (const mass of masses) {
    for (const side of SIDES) {
      const exposedSegments = exposedSideSegments(mass.rect, side, rects);
      rectangularArea += exposedSegments.reduce((sum, [start, end]) => sum + (end - start) * mass.eaveHeight, 0);
      gableArea += openGableSide(mass, side)
        ? exposedSegments.reduce((sum, [start, end]) => sum + gableSegmentArea(mass, side, start, end), 0)
        : 0;
    }
  }

  for (const [levelId, rawLevel] of Object.entries((data.levels as AnyRecord | undefined) ?? {})) {
    const level = rawLevel as AnyRecord;
    for (const opening of level.openings ?? []) {
      if (!isExteriorOpening(opening)) {
        continue;
      }
      const kind = String(opening.kind ?? "door");
      const area = Number(opening.width ?? 0) * openingHeight(opening, assumptions);
      openingsArea += area;
      if (kind === "window") {
        windowArea += area;
        windowCount += 1;
      } else if (kind === "door") {
        doorArea += area;
        doorCount += 1;
      }
    }
  }
  const grossArea = rectangularArea + gableArea;
  return {
    length: masses.reduce(
      (sum, mass) => sum + SIDES.reduce((sideSum, side) => sideSum + exposedSideSegments(mass.rect, side, rects).reduce((total, [start, end]) => total + end - start, 0), 0),
      0
    ),
    grossArea,
    rectangularArea,
    gableArea,
    netArea: Math.max(0, grossArea - openingsArea),
    openingsArea,
    windowArea,
    windowCount,
    doorArea,
    doorCount,
    breakdown: [
      `Exposed rectangular wall faces to roof eaves: ${formatNumber(rectangularArea)} sq ft`,
      `Open-gable triangular wall faces: ${formatNumber(gableArea)} sq ft`,
      `Exterior openings subtracted: ${formatNumber(openingsArea)} sq ft`,
      "Faces are generated from unique mass rectangles and roof eave heights, not repeated per floor",
      "Cladding quantity adds configured waste after net exterior face area"
    ]
  };
}

function exteriorWallAssemblyConfig(data: AnyRecord, assumptions: CostAssumptions) {
  const exteriorWall = (((data.costing as AnyRecord | undefined)?.exterior_wall ?? {}) as AnyRecord);
  const icf = ((exteriorWall.icf ?? {}) as AnyRecord);
  const block = ((icf.block ?? {}) as AnyRecord);
  const cladding = ((exteriorWall.cladding ?? {}) as AnyRecord);
  const insulationThicknessIn = numberFrom(icf.insulation_thickness_in, 2.5);
  const concreteThicknessIn = numberFrom(icf.concrete_thickness_in, 6);
  const claddingThicknessIn = numberFrom(cladding.thickness_in, 1);
  return {
    heightFt: numberFrom(exteriorWall.height_ft, assumptions.exteriorWallHeightFt),
    icf: {
      blockLengthFt: numberFrom(block.length_ft, 4),
      blockHeightFt: numberFrom(block.height_ft, 16 / 12),
      insulationThicknessIn,
      concreteThicknessIn,
      wastePercent: numberFrom(icf.waste_percent, 8)
    },
    cladding: {
      type: String(cladding.type ?? "fieldstone"),
      thicknessIn: claddingThicknessIn,
      wastePercent: numberFrom(cladding.waste_percent, 10)
    },
    totalThicknessIn: insulationThicknessIn * 2 + concreteThicknessIn + claddingThicknessIn
  };
}

function plumbingPexLength(data: AnyRecord, assumptions: CostAssumptions): number {
  const plumbing = ((data.costing as AnyRecord | undefined)?.plumbing ?? {}) as AnyRecord;
  const explicitPex = Number(plumbing.pex_length_ft);
  if (Number.isFinite(explicitPex)) {
    return explicitPex;
  }
  let wetSpaces = 0;
  for (const rawLevel of Object.values((data.levels as AnyRecord | undefined) ?? {})) {
    const level = rawLevel as AnyRecord;
    for (const [spaceId, rawSpace] of Object.entries((level.spaces as AnyRecord | undefined) ?? {})) {
      const space = rawSpace as AnyRecord;
      const text = `${spaceId} ${String(space.label ?? "")}`.toLowerCase();
      if (/(bath|kitchen|laundry|machine|mechanical|utility|wet)/.test(text)) {
        wetSpaces += 1;
      }
    }
  }
  return wetSpaces * numberFrom(plumbing.pex_per_wet_space_ft, assumptions.defaultPexPerWetSpaceFt);
}

function isExteriorOpening(opening: AnyRecord): boolean {
  if (typeof opening.wall === "string") {
    return opening.wall.startsWith("exterior_");
  }
  return Boolean(opening.space && opening.side);
}

function roofStats(data: AnyRecord, assumptions: CostAssumptions): { area: number; areaWithWaste: number; breakdown: string[] } {
  const masses = uniqueRoofMasses(data, assumptions);
  const sorted = [...masses].sort((a, b) => b.eaveHeight - a.eaveHeight);
  const blockers: Rect[] = [];
  let area = 0;
  const breakdown: string[] = [];
  for (const mass of sorted) {
    const roofRect = roofEaveRect(mass);
    const projected = rectVisibleArea(roofRect, blockers);
    if (projected <= 0.01) {
      blockers.push(roofRect);
      breakdown.push(`${mass.id}: covered by higher/equal roof masses`);
      continue;
    }
    const slopeFactor = Math.sqrt(1 + mass.pitch * mass.pitch);
    const sloped = projected * slopeFactor;
    area += sloped;
    blockers.push(roofRect);
    breakdown.push(
      `${mass.id}: ${formatNumber(projected)} sq ft projected visible x ${formatNumber(slopeFactor)} slope = ${formatNumber(sloped)} sq ft`
    );
  }
  return {
    area,
    areaWithWaste: area * (1 + assumptions.roofWastePercent / 100),
    breakdown: [...breakdown, `${formatNumber(assumptions.roofWastePercent)}% roofing waste applied`]
  };
}

function roofAreaEstimate(data: AnyRecord, assumptions: CostAssumptions): number {
  return roofStats(data, assumptions).areaWithWaste;
}

function uniqueRoofMasses(data: AnyRecord, assumptions: CostAssumptions): RoofMass[] {
  const defaultPitch = pitchValue((data.roof as AnyRecord | undefined)?.pitch, assumptions);
  const defaultMargin = numberFrom((data.roof as AnyRecord | undefined)?.eave_margin, 0);
  const levelIds = Object.keys((data.levels as AnyRecord | undefined) ?? {});
  const masses = (data.masses ?? {}) as AnyRecord;
  const result: RoofMass[] = [];
  for (const [massId, rawMass] of Object.entries(masses)) {
    const mass = rawMass as AnyRecord;
    const massLevels = Array.isArray(mass.levels) ? mass.levels.map(String) : typeof mass.level === "string" ? [mass.level] : levelIds;
    for (const [index, spec] of rectSpecs(mass).entries()) {
      const roof = ((spec.roof ?? mass.roof ?? {}) as AnyRecord);
      if (roof.enabled === false || roof.mode === false) {
        continue;
      }
      const specLevels = Array.isArray(spec.levels) ? spec.levels.map(String) : typeof spec.level === "string" ? [spec.level] : massLevels;
      const levelId = specLevels.find((candidate) => levelIds.includes(candidate)) ?? levelIds[0] ?? "L1";
      const rect = resolveRectSpec(data, levelId, spec);
      if (!rect) {
        continue;
      }
      const pitch = optionalPitchValue(roof.pitch ?? roof.roof_pitch) ?? defaultPitch;
      const eaveHeight = numberFrom(roof.eave_height, assumptions.exteriorWallHeightFt);
      const mode = String(roof.mode ?? "hip").replace("-", "_");
      const [start, end] = roofEnds(roof, mode);
      result.push({
        id: String(spec.id ?? `${massId}_${index + 1}`),
        rect,
        roof,
        pitch,
        eaveHeight,
        eaveMargin: numberFrom(roof.eave_margin, defaultMargin),
        eaveSides: roofEaveSides(roof),
        ridge: roofRidge(roof, rect),
        start,
        end
      });
    }
  }
  if (!result.length) {
    const fallbackLevel = levelIds[0] ?? "L1";
    return massRectsForLevel(data, fallbackLevel).map(({ massId, rect }, index) => ({
      id: massId || `mass_${index + 1}`,
      rect,
      roof: {},
      pitch: defaultPitch,
      eaveHeight: assumptions.exteriorWallHeightFt,
      eaveMargin: defaultMargin,
      eaveSides: [...SIDES],
      ridge: rect.width >= rect.height ? "x" : "y",
      start: "hip",
      end: "hip"
    }));
  }
  return result;
}

function roofEaveSides(roof: AnyRecord): Side[] {
  const raw = roof.eave_sides ?? roof.eaves;
  if (Array.isArray(raw)) {
    const sides = raw.filter((side): side is Side => SIDES.includes(side as Side));
    return sides.length ? sides : [...SIDES];
  }
  return [...SIDES];
}

function roofRidge(roof: AnyRecord, rect: Rect): "x" | "y" {
  const ridge = String(roof.ridge ?? "");
  if (ridge === "x" || ridge === "y") {
    return ridge;
  }
  return rect.width >= rect.height ? "x" : "y";
}

function roofEnds(roof: AnyRecord, mode: string): ["open" | "hip", "open" | "hip"] {
  if (mode === "hip") {
    return ["hip", "hip"];
  }
  if (Array.isArray(roof.ends)) {
    return [roofEndKind(roof.ends[0]), roofEndKind(roof.ends[1])];
  }
  return [roofEndKind(roof.start ?? "open"), roofEndKind(roof.end ?? "open")];
}

function roofEndKind(value: unknown): "open" | "hip" {
  return String(value ?? "open").replace("-", "_") === "hip" ? "hip" : "open";
}

function roofEaveRect(mass: RoofMass): Rect {
  const north = mass.eaveSides.includes("north") ? mass.eaveMargin : 0;
  const east = mass.eaveSides.includes("east") ? mass.eaveMargin : 0;
  const south = mass.eaveSides.includes("south") ? mass.eaveMargin : 0;
  const west = mass.eaveSides.includes("west") ? mass.eaveMargin : 0;
  return makeRect(mass.rect.left - west, mass.rect.top - north, mass.rect.right + east, mass.rect.bottom + south);
}

function rectVisibleArea(subject: Rect, blockers: Rect[]): number {
  const xValues = [subject.left, subject.right];
  const yValues = [subject.top, subject.bottom];
  for (const blocker of blockers) {
    xValues.push(blocker.left, blocker.right);
    yValues.push(blocker.top, blocker.bottom);
  }
  const xs = uniqueSorted(xValues);
  const ys = uniqueSorted(yValues);
  let area = 0;
  for (const [left, right] of pairs(xs)) {
    for (const [top, bottom] of pairs(ys)) {
      const x = (left + right) / 2;
      const y = (top + bottom) / 2;
      if (contains(subject, x, y) && !blockers.some((rect) => contains(rect, x, y))) {
        area += (right - left) * (bottom - top);
      }
    }
  }
  return area;
}

function exposedSideSegments(rect: Rect, side: Side, allRects: Rect[]): Array<[number, number]> {
  const horizontal = side === "north" || side === "south";
  const start = horizontal ? rect.left : rect.top;
  const end = horizontal ? rect.right : rect.bottom;
  const sideCoordinates = [start, end];
  for (const other of allRects) {
    if (horizontal) {
      sideCoordinates.push(other.left, other.right);
    } else {
      sideCoordinates.push(other.top, other.bottom);
    }
  }
  const splitPoints = uniqueSorted(sideCoordinates).filter((point) => point >= start - 1e-6 && point <= end + 1e-6);
  const exposed: Array<[number, number]> = [];
  const epsilon = 1e-4;
  for (const [segmentStart, segmentEnd] of pairs(splitPoints)) {
    if (segmentEnd <= segmentStart + 1e-6) {
      continue;
    }
    const mid = (segmentStart + segmentEnd) / 2;
    const probe =
      side === "north" ? { x: mid, y: rect.top - epsilon } :
      side === "south" ? { x: mid, y: rect.bottom + epsilon } :
      side === "east" ? { x: rect.right + epsilon, y: mid } :
      { x: rect.left - epsilon, y: mid };
    if (!allRects.some((other) => contains(other, probe.x, probe.y))) {
      exposed.push([segmentStart, segmentEnd]);
    }
  }
  return mergeIntervals(exposed);
}

function openGableSide(mass: RoofMass, side: Side): boolean {
  if (mass.ridge === "x") {
    if (side === "west") return mass.start === "open";
    if (side === "east") return mass.end === "open";
    return false;
  }
  if (side === "north") return mass.start === "open";
  if (side === "south") return mass.end === "open";
  return false;
}

function gableSegmentArea(mass: RoofMass, side: Side, segmentStart: number, segmentEnd: number): number {
  const horizontal = side === "north" || side === "south";
  const baseStart = horizontal ? mass.rect.left : mass.rect.top;
  const baseLength = horizontal ? mass.rect.width : mass.rect.height;
  if (baseLength <= 0) {
    return 0;
  }
  const perpendicular = mass.ridge === "x" ? mass.rect.height : mass.rect.width;
  const peakRise = Math.max(0, perpendicular / 2) * mass.pitch;
  const start = Math.max(0, Math.min(baseLength, segmentStart - baseStart));
  const end = Math.max(0, Math.min(baseLength, segmentEnd - baseStart));
  if (end <= start || peakRise <= 0) {
    return 0;
  }
  return triangularIntegral(end, baseLength, peakRise) - triangularIntegral(start, baseLength, peakRise);
}

function triangularIntegral(t: number, baseLength: number, peakRise: number): number {
  const mid = baseLength / 2;
  if (mid <= 0) {
    return 0;
  }
  if (t <= mid) {
    return peakRise * t * t / (2 * mid);
  }
  const leftHalfArea = peakRise * mid / 2;
  const u = t - mid;
  return leftHalfArea + peakRise * (u - u * u / (2 * mid));
}

function pitchValue(raw: unknown, assumptions: CostAssumptions): number {
  return optionalPitchValue(raw) ?? assumptions.defaultRoofPitchRise / assumptions.defaultRoofPitchRun;
}

function optionalPitchValue(raw: unknown): number | null {
  if (typeof raw === "string" && raw.includes(":")) {
    const [rise, run] = raw.split(":").map(Number);
    return run ? rise / run : null;
  }
  const numeric = Number(raw);
  if (Number.isFinite(numeric)) {
    return numeric;
  }
  return null;
}

function partitionLength(data: AnyRecord, levelId: string, partition: AnyRecord): number {
  const datums = mergedDatums(data, levelId);
  if (Array.isArray(partition.from) && Array.isArray(partition.to)) {
    const x1 = value(partition.from[0], datums.x);
    const y1 = value(partition.from[1], datums.y);
    const x2 = value(partition.to[0], datums.x);
    const y2 = value(partition.to[1], datums.y);
    return Math.hypot(x2 - x1, y2 - y1);
  }
  return Number(partition.len ?? 0);
}

function sharedBoundary(a: Rect | null | undefined, b: Rect | null | undefined): { length: number } | null {
  if (!a || !b) {
    return null;
  }
  if (near(a.right, b.left) || near(b.right, a.left)) {
    const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return overlap > 1e-6 ? { length: overlap } : null;
  }
  if (near(a.bottom, b.top) || near(b.bottom, a.top)) {
    const overlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    return overlap > 1e-6 ? { length: overlap } : null;
  }
  return null;
}

function openingHeight(opening: AnyRecord, assumptions: CostAssumptions) {
  if (opening.height !== undefined) {
    return Number(opening.height);
  }
  if (opening.kind === "window") {
    return assumptions.defaultWindowHeightFt;
  }
  if (opening.kind === "door") {
    return assumptions.defaultDoorHeightFt;
  }
  return assumptions.defaultOpeningHeightFt;
}

function uniqueSorted(values: number[]) {
  return [...values].sort((a, b) => a - b).filter((value, index, sorted) => index === 0 || !near(value, sorted[index - 1]));
}

function rectCoordinates(rects: Rect[], axis: "x" | "y") {
  const values: number[] = [];
  for (const rect of rects) {
    if (axis === "x") {
      values.push(rect.left, rect.right);
    } else {
      values.push(rect.top, rect.bottom);
    }
  }
  return values;
}

function pairs(values: number[]): Array<[number, number]> {
  return values.slice(0, -1).map((value, index) => [value, values[index + 1]]);
}

function contains(rect: Rect, x: number, y: number) {
  return x >= rect.left - 1e-6 && x <= rect.right + 1e-6 && y >= rect.top - 1e-6 && y <= rect.bottom + 1e-6;
}

function mergeIntervals(intervals: Array<[number, number]>): Array<[number, number]> {
  const sorted = [...intervals].sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const [start, end] of sorted) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1] + 1e-6) {
      last[1] = Math.max(last[1], end);
    } else {
      merged.push([start, end]);
    }
  }
  return merged;
}

function roundKey(value: number) {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function near(a: number, b: number) {
  return Math.abs(a - b) <= 1e-6;
}

function formatNumber(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function numberFrom(value: unknown, fallback: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function titleCase(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
