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

export function estimateCosts(
  data: AnyRecord,
  assumptions: CostAssumptions = DEFAULT_COST_ASSUMPTIONS,
  materials: MaterialCost[] = DEFAULT_MATERIAL_COSTS
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
  const padInsulationArea = Math.max(0, unionArea(insulationRects) - foundationPadArea);
  const footingLength = boundarySegments(footingRects).reduce((total, segment) => total + segment.end - segment.start, 0);
  const padRebarLength = scanlineLength(padRects, rebarSpacing, rebarCover);
  const footingRebarLength = footingLength * assumptions.footingRebarRuns;
  const interior = interiorWallStats(data, assumptions);
  const exteriorAssembly = exteriorWallAssemblyConfig(data, assumptions);
  const exterior = exteriorWallStats(data, assumptions, exteriorAssembly.heightFt);
  const icfBlockArea = exteriorAssembly.icf.blockLengthFt * exteriorAssembly.icf.blockHeightFt;
  const icfBlockCount = icfBlockArea > 0 ? Math.ceil((exterior.netArea / icfBlockArea) * (1 + exteriorAssembly.icf.wastePercent / 100)) : 0;
  const icfCoreConcreteYd3 = exterior.netArea * (exteriorAssembly.icf.concreteThicknessIn / 12) / 27;
  const claddingArea = exterior.netArea * (1 + exteriorAssembly.cladding.wastePercent / 100);
  const flooringArea = floorAreaEstimate(data) * (1 + assumptions.flooringWastePercent / 100);
  const pexLength = plumbingPexLength(data, assumptions);
  const roofArea = roofAreaEstimate(data, assumptions);
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
      notes: `${formatNumber(foundationPadArea)} sq ft slab, ${formatNumber(footingLength)} ft footing`
    },
    {
      id: "pad_insulation",
      group: "pad",
      label: "Pad insulation",
      materialId: "pad_insulation",
      quantity: padInsulationArea,
      unit: "sq ft",
      notes: `${formatNumber(insulationMargin)} ft perimeter apron beyond source mass`
    },
    {
      id: "pad_and_footing_rebar",
      group: "pad",
      label: "Pad grid + footing rebar",
      materialId: "rebar",
      quantity: padRebarLength + footingRebarLength,
      unit: "ft",
      notes: `${formatNumber(padRebarLength)} ft grid, ${formatNumber(footingRebarLength)} ft footing`
    },
    {
      id: "roofing_area",
      group: "roof",
      label: "Roofing material",
      materialId: "roofing",
      quantity: roofArea,
      unit: "sq ft",
      notes: `Includes ${assumptions.roofWastePercent}% waste and pitch slope factor`
    },
    {
      id: "interior_framing",
      group: "framing",
      label: "Interior framing lumber",
      materialId: "interior_framing",
      quantity: interior.netOneSideArea,
      unit: "sq ft wall",
      notes: `${formatNumber(interior.length)} ft derived/explicit interior partitions`
    },
    {
      id: "interior_wall_board",
      group: "interior",
      label: "Interior wall board",
      materialId: "interior_drywall",
      quantity: interior.netBothSidesArea,
      unit: "sq ft face",
      notes: "Both faces, openings subtracted"
    },
    {
      id: "interior_doors",
      group: "interior",
      label: "Interior doors",
      materialId: "interior_doors",
      quantity: interior.doorCount,
      unit: "each",
      notes: `${formatNumber(interior.doorArea)} sq ft interior door openings`
    },
    {
      id: "icf_blocks",
      group: "walls",
      label: "ICF blocks",
      materialId: "icf_block",
      quantity: icfBlockCount,
      unit: "block",
      notes: `${formatNumber(exterior.netArea)} sq ft net wall, ${formatNumber(exteriorAssembly.icf.wastePercent)}% waste`
    },
    {
      id: "icf_core_concrete",
      group: "walls",
      label: "ICF core concrete",
      materialId: "concrete",
      quantity: icfCoreConcreteYd3,
      unit: "yd3",
      notes: `${formatNumber(exteriorAssembly.icf.concreteThicknessIn)}" concrete core`
    },
    {
      id: "exterior_cladding",
      group: "walls",
      label: `${titleCase(exteriorAssembly.cladding.type)} cladding`,
      materialId: "exterior_cladding",
      quantity: claddingArea,
      unit: "sq ft",
      notes: `${formatNumber(exteriorAssembly.cladding.thicknessIn)}" thick, ${formatNumber(exteriorAssembly.cladding.wastePercent)}% waste`
    },
    {
      id: "window_area",
      group: "walls",
      label: "Windows",
      materialId: "windows",
      quantity: exterior.windowArea,
      unit: "sq ft",
      notes: `${formatNumber(exterior.windowCount)} exterior windows`
    },
    {
      id: "exterior_doors",
      group: "walls",
      label: "Exterior doors",
      materialId: "exterior_doors",
      quantity: exterior.doorCount,
      unit: "each",
      notes: `${formatNumber(exterior.doorArea)} sq ft exterior door area`
    },
    {
      id: "flooring",
      group: "interior",
      label: "Flooring",
      materialId: "flooring",
      quantity: flooringArea,
      unit: "sq ft",
      notes: `Floor area plus ${assumptions.flooringWastePercent}% waste`
    },
    {
      id: "pex_pipe",
      group: "services",
      label: "PEX pipe",
      materialId: "pex_pipe",
      quantity: pexLength,
      unit: "ft",
      notes: "First-pass wet-space plumbing allowance"
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

function exteriorWallStats(data: AnyRecord, assumptions: CostAssumptions, wallHeightFt: number) {
  let length = 0;
  let openingsArea = 0;
  let windowArea = 0;
  let windowCount = 0;
  let doorArea = 0;
  let doorCount = 0;
  for (const [levelId, rawLevel] of Object.entries((data.levels as AnyRecord | undefined) ?? {})) {
    const rects = massRectsForLevel(data, levelId).map((item) => item.rect);
    length += boundarySegments(rects).reduce((sum, segment) => sum + segment.end - segment.start, 0);
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
  return {
    length,
    netArea: Math.max(0, length * wallHeightFt - openingsArea),
    openingsArea,
    windowArea,
    windowCount,
    doorArea,
    doorCount
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

function roofAreaEstimate(data: AnyRecord, assumptions: CostAssumptions): number {
  const defaultPitch = pitchValue((data.roof as AnyRecord | undefined)?.pitch, assumptions);
  let projected = 0;
  for (const levelId of Object.keys((data.levels as AnyRecord | undefined) ?? {})) {
    for (const { rect, spec } of massRectsForLevel(data, levelId)) {
      const roof = ((spec.roof ?? {}) as AnyRecord);
      if (roof.enabled === false || roof.mode === false) {
        continue;
      }
      const pitch = optionalPitchValue(roof.pitch ?? roof.roof_pitch) ?? defaultPitch;
      const margin = Number(roof.eave_margin ?? (data.roof as AnyRecord | undefined)?.eave_margin ?? 0);
      const roofRect = expandRect(rect, Number.isFinite(margin) ? margin : 0);
      projected += roofRect.width * roofRect.height * Math.sqrt(1 + pitch * pitch);
    }
  }
  return projected * (1 + assumptions.roofWastePercent / 100);
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
