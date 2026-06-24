import type { AnyRecord, SpaceRect } from "./types";
import { resolveSpaceRect } from "./geometry";

type Rect = SpaceRect;

export type StructuralPointLoad = {
  id: string;
  loadLb: number;
  bearingAreaSqFt: number;
  pressurePsf: number;
  notes: string;
};

export type StructuralLineLoad = {
  id: string;
  loadPlf: number;
  totalLoadLb: number;
  lengthFt: number;
  notes: string;
};

export type RafterEstimate = {
  id: string;
  level: string;
  massId: string;
  rectId: string;
  count: number;
  spacingIn: number;
  maxLengthFt: number;
  purchaseRequired: boolean;
  notes: string;
};

export type StructuralEstimate = {
  pointLoads: StructuralPointLoad[];
  lineLoads: StructuralLineLoad[];
  rafters: RafterEstimate[];
  missingInputs: string[];
};

export function estimateStructuralPrep(data: AnyRecord): StructuralEstimate {
  const structural = ((data.structural ?? {}) as AnyRecord);
  const materials = ((structural.materials ?? {}) as AnyRecord);
  const bearing = ((structural.bearing ?? {}) as AnyRecord);
  const pointLoads = pointLoadEstimates(data, materials, bearing);
  const lineLoads = lineLoadEstimates(data, materials, bearing);
  const rafters = rafterEstimates(data, structural);
  const missingInputs = missingStructuralInputs(structural);
  return { pointLoads, lineLoads, rafters, missingInputs };
}

function pointLoadEstimates(data: AnyRecord, materials: AnyRecord, bearing: AnyRecord): StructuralPointLoad[] {
  const loads: StructuralPointLoad[] = [];
  for (const rawLoad of (bearing.point_loads ?? []) as AnyRecord[]) {
    if (rawLoad.kind !== "masonry_mass") {
      continue;
    }
    const rect = rectFromLoad(data, rawLoad);
    if (!rect) {
      continue;
    }
    const heightFt = numberFrom(rawLoad.height_ft, 0);
    const densityPcf = materialDensity(materials, rawLoad.material);
    const loadLb = rect.width * rect.height * heightFt * densityPcf;
    const bearingAreaSqFt = Math.max(rect.width * rect.height, 1e-6);
    loads.push({
      id: String(rawLoad.id ?? "point_load"),
      loadLb,
      bearingAreaSqFt,
      pressurePsf: loadLb / bearingAreaSqFt,
      notes: `${formatNumber(rect.width)} x ${formatNumber(rect.height)} ft masonry mass, ${formatNumber(heightFt)} ft high`
    });
  }
  return loads;
}

function lineLoadEstimates(data: AnyRecord, materials: AnyRecord, bearing: AnyRecord): StructuralLineLoad[] {
  const loads: StructuralLineLoad[] = [];
  for (const rawLoad of (bearing.line_loads ?? []) as AnyRecord[]) {
    if (rawLoad.kind !== "masonry_perimeter") {
      continue;
    }
    const rect = rectFromLoad(data, rawLoad);
    if (!rect) {
      continue;
    }
    const lengthFt = (rect.width + rect.height) * 2;
    const thicknessFt = numberFrom(rawLoad.wall_thickness_in, 0) / 12;
    const heightFt = numberFrom(rawLoad.height_ft, 0);
    const densityPcf = materialDensity(materials, rawLoad.material);
    const loadPlf = thicknessFt * heightFt * densityPcf;
    loads.push({
      id: String(rawLoad.id ?? "line_load"),
      loadPlf,
      totalLoadLb: loadPlf * lengthFt,
      lengthFt,
      notes: `${formatNumber(thicknessFt * 12)} in masonry perimeter, ${formatNumber(heightFt)} ft high`
    });
  }
  return loads;
}

