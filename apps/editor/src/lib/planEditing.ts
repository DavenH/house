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
  if (["space", "feature", "opening", "wall", "stair", "level"].includes(kind)) {
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
  if (selected.kind === "stair") {
    return ((data.stairs as AnyRecord | undefined) ?? {})[selected.id] ?? null;
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

export function setFeatureAt(data: AnyRecord, levelId: string, featureId: string, at: [number, number]) {
  const feature = ((data.levels as AnyRecord)?.[levelId]?.features ?? {})[featureId] as AnyRecord | undefined;
  if (!feature) {
    return;
  }
  feature.at = at;
  syncStackedFeaturePlacement(data, levelId, featureId, at);
}

export function setFeatureAtCoordinate(
  data: AnyRecord,
  levelId: string,
  featureId: string,
  axisIndex: 0 | 1,
  value: number
) {
  const feature = ((data.levels as AnyRecord)?.[levelId]?.features ?? {})[featureId] as AnyRecord | undefined;
  if (!feature) {
    return;
  }
  const at: [number, number] = [
    Number(feature.at?.[0] ?? 20),
    Number(feature.at?.[1] ?? 20)
  ];
  at[axisIndex] = value;
  setFeatureAt(data, levelId, featureId, at);
}

function syncStackedFeaturePlacement(data: AnyRecord, levelId: string, featureId: string, at: [number, number]) {
  const sourceRef = `${levelId}.${featureId}`;
  for (const stack of (data.stacks ?? []) as AnyRecord[]) {
    const members = Array.isArray(stack.members) ? stack.members : [];
    const same = Array.isArray(stack.same) ? stack.same : [];
    if (!members.includes(sourceRef) || !same.some((rule: string) => ["center", "cx", "cy"].includes(rule))) {
      continue;
    }
    for (const member of members) {
      if (member === sourceRef || typeof member !== "string" || !member.includes(".")) {
        continue;
      }
      const [targetLevel, targetFeature] = member.split(".", 2);
      const feature = ((data.levels as AnyRecord)?.[targetLevel]?.features ?? {})[targetFeature] as AnyRecord | undefined;
      if (!feature) {
        continue;
      }
      const nextAt: [number, number] = [
        Number(feature.at?.[0] ?? at[0]),
        Number(feature.at?.[1] ?? at[1])
      ];
      if (same.includes("center") || same.includes("cx")) {
        nextAt[0] = at[0];
      }
      if (same.includes("center") || same.includes("cy")) {
        nextAt[1] = at[1];
      }
      feature.at = nextAt;
    }
  }
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
  } else if (selected.kind === "stair") {
    delete (data.stairs as AnyRecord | undefined)?.[selected.id];
  }
  return { kind: "", level: "", id: "" };
}

export function mergeSpaceInto(data: AnyRecord, levelId: string, sourceId: string, targetId: string): Selection {
  if (!sourceId || !targetId || sourceId === targetId) {
    return { kind: "space", level: levelId, id: sourceId };
  }
  const levelData = ensureLevel(data, levelId);
  const source = levelData.spaces?.[sourceId];
  const target = levelData.spaces?.[targetId];
  const sourceRect = resolveSpaceRect(data, levelId, sourceId);
  const targetRect = resolveSpaceRect(data, levelId, targetId);
  if (!source || !target || !sourceRect || !targetRect) {
    return { kind: "space", level: levelId, id: sourceId };
  }
  const left = Math.min(sourceRect.left, targetRect.left);
  const top = Math.min(sourceRect.top, targetRect.top);
  const right = Math.max(sourceRect.right, targetRect.right);
  const bottom = Math.max(sourceRect.bottom, targetRect.bottom);
  levelData.spaces[targetId] = {
    ...target,
    rect: [left, top, right - left, bottom - top]
  };
  delete levelData.spaces[sourceId];
  replaceSpaceReferences(levelData, sourceId, targetId);
  return { kind: "space", level: levelId, id: targetId };
}

function replaceSpaceReferences(levelData: AnyRecord, sourceId: string, targetId: string) {
  for (const feature of Object.values((levelData.features ?? {}) as AnyRecord)) {
    const featureData = feature as AnyRecord;
    if (featureData.within === sourceId) {
      featureData.within = targetId;
    }
    if (featureData.along?.space === sourceId) {
      featureData.along.space = targetId;
    }
  }
  if (Array.isArray(levelData.openings)) {
    for (const opening of levelData.openings as AnyRecord[]) {
      if (opening.space === sourceId) {
        opening.space = targetId;
      }
      if (Array.isArray(opening.between)) {
        opening.between = opening.between.map((spaceId: string) => (spaceId === sourceId ? targetId : spaceId));
      }
    }
  }
  if (Array.isArray(levelData.connections)) {
    levelData.connections = levelData.connections
      .map((connection: unknown) => {
        const connectionData = Array.isArray(connection) ? { between: connection } : { ...((connection ?? {}) as AnyRecord) };
        if (Array.isArray(connectionData.between)) {
          connectionData.between = connectionData.between.map((spaceId: string) =>
            spaceId === sourceId ? targetId : spaceId
          );
        }
        return connectionData;
      })
      .filter((connection: AnyRecord) => !isSelfEdge(connection.between));
  }
  if (Array.isArray(levelData.access)) {
    const seen = new Set<string>();
    levelData.access = levelData.access
      .map((edge: unknown) => {
        if (Array.isArray(edge)) {
          return edge.map((spaceId: string) => (spaceId === sourceId ? targetId : spaceId));
        }
        const edgeData = { ...((edge ?? {}) as AnyRecord) };
        if (edgeData.from === sourceId) {
          edgeData.from = targetId;
        }
        if (edgeData.to === sourceId) {
          edgeData.to = targetId;
        }
        return edgeData;
      })
      .filter((edge: unknown) => {
        const endpoints = Array.isArray(edge) ? edge : [(edge as AnyRecord).from, (edge as AnyRecord).to];
        if (isSelfEdge(endpoints)) {
          return false;
        }
        const key = endpoints.join("->");
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
  }
}

function isSelfEdge(endpoints: unknown) {
  return Array.isArray(endpoints) && endpoints.length >= 2 && endpoints[0] === endpoints[1];
}

function resolveSpaceRect(data: AnyRecord, levelId: string, spaceId: string) {
  const space = ((data.levels as AnyRecord)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
  if (!space) {
    return null;
  }
  if (Array.isArray(space.rect)) {
    const [x, y, w, h] = space.rect.map(Number);
    return { left: x, top: y, right: x + w, bottom: y + h };
  }
  if (Array.isArray(space.x) && Array.isArray(space.y)) {
    const left = datumValue(data, "x", space.x[0]);
    const right = datumValue(data, "x", space.x[1]);
    const top = datumValue(data, "y", space.y[0]);
    const bottom = datumValue(data, "y", space.y[1]);
    if ([left, right, top, bottom].some((value) => value === null)) {
      return null;
    }
    return { left: left as number, top: top as number, right: right as number, bottom: bottom as number };
  }
  return null;
}

function datumValue(data: AnyRecord, axis: "x" | "y", value: unknown): number | null {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const datums = ((data.datums ?? {}) as AnyRecord)[axis] ?? {};
    return typeof datums[value] === "number" ? datums[value] : null;
  }
  return null;
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
