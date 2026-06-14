import * as yaml from "js-yaml";
import type { AnyRecord, PaletteItem, Selection, SelectionKind } from "./types";
import { dumpPlanYaml, isPlainObject } from "./yamlFormat";

export function normalizeSvgKind(kind: string): SelectionKind {
  if (kind === "feature-clearance") {
    return "feature";
  }
  if (kind === "wall-select" || kind === "wall-grip") {
    return "wall";
  }
  if (["space", "feature", "opening", "wall", "level"].includes(kind)) {
    return kind as SelectionKind;
  }
  return "";
}

export function resolveSelection(data: AnyRecord, selected: Selection): AnyRecord | null {
  if (!selected.kind || !selected.level) {
    return null;
  }
  const selectedLevel = ((data.levels as AnyRecord | undefined)?.[selected.level] ?? {}) as AnyRecord;
  if (selected.kind === "space") {
    return selectedLevel.spaces?.[selected.id] ?? null;
  }
  if (selected.kind === "feature") {
    return selectedLevel.features?.[selected.id] ?? null;
  }
  if (selected.kind === "opening") {
    const index = openingIndex(selectedLevel, selected.id);
    selected.index = index;
    return index >= 0 ? selectedLevel.openings[index] : null;
  }
  if (selected.kind === "connection") {
    const index = Number(selected.index ?? selected.id);
    return selectedLevel.connections?.[index] ?? null;
  }
  return { id: selected.id };
}

export function openingIndex(selectedLevel: AnyRecord, id: string) {
  return Array.isArray(selectedLevel.openings)
    ? selectedLevel.openings.findIndex((opening: AnyRecord) => opening.id === id)
    : -1;
}

export function connectionOpeningIndex(selectedLevel: AnyRecord, id: string) {
  return Array.isArray(selectedLevel.connections)
    ? selectedLevel.connections.findIndex((connection: unknown, index: number) => connectionOpeningId(connection, index) === id)
    : -1;
}

export function findOpening(data: AnyRecord, id: string): Selection | null {
  for (const levelId of Object.keys((data.levels as AnyRecord | undefined) ?? {})) {
    const currentLevel = (data.levels as AnyRecord)[levelId];
    const index = openingIndex(currentLevel, id);
    if (index >= 0) {
      return { kind: "opening", level: levelId, id, index };
    }
  }
  return null;
}

export function findConnectionOpening(data: AnyRecord, id: string): Selection | null {
  for (const levelId of Object.keys((data.levels as AnyRecord | undefined) ?? {})) {
    const currentLevel = (data.levels as AnyRecord)[levelId];
    const index = connectionOpeningIndex(currentLevel, id);
    if (index >= 0) {
      return { kind: "connection", level: levelId, id, index };
    }
  }
  return null;
}

export function connectionOpeningId(connection: unknown, index: number) {
  const data = Array.isArray(connection) ? { between: connection } : ((connection ?? {}) as AnyRecord);
  const between = Array.isArray(data.between) ? data.between : ["", ""];
  const kind = data.kind ?? "door";
  return data.id ?? `${between[0]}_${between[1]}_${kind}_${index + 1}`;
}

export function ensureLevel(data: AnyRecord, levelId: string): AnyRecord {
  data.levels ??= {};
  data.levels[levelId] ??= { title: levelId, spaces: {}, features: {}, openings: [] };
  return data.levels[levelId];
}

export function entries(record: unknown): Array<[string, AnyRecord]> {
  if (!record || typeof record !== "object" || Array.isArray(record)) {
    return [];
  }
  return Object.entries(record as AnyRecord);
}

export function addPaletteItemToData(data: AnyRecord, activeLevel: string, item: PaletteItem): Selection {
  const targetLevel = ensureLevel(data, activeLevel);
  if (item.noun === "space") {
    const id = uniqueId(targetLevel.spaces ?? {}, "room");
    targetLevel.spaces ??= {};
    targetLevel.spaces[id] = {
      rect: [10, 10, 10, 10],
      privacy: "semi_private"
    };
    return { kind: "space", level: activeLevel, id };
  }
  if (item.noun === "feature") {
    targetLevel.features ??= {};
    const id = uniqueId(targetLevel.features, item.kind ?? "feature");
    targetLevel.features[id] = featureDefaults(data, item.kind ?? "feature");
    return { kind: "feature", level: activeLevel, id };
  }
  if (item.noun === "opening") {
    targetLevel.openings ??= [];
    const id = uniqueIdFromArray(targetLevel.openings, item.openingKind ?? "opening");
    const space = Object.keys(targetLevel.spaces ?? {})[0] ?? "";
    targetLevel.openings.push({
      id,
      space,
      side: "north",
      width: item.openingKind === "door" ? 3 : 5,
      kind: item.openingKind
    });
    return { kind: "opening", level: activeLevel, id, index: targetLevel.openings.length - 1 };
  }
  targetLevel.connections ??= [];
  const spaceIds = Object.keys(targetLevel.spaces ?? {});
  targetLevel.connections.push({
    between: [spaceIds[0] ?? "", spaceIds[1] ?? ""],
    kind: item.openingKind
  });
  return {
    kind: "connection",
    level: activeLevel,
    id: String(targetLevel.connections.length - 1),
    index: targetLevel.connections.length - 1
  };
}

export function setPath(root: AnyRecord, path: Array<string | number>, value: unknown) {
  let current = root;
  for (let index = 0; index < path.length - 1; index += 1) {
    const part = path[index];
    current[part] ??= typeof path[index + 1] === "number" ? [] : {};
    current = current[part];
  }
  current[path[path.length - 1]] = value;
}