function rafterEstimates(data: AnyRecord, structural: AnyRecord): RafterEstimate[] {
  const rafterConfig = ((structural.rafters ?? {}) as AnyRecord);
  const spacingIn = numberFrom(rafterConfig.spacing_in, 16);
  const spacingFt = spacingIn / 12;
  const purchaseThresholdFt = numberFrom(rafterConfig.purchase_length_threshold_ft, 16);
  const defaultPitch = pitchValue((data.roof as AnyRecord | undefined)?.pitch, 8 / 12);
  const estimates: RafterEstimate[] = [];
  for (const levelId of Object.keys((data.levels as AnyRecord | undefined) ?? {})) {
    for (const item of massRectsForLevel(data, levelId)) {
      const roof = ((item.spec.roof ?? {}) as AnyRecord);
      if (roof.enabled === false || roof.mode === false) {
        continue;
      }
      const mode = String(roof.mode ?? "");
      const ridge = String(roof.ridge ?? "x");
      const pitch = pitchValue(roof.pitch ?? roof.roof_pitch, defaultPitch);
      const eaveMargin = numberFrom(roof.eave_margin ?? (data.roof as AnyRecord | undefined)?.eave_margin, 0);
      const acrossRidge = ridge === "y" ? item.rect.width : item.rect.height;
      const alongRidge = ridge === "y" ? item.rect.height : item.rect.width;
      const run = Math.max(0, acrossRidge / 2 + eaveMargin);
      const length = mode === "hip"
        ? Math.hypot(run, alongRidge / 2 + eaveMargin, run * pitch)
        : Math.hypot(run, run * pitch);
      const count = Math.max(2, Math.ceil((alongRidge + eaveMargin * 2) / spacingFt) + 1);
      estimates.push({
        id: `${levelId}.${item.massId}.${item.rectId}`,
        level: levelId,
        massId: item.massId,
        rectId: item.rectId,
        count,
        spacingIn,
        maxLengthFt: length,
        purchaseRequired: length > purchaseThresholdFt,
        notes: `${mode || "roof"} rafters at ${formatNumber(spacingIn)} in spacing`
      });
    }
  }
  return estimates;
}

function missingStructuralInputs(structural: AnyRecord): string[] {
  const designLoads = ((structural.design_loads ?? {}) as AnyRecord);
  const missing: string[] = [];
  for (const key of ["roof_snow_psf", "wind_psf", "soil_bearing_psf"]) {
    const value = designLoads[key];
    if (value === undefined || value === null || value === "") {
      missing.push(key);
    }
  }
  return missing;
}

function rectFromLoad(data: AnyRecord, load: AnyRecord): Rect | null {
  const levelId = String(load.level ?? "L1");
  if (typeof load.space === "string") {
    return resolveSpaceRect(data, levelId, load.space);
  }
  if (Array.isArray(load.at) && Array.isArray(load.size)) {
    return makeRect(
      numberFrom(load.at[0], 0),
      numberFrom(load.at[1], 0),
      numberFrom(load.at[0], 0) + numberFrom(load.size[0], 0),
      numberFrom(load.at[1], 0) + numberFrom(load.size[1], 0)
    );
  }
  return null;
}

function materialDensity(materials: AnyRecord, materialId: unknown): number {
  const material = materials[String(materialId)] as AnyRecord | undefined;
  return numberFrom(material?.density_pcf, 120);
}

function massRectsForLevel(data: AnyRecord, levelId: string): Array<{ massId: string; rectId: string; rect: Rect; spec: AnyRecord }> {
  const masses = (data.masses ?? {}) as AnyRecord;
  const rects: Array<{ massId: string; rectId: string; rect: Rect; spec: AnyRecord }> = [];
  for (const [massId, rawMass] of Object.entries(masses)) {
    const mass = rawMass as AnyRecord;
    if (!massAppliesToLevel(mass, levelId)) {
      continue;
    }
    for (const [index, spec] of rectSpecs(mass).entries()) {
      if (!rectSpecAppliesToLevel(spec, mass, levelId)) {
        continue;
      }
      const rect = resolveRectSpec(data, levelId, spec);
      if (rect) {
        rects.push({ massId, rectId: String(spec.id ?? `rect_${index + 1}`), rect, spec });
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
  if (Array.isArray(rect.x) && Array.isArray(rect.y)) {
    const x0 = value(rect.x[0], datums.x);
    const x1 = value(rect.x[1], datums.x);
    const y0 = value(rect.y[0], datums.y);
    const y1 = value(rect.y[1], datums.y);
    return makeRect(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1));
  }
  if (Array.isArray(rect)) {
    return makeRect(value(rect[0], datums.x), value(rect[1], datums.y), value(rect[0], datums.x) + numberFrom(rect[2], 0), value(rect[1], datums.y) + numberFrom(rect[3], 0));
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
  return numberFrom(datums[String(raw)], 0);
}

function makeRect(left: number, top: number, right: number, bottom: number): Rect {
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function pitchValue(raw: unknown, fallback: number): number {
  if (typeof raw === "string" && raw.includes(":")) {
    const [rise, run] = raw.split(":").map(Number);
    return run ? rise / run : fallback;
  }
  return numberFrom(raw, fallback);
}

function numberFrom(value: unknown, fallback: number): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function formatNumber(value: number) {
  return value.toLocaleString(undefined, { maximumSignificantDigits: 3 });
}