export function deleteSelection(data: AnyRecord, selected: Selection): Selection {
  if (!selected.kind || !selected.level) {
    return selected;
  }
  const selectedLevel = ensureLevel(data, selected.level);
  if (selected.kind === "space") {
    removeSpaceReferences(selectedLevel, selected.id);
    delete selectedLevel.spaces?.[selected.id];
  } else if (selected.kind === "feature") {
    delete selectedLevel.features?.[selected.id];
  } else if (selected.kind === "opening") {
    const index = openingIndex(selectedLevel, selected.id);
    if (index >= 0) {
      selectedLevel.openings.splice(index, 1);
    }
  } else if (selected.kind === "connection") {
    const index = Number(selected.index ?? selected.id);
    if (Array.isArray(selectedLevel.connections) && index >= 0) {
      selectedLevel.connections.splice(index, 1);
    }
  }
  return { kind: "", level: "", id: "" };
}

export function removeSpaceReferences(levelData: AnyRecord, spaceId: string) {
  if (levelData.features) {
    for (const [featureId, feature] of Object.entries(levelData.features as AnyRecord)) {
      const featureData = feature as AnyRecord;
      if (featureData.within === spaceId || featureData.along?.space === spaceId) {
        delete levelData.features[featureId];
      }
    }
  }
  if (Array.isArray(levelData.connections)) {
    levelData.connections = levelData.connections.filter((connection: unknown) => {
      const connectionData = Array.isArray(connection) ? { between: connection } : ((connection ?? {}) as AnyRecord);
      return !Array.isArray(connectionData.between) || !connectionData.between.includes(spaceId);
    });
  }
  if (Array.isArray(levelData.access)) {
    levelData.access = levelData.access.filter((edge: unknown) => {
      if (Array.isArray(edge)) {
        return !edge.includes(spaceId);
      }
      const edgeData = (edge ?? {}) as AnyRecord;
      return edgeData.from !== spaceId && edgeData.to !== spaceId;
    });
  }
  if (Array.isArray(levelData.openings)) {
    levelData.openings = levelData.openings.filter((opening: AnyRecord) => opening.space !== spaceId);
  }
}

export function cleanupYamlDanglingReferences(source: string): { yamlText: string } | null {
  let parsed: unknown;
  try {
    parsed = yaml.load(source);
  } catch {
    return null;
  }
  if (!isPlainObject(parsed) || !isPlainObject(parsed.levels)) {
    return null;
  }
  let changed = false;
  for (const levelData of Object.values(parsed.levels as AnyRecord)) {
    if (!isPlainObject(levelData) || !isPlainObject(levelData.spaces)) {
      continue;
    }
    const spaceIds = new Set(Object.keys(levelData.spaces));
    for (const spaceId of referencedMissingSpaces(levelData, spaceIds)) {
      removeSpaceReferences(levelData, spaceId);
      changed = true;
    }
  }
  return changed ? { yamlText: dumpPlanYaml(parsed) } : null;
}

function referencedMissingSpaces(levelData: AnyRecord, spaceIds: Set<string>) {
  const missing = new Set<string>();
  for (const feature of Object.values((levelData.features ?? {}) as AnyRecord)) {
    const featureData = feature as AnyRecord;
    addMissingSpace(missing, spaceIds, featureData.within);
    addMissingSpace(missing, spaceIds, featureData.along?.space);
  }
  for (const connection of levelData.connections ?? []) {
    const connectionData = Array.isArray(connection) ? { between: connection } : ((connection ?? {}) as AnyRecord);
    for (const spaceId of connectionData.between ?? []) {
      addMissingSpace(missing, spaceIds, spaceId);
    }
  }
  for (const opening of levelData.openings ?? []) {
    const openingData = (opening ?? {}) as AnyRecord;
    addMissingSpace(missing, spaceIds, openingData.space);
    for (const spaceId of openingData.between ?? []) {
      addMissingSpace(missing, spaceIds, spaceId);
    }
  }
  for (const edge of levelData.access ?? []) {
    if (Array.isArray(edge)) {
      for (const spaceId of edge) {
        addMissingSpace(missing, spaceIds, spaceId);
      }
    } else {
      const edgeData = (edge ?? {}) as AnyRecord;
      addMissingSpace(missing, spaceIds, edgeData.from);
      addMissingSpace(missing, spaceIds, edgeData.to);
    }
  }
  return missing;
}

function addMissingSpace(missing: Set<string>, spaceIds: Set<string>, value: unknown) {
  if (typeof value === "string" && !spaceIds.has(value)) {
    missing.add(value);
  }
}

function featureDefaults(data: AnyRecord, kind: string): AnyRecord {
  const catalog = (data.catalog ?? {}) as AnyRecord;
  if (catalog[kind]) {
    return { kind, at: [20, 20] };
  }
  const base: Record<string, AnyRecord> = {
    desk_counter: { at: [20, 20], size: [6, 2], label: "DESK/COUNTER" },
    refrigerator: { at: [20, 20], size: [3, 3], label: "REFRIGERATOR" },
    storage: { at: [20, 20], size: [6, 4], label: "STORAGE" }
  };
  return base[kind] ?? { at: [20, 20], size: [4, 4], label: labelFor(kind) };
}

function uniqueId(record: AnyRecord, base: string) {
  const safe = base.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").toLowerCase() || "item";
  let id = safe;
  let counter = 2;
  while (Object.prototype.hasOwnProperty.call(record, id)) {
    id = `${safe}_${counter++}`;
  }
  return id;
}

function uniqueIdFromArray(items: AnyRecord[], base: string) {
  const record: AnyRecord = {};
  for (const item of items) {
    record[item.id] = true;
  }
  return uniqueId(record, base);
}

function labelFor(value: string) {
  return value.replace(/_/g, " ").toUpperCase();
}
