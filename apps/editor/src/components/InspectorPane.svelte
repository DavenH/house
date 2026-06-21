<script lang="ts">
  import {
    type DatumRow,
    relationData as accessData,
    relationData as connectionData,
    relationIncludesPair,
    roundHalf,
    sameKey,
    splitList,
    uniqueListId
  } from "../lib/inspectorModel";
  import type { AnyRecord, MassEdgeRef, Selection, SelectionKind, WallLine } from "../lib/types";
  import InspectorHeader from "./InspectorHeader.svelte";
  import PulloutTab from "./PulloutTab.svelte";

  export let selected: Selection = { kind: "", level: "", id: "" };
  export let open = true;
  export let selectedObject: AnyRecord | null = null;
  export let selectedWallLine: WallLine | null = null;
  export let selectedWallEdgeRefs: MassEdgeRef[] = [];
  export let planData: AnyRecord = {};
  export let activeLevel = "";
  export let spaces: Array<[string, AnyRecord]> = [];
  export let datums: AnyRecord = {};
  export let connections: AnyRecord[] = [];
  export let openings: AnyRecord[] = [];
  export let partitions: AnyRecord[] = [];
  export let access: Array<string[] | AnyRecord> = [];
  export let stacks: AnyRecord[] = [];
  export let alignments: AnyRecord[] = [];
  export let catalog: AnyRecord = {};
  export let constraintRefs: Array<{ value: string; label: string }> = [];
  export let deleteSelected: () => void;
  export let addWindowToSelectedWall: () => void = () => {};
  export let selectObject: (kind: SelectionKind, id: string, index?: number) => void;
  export let updateField: (path: Array<string | number>, value: unknown) => void;
  export let updateNumber: (path: Array<string | number>, value: string) => void;
  export let onToggle: () => void;

  let featureFormKey = "";
  let featureXValue = "";
  let featureYValue = "";
  let featureWidthValue = "";
  let featureHeightValue = "";

  $: connection =
    selected.kind === "connection" && selectedObject
      ? Array.isArray(selectedObject)
        ? { between: selectedObject }
        : selectedObject
      : null;
  $: relationScopeKey = [
    selected.kind,
    selected.level,
    selected.id,
    selected.index ?? "",
    activeLevel,
    selectedObject?.space ?? "",
    connection?.between?.join(",") ?? ""
  ].join("|");
  $: scopedConnectionRows = relationScopeKey
    ? connections
        .map((item, index) => ({ item, index }))
        .filter((row) => connectionIsScoped(row.item, row.index))
    : [];
  $: scopedOpeningRows = relationScopeKey
    ? openings
        .map((item, index) => ({ item, index }))
        .filter((row) => openingIsScoped(row.item, row.index))
    : [];
  $: scopedAccessRows = relationScopeKey
    ? access
        .map((item, index) => ({ item, index }))
        .filter((row) => accessIsScoped(row.item))
    : [];
  $: scopedStackRows = relationScopeKey
    ? stacks
        .map((item, index) => ({ item, index }))
        .filter((row) => constraintIsScoped(row.item))
    : [];
  $: scopedAlignmentRows = relationScopeKey
    ? alignments
        .map((item, index) => ({ item, index }))
        .filter((row) => constraintIsScoped(row.item))
    : [];
  $: scopedDatumRows = relationScopeKey && spaces && datums && selectedObject !== undefined ? selectedDatumRows() : [];
  $: hasScopedRelations =
    scopedConnectionRows.length > 0 ||
    scopedOpeningRows.length > 0 ||
    scopedAccessRows.length > 0 ||
    scopedStackRows.length > 0 ||
    scopedAlignmentRows.length > 0 ||
    scopedDatumRows.length > 0;
  const sameOptions = [
    { label: "Same footprint", value: "x,y,w,h" },
    { label: "Same left edge + width", value: "x,w" },
    { label: "Same top edge + height", value: "y,h" },
    { label: "Same center point", value: "cx,cy" },
    { label: "Same horizontal center", value: "cx" },
    { label: "Same vertical center", value: "cy" },
    { label: "Same width + height", value: "w,h" },
    { label: "Same left edge", value: "x" },
    { label: "Same top edge", value: "y" },
    { label: "Same right edge", value: "right" },
    { label: "Same bottom edge", value: "bottom" },
    { label: "Same width", value: "w" },
    { label: "Same height", value: "h" }
  ];
  $: selectedFeature =
    selected.kind === "feature"
      ? (((planData.levels as AnyRecord | undefined)?.[selected.level]?.features ?? {})[selected.id] as AnyRecord | undefined)
      : undefined;
  $: effectiveSelectedFeature = (selectedFeature ?? selectedObject ?? {}) as AnyRecord;
  $: catalogFeature = ((effectiveSelectedFeature?.kind ? catalog[effectiveSelectedFeature.kind] : null) ?? {}) as AnyRecord;
  $: featureSizeSource = effectiveSelectedFeature.size ?? catalogFeature.size;
  $: featureWidth = Number(featureSizeSource?.[0] ?? 4);
  $: featureHeight = Number(featureSizeSource?.[1] ?? 4);
  $: featureLabel = effectiveSelectedFeature.label ?? catalogFeature.label ?? "";
  $: featureMargin = effectiveSelectedFeature.clearance?.around ?? catalogFeature.clearance?.around ?? "";
  $: featureRotation = effectiveSelectedFeature.rotation ?? catalogFeature.rotation ?? 0;
  $: selectedFeatureKey =
    selected.kind === "feature"
      ? `${selected.level}:${selected.id}:${effectiveSelectedFeature.kind ?? ""}:${JSON.stringify(effectiveSelectedFeature.size ?? catalogFeature.size ?? [])}:${featureRotation}`
      : "";
  $: if (selectedFeatureKey !== featureFormKey) {
    featureFormKey = selectedFeatureKey;
    featureXValue = String(effectiveSelectedFeature.at?.[0] ?? 20);
    featureYValue = String(effectiveSelectedFeature.at?.[1] ?? 20);
    featureWidthValue = String(featureWidth);
    featureHeightValue = String(featureHeight);
  }
  $: featureKindOptions = [
    { value: "rectangle", label: "Rectangle" },
    { value: "piano", label: "Piano" },
    ...Object.keys(catalog).map((kind) => ({ value: kind, label: kind }))
  ].filter((option, index, options) => options.findIndex((item) => item.value === option.value) === index);
  $: selectedStair =
    selected.kind === "stair"
      ? (((planData.stairs as AnyRecord | undefined) ?? {})[selected.id] ?? selectedObject ?? {})
      : undefined;
  $: storyHeight = Number((planData.story as AnyRecord | undefined)?.floor_to_floor ?? selectedStair?.floor_to_floor ?? 10);

  const sideOptions = ["north", "east", "south", "west"];
  const positionOptions = ["west", "east", "north", "south", "start", "end"];
  const openingKindOptions = ["door", "arch", "open"];

  function connectionIndex() {
    return selected.index ?? Number(selected.id) ?? 0;
  }

  function updateConnectionField(field: string, value: unknown) {
    const index = connectionIndex();
    const current: AnyRecord = Array.isArray(selectedObject) ? { between: selectedObject } : { ...(selectedObject ?? {}) };
    if (value === undefined) {
      delete current[field];
    } else {
      current[field] = value;
    }
    updateField(["levels", selected.level, "connections", index], current);
  }

  function updateConnectionNumber(field: string, value: string) {
    const numberValue = Number(value);
    if (!Number.isNaN(numberValue)) {
      updateConnectionField(field, numberValue);
    }
  }

  function updateFeatureWithin(value: string) {
    if (value) {
      updateField(["levels", selected.level, "features", selected.id, "within"], value);
      return;
    }
    const current: AnyRecord = { ...(effectiveSelectedFeature ?? {}) };
    delete current.within;
    updateField(["levels", selected.level, "features", selected.id], current);
  }

  function updateFeatureKind(value: string) {
    const current: AnyRecord = { ...(effectiveSelectedFeature ?? {}) };
    current.kind = value;
    current.size = Array.isArray(current.size) ? current.size : [featureWidth, featureHeight];
    updateField(["levels", selected.level, "features", selected.id], current);
  }

  function updateFeatureMargin(value: string) {
    const numberValue = Number(value);
    const current: AnyRecord = { ...(effectiveSelectedFeature ?? {}) };
    const clearance: AnyRecord = { ...(current.clearance ?? {}) };
    if (value === "" || Number.isNaN(numberValue)) {
      delete clearance.around;
    } else {
      clearance.around = numberValue;
    }
    if (Object.keys(clearance).length) {
      current.clearance = clearance;
    } else {
      delete current.clearance;
    }
    updateField(["levels", selected.level, "features", selected.id], current);
  }

  function updateFeatureNumber(field: "x" | "y" | "w" | "h", value: string) {
    if (field === "x") {
      featureXValue = value;
      updateNumber(["levels", selected.level, "features", selected.id, "at", 0], value);
    } else if (field === "y") {
      featureYValue = value;
      updateNumber(["levels", selected.level, "features", selected.id, "at", 1], value);
    } else if (field === "w") {
      featureWidthValue = value;
      updateNumber(["levels", selected.level, "features", selected.id, "size", 0], value);
    } else {
      featureHeightValue = value;
      updateNumber(["levels", selected.level, "features", selected.id, "size", 1], value);
    }
  }

  function updateStairNumber(path: Array<string | number>, value: string) {
    const numberValue = Number(value);
    if (!Number.isNaN(numberValue)) {
      updateField(["stairs", selected.id, ...path], numberValue);
    }
  }

  function updateStoryHeight(value: string) {
    const numberValue = Number(value);
    if (!Number.isNaN(numberValue)) {
      updateField(["story", "floor_to_floor"], numberValue);
    }
  }

  function updateConnectionAt(index: number, field: string, value: unknown) {
    const current = { ...connectionData(connections[index] ?? {}) };
    if (value === undefined || value === "") {
      delete current[field];
    } else {
      current[field] = value;
    }
    updateField(["levels", activeLevel, "connections", index], current);
  }

  function updateConnectionNumberAt(index: number, field: string, value: string) {
    const numberValue = Number(value);
    updateConnectionAt(index, field, Number.isNaN(numberValue) ? undefined : numberValue);
  }

  function removeConnectionAt(index: number) {
    const next = connections.slice();
    next.splice(index, 1);
    updateField(["levels", activeLevel, "connections"], next);
  }

  function updateOpeningAt(index: number, field: string, value: unknown) {
    const current = { ...(openings[index] ?? {}) };
    if (value === undefined || value === "") {
      delete current[field];
    } else {
      current[field] = value;
    }
    updateField(["levels", activeLevel, "openings", index], current);
  }

  function updateOpeningNumberAt(index: number, field: string, value: string) {
    const numberValue = Number(value);
    updateOpeningAt(index, field, Number.isNaN(numberValue) ? undefined : numberValue);
  }

  function removeOpeningAt(index: number) {
    const next = openings.slice();
    next.splice(index, 1);
    updateField(["levels", activeLevel, "openings"], next);
  }

  function addConnection(kind = "door", width = 3) {
    const subject = subjectSpaceId();
    const target = connectionTargetSpaceId(subject);
    if (!subject || !target) {
      return;
    }
    updateField(["levels", activeLevel, "connections"], [
      ...connections,
      { between: [subject, target], kind, width }
    ]);
  }

  function canAddConnection() {
    const subject = subjectSpaceId();
    const target = connectionTargetSpaceId(subject);
    if (!subject || !target) {
      return false;
    }
    const wallPair = selectedWallSpacePair();
    return !wallPair || !connections.some((item) => relationIncludesPair(connectionData(item), wallPair));
  }

  function updateAccessAt(index: number, value: string) {
    updateField(["levels", activeLevel, "access", index], splitList(value));
  }

  function updateAccessOtherEndpoint(index: number, value: string) {
    const subject = subjectSpaceId();
    updateField(["levels", activeLevel, "access", index], subject ? [subject, value] : splitList(value));
  }

  function updateConstraintAt(kind: "stacks" | "alignments", index: number, field: string, value: unknown) {
    updateField([kind, index, field], value);
  }

  function sameLabel(value: unknown) {
    const key = sameKey(value);
    return sameOptions.find((option) => option.value === key)?.label ?? `Custom (${key})`;
  }

  function updateConstraintSame(kind: "stacks" | "alignments", index: number, value: string) {
    updateConstraintAt(kind, index, "same", splitList(value));
  }

  function updateConstraintMember(kind: "stacks" | "alignments", index: number, memberIndex: number, value: string) {
    const source = kind === "stacks" ? stacks[index] : alignments[index];
    const members = Array.isArray(source?.members) ? [...source.members] : [];
    members[memberIndex] = value;
    updateConstraintAt(kind, index, "members", members.filter(Boolean));
  }

  function constraintMemberLabel(value: string) {
    return constraintRefs.find((ref) => ref.value === value)?.label ?? value;
  }

  function selectedRef() {
    return selected.level && selected.id ? `${selected.level}.${selected.id}` : "";
  }

  function selectedDatumRows(): DatumRow[] {
    if (selected.kind === "wall") {
      return wallDatumRows(selected.id);
    }
    if (selected.kind !== "space" || !selectedObject) {
      return [];
    }
    const rows: DatumRow[] = [];
    const label = spaceDisplayName(selected.id);
    if (Array.isArray(selectedObject.x)) {
      rows.push(datumRow(`${label} West`, "x", selectedObject.x[0], ["levels", activeLevel, "spaces", selected.id, "x", 0]));
      rows.push(datumRow(`${label} East`, "x", selectedObject.x[1], ["levels", activeLevel, "spaces", selected.id, "x", 1]));
    }
    if (Array.isArray(selectedObject.y)) {
      rows.push(datumRow(`${label} North`, "y", selectedObject.y[0], ["levels", activeLevel, "spaces", selected.id, "y", 0]));
      rows.push(datumRow(`${label} South`, "y", selectedObject.y[1], ["levels", activeLevel, "spaces", selected.id, "y", 1]));
    }
    return rows.filter((row) => typeof row.name === "string");
  }

  function wallDatumRows(wallId: string): DatumRow[] {
    const contained = wallId.match(/^(.+)__(.+)_(north|east|south|west)_wall$/);
    if (contained) {
      const innerId = contained[2];
      const side = contained[3];
      const row = spaceEdgeDatumRow(innerId, side);
      return row ? [row] : [];
    }
    const shared = wallId.match(/^(.+)__(.+)_wall$/);
    if (!shared) {
      return exteriorWallDatumRows();
    }
    const firstId = shared[1];
    const secondId = shared[2];
    const first = spaceRect(firstId);
    const second = spaceRect(secondId);
    if (!first || !second) {
      return [];
    }
    const rows: DatumRow[] = [];
    if (Math.abs(first.right - second.left) < 0.01) {
      rows.push(...compactRows(spaceEdgeDatumRow(firstId, "east"), spaceEdgeDatumRow(secondId, "west")));
    } else if (Math.abs(second.right - first.left) < 0.01) {
      rows.push(...compactRows(spaceEdgeDatumRow(firstId, "west"), spaceEdgeDatumRow(secondId, "east")));
    } else if (Math.abs(first.bottom - second.top) < 0.01) {
      rows.push(...compactRows(spaceEdgeDatumRow(firstId, "south"), spaceEdgeDatumRow(secondId, "north")));
    } else if (Math.abs(second.bottom - first.top) < 0.01) {
      rows.push(...compactRows(spaceEdgeDatumRow(firstId, "north"), spaceEdgeDatumRow(secondId, "south")));
    }
    return rows;
  }

  function exteriorWallDatumRows(): DatumRow[] {
    return uniqueDatumRows([...massEdgeDatumRows(), ...adjacentSpaceDatumRows()]);
  }

  function massEdgeDatumRows(): DatumRow[] {
    const masses = (planData.masses ?? {}) as AnyRecord;
    const rows: DatumRow[] = [];
    for (const ref of selectedWallEdgeRefs) {
      const mass = masses[ref.massId] as AnyRecord | undefined;
      const rect = ref.rectIndex === null ? mass?.rect : mass?.rects?.[ref.rectIndex ?? 0];
      if (!rect || !Array.isArray(rect.x) || !Array.isArray(rect.y)) {
        continue;
      }
      const axis: "x" | "y" = ref.edge === "left" || ref.edge === "right" ? "x" : "y";
      const edgeIndex: 0 | 1 = ref.edge === "left" || ref.edge === "top" ? 0 : 1;
      const path =
        ref.rectIndex === null
          ? ["masses", ref.massId, "rect", axis, edgeIndex]
          : ["masses", ref.massId, "rects", ref.rectIndex, axis, edgeIndex];
      const label = `${ref.massId}${ref.rectIndex === null ? "" : ` #${ref.rectIndex + 1}`} ${edgeDisplayName(ref.edge)}`;
      rows.push(datumRow(label, axis, rect[axis][edgeIndex], path));
    }
    return rows;
  }

  function adjacentSpaceDatumRows(): DatumRow[] {
    if (!selectedWallLine) {
      return [];
    }
    const horizontal = Math.abs(selectedWallLine.y1 - selectedWallLine.y2) < 0.01;
    const vertical = Math.abs(selectedWallLine.x1 - selectedWallLine.x2) < 0.01;
    if (!horizontal && !vertical) {
      return [];
    }
    const rows: DatumRow[] = [];
    for (const [spaceId] of spaces) {
      const rect = spaceRect(spaceId);
      if (!rect) {
        continue;
      }
      if (horizontal) {
        const y = selectedWallLine.y1;
        const left = Math.min(selectedWallLine.x1, selectedWallLine.x2);
        const right = Math.max(selectedWallLine.x1, selectedWallLine.x2);
        if (intervalOverlaps(rect.left, rect.right, left, right)) {
          if (Math.abs(rect.top - y) < 0.02) {
            rows.push(...compactRows(spaceEdgeDatumRow(spaceId, "north")));
          }
          if (Math.abs(rect.bottom - y) < 0.02) {
            rows.push(...compactRows(spaceEdgeDatumRow(spaceId, "south")));
          }
        }
      }
      if (vertical) {
        const x = selectedWallLine.x1;
        const top = Math.min(selectedWallLine.y1, selectedWallLine.y2);
        const bottom = Math.max(selectedWallLine.y1, selectedWallLine.y2);
        if (intervalOverlaps(rect.top, rect.bottom, top, bottom)) {
          if (Math.abs(rect.left - x) < 0.02) {
            rows.push(...compactRows(spaceEdgeDatumRow(spaceId, "west")));
          }
          if (Math.abs(rect.right - x) < 0.02) {
            rows.push(...compactRows(spaceEdgeDatumRow(spaceId, "east")));
          }
        }
      }
    }
    return rows;
  }

  function uniqueDatumRows(rows: DatumRow[]) {
    const seen = new Set<string>();
    return rows.filter((row) => {
      const key = row.path.join("|");
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  function intervalOverlaps(a1: number, a2: number, b1: number, b2: number) {
    return Math.min(a2, b2) - Math.max(a1, b1) > 0.02;
  }

  function edgeDisplayName(edge: MassEdgeRef["edge"]) {
    return edge === "left" ? "West" : edge === "right" ? "East" : edge === "top" ? "North" : "South";
  }

  function compactRows(...rows: Array<DatumRow | null>) {
    return rows.filter((row): row is DatumRow => Boolean(row));
  }

  function spaceEdgeDatumRow(spaceId: string, side: string): DatumRow | null {
    const space = spaces.find(([id]) => id === spaceId)?.[1];
    if (!space) {
      return null;
    }
    if (side === "west" && Array.isArray(space.x)) {
      return datumRow(`${spaceDisplayName(spaceId)} West`, "x", space.x[0], ["levels", activeLevel, "spaces", spaceId, "x", 0]);
    }
    if (side === "east" && Array.isArray(space.x)) {
      return datumRow(`${spaceDisplayName(spaceId)} East`, "x", space.x[1], ["levels", activeLevel, "spaces", spaceId, "x", 1]);
    }
    if (side === "north" && Array.isArray(space.y)) {
      return datumRow(`${spaceDisplayName(spaceId)} North`, "y", space.y[0], ["levels", activeLevel, "spaces", spaceId, "y", 0]);
    }
    if (side === "south" && Array.isArray(space.y)) {
      return datumRow(`${spaceDisplayName(spaceId)} South`, "y", space.y[1], ["levels", activeLevel, "spaces", spaceId, "y", 1]);
    }
    return null;
  }

  function datumRow(label: string, axis: "x" | "y", name: unknown, path: Array<string | number>): DatumRow {
    const datumName = String(name ?? "");
    const numeric = Number(name);
    const linked = typeof name === "string" && Number.isNaN(numeric);
    return { label, axis, name: datumName, value: linked ? datums[axis]?.[datumName] : numeric, linked, path };
  }

  function updateDatumRowValue(row: DatumRow, value: string) {
    if (row.linked) {
      updateNumber(["datums", row.axis, row.name], value);
    } else {
      updateNumber(row.path, value);
    }
  }

  function createDatumForRow(row: DatumRow) {
    const suggestedName = uniqueDatumName(row);
    const requestedName = window.prompt("New datum name", suggestedName);
    if (requestedName === null) {
      return;
    }
    const datumName = uniqueDatumName(row, requestedName);
    const value = Number(row.value);
    updateField(["datums", row.axis, datumName], Number.isNaN(value) ? 0 : value);
    updateDatumReference(row, datumName);
  }

  function uniqueDatumName(row: DatumRow, preferredName = "") {
    const existing = new Set(datumOptions(row.axis));
    const base = cleanDatumName(preferredName || row.label);
    let name = base;
    let index = 2;
    while (existing.has(name)) {
      name = `${base}_${index}`;
      index += 1;
    }
    return name;
  }

  function cleanDatumName(label: string) {
    const directionSuffix: Record<string, string> = { west: "w", east: "e", north: "n", south: "s" };
    const parts = label
      .toLowerCase()
      .replace(/[/#]+/g, " ")
      .split(/[^a-z0-9]+/)
      .filter(Boolean);
    const last = parts[parts.length - 1] ?? "datum";
    if (directionSuffix[last]) {
      parts[parts.length - 1] = directionSuffix[last];
    }
    return (parts.join("_") || "datum").replace(/_+/g, "_");
  }

  function changeDatumSelection(row: DatumRow, value: string) {
    if (value === "__new") {
      createDatumForRow(row);
      return;
    }
    linkDatumRow(row, value);
  }

  function linkDatumRow(row: DatumRow, datumName: string) {
    if (!datumName) {
      return;
    }
    updateDatumReference(row, datumName);
  }

  function updateDatumReference(row: DatumRow, datumName: string) {
    for (const path of constrainedDatumPaths(row)) {
      updateField(path, datumName);
    }
  }

  function constrainedDatumPaths(row: DatumRow) {
    const paths = [row.path];
    const parsed = parseSpaceDatumPath(row.path);
    if (!parsed) {
      return paths;
    }
    const sourceRef = `${parsed.levelId}.${parsed.spaceId}`;
    for (const stack of stacks) {
      const members = Array.isArray(stack.members) ? stack.members : [];
      if (!members.includes(sourceRef) || !stackConstrainsDatumEdge(stack, parsed.axis, parsed.edgeIndex)) {
        continue;
      }
      for (const member of members) {
        if (member === sourceRef || typeof member !== "string" || !member.includes(".")) {
          continue;
        }
        const [levelId, spaceId] = member.split(".", 2);
        const space = ((planData.levels as AnyRecord | undefined)?.[levelId]?.spaces ?? {})[spaceId] as AnyRecord | undefined;
        if (Array.isArray(space?.[parsed.axis])) {
          paths.push(["levels", levelId, "spaces", spaceId, parsed.axis, parsed.edgeIndex]);
        }
      }
    }
    return uniquePaths(paths);
  }

  function parseSpaceDatumPath(
    path: Array<string | number>
  ): { levelId: string; spaceId: string; axis: "x" | "y"; edgeIndex: 0 | 1 } | null {
    if (path.length !== 6 || path[0] !== "levels" || path[2] !== "spaces") {
      return null;
    }
    const [_, levelId, __, spaceId, axis, edgeIndex] = path;
    if (typeof levelId !== "string" || typeof spaceId !== "string" || (axis !== "x" && axis !== "y") || (edgeIndex !== 0 && edgeIndex !== 1)) {
      return null;
    }
    return { levelId, spaceId, axis, edgeIndex };
  }

  function stackConstrainsDatumEdge(stack: AnyRecord, axis: "x" | "y", edgeIndex: 0 | 1) {
    const same = Array.isArray(stack.same) ? stack.same : [];
    if (same.includes("bbox")) {
      return true;
    }
    if (axis === "x") {
      return edgeIndex === 0 ? same.includes("x") || same.includes("w") : same.includes("w");
    }
    return edgeIndex === 0 ? same.includes("y") || same.includes("h") : same.includes("h");
  }

  function uniquePaths(paths: Array<Array<string | number>>) {
    const seen = new Set<string>();
    return paths.filter((path) => {
      const key = path.join("|");
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  function datumOptions(axis: "x" | "y") {
    return Object.keys(datums[axis] ?? {});
  }

  function addPartitionWall(direction: "vertical" | "horizontal") {
    if (selected.kind !== "space") {
      return;
    }
    const rect = spaceRect(selected.id);
    if (!rect) {
      return;
    }
    const id = uniqueListId(partitions, "partition");
    const partition =
      direction === "vertical"
        ? { id, from: [roundHalf((rect.left + rect.right) / 2), roundHalf(rect.top)], to: [roundHalf((rect.left + rect.right) / 2), roundHalf(rect.bottom)] }
        : { id, from: [roundHalf(rect.left), roundHalf((rect.top + rect.bottom) / 2)], to: [roundHalf(rect.right), roundHalf((rect.top + rect.bottom) / 2)] };
    updateField(["levels", activeLevel, "partitions"], [...partitions, partition]);
  }

  function removeSelectedWall() {
    if (selected.kind !== "wall") {
      return;
    }
    const partitionIndex = partitions.findIndex((partition) => partition.id === selected.id);
    if (partitionIndex >= 0) {
      const next = partitions.slice();
      next.splice(partitionIndex, 1);
      updateField(["levels", activeLevel, "partitions"], next);
      return;
    }
    const length = selectedWallLength(selected.id);
    if (!length) {
      return;
    }
    const pair = selectedWallSpacePair();
    if (pair) {
      const connectionIndex = connections.findIndex((item) => relationIncludesPair(connectionData(item), pair));
      const fullWidth = roundHalf(length);
      if (connectionIndex >= 0) {
        const next = connections.slice();
        next[connectionIndex] = { ...connectionData(next[connectionIndex]), between: pair, kind: "open", width: fullWidth };
        updateField(["levels", activeLevel, "connections"], next);
        return;
      }
      addConnection("open", fullWidth);
      return;
    }
    const openingId = uniqueListId(openings, `${selected.id}_open`);
    updateField(["levels", activeLevel, "openings"], [
      ...openings,
      { id: openingId, wall: selected.id, offset: 0, width: roundHalf(length), kind: "open" }
    ]);
  }

  function selectedWallCanBeRemoved() {
    return selected.kind === "wall" && (partitions.some((partition) => partition.id === selected.id) || Boolean(selectedWallLength(selected.id)));
  }

  function selectedWallSpacePair(): [string, string] | null {
    return selected.kind === "wall" ? wallSpacePair(selected.id) : null;
  }

  function wallSpacePair(wallId: string): [string, string] | null {
    if (wallId.match(/^(.+)__(.+)_(north|east|south|west)_wall$/)) {
      return null;
    }
    const shared = wallId.match(/^(.+)__(.+)_wall$/);
    if (!shared) {
      return null;
    }
    const pair: [string, string] = [shared[1], shared[2]];
    if (!spaceRect(pair[0]) || !spaceRect(pair[1]) || selectedWallLength(wallId) <= 0) {
      return null;
    }
    return pair;
  }

  function selectedWallLength(wallId: string) {
    const contained = wallId.match(/^(.+)__(.+)_(north|east|south|west)_wall$/);
    if (contained) {
      const inner = spaceRect(contained[2]);
      if (!inner) {
        return 0;
      }
      return contained[3] === "north" || contained[3] === "south" ? inner.right - inner.left : inner.bottom - inner.top;
    }
    const shared = wallId.match(/^(.+)__(.+)_wall$/);
    if (!shared) {
      return 0;
    }
    const first = spaceRect(shared[1]);
    const second = spaceRect(shared[2]);
    if (!first || !second) {
      return 0;
    }
    if (Math.abs(first.right - second.left) < 0.01 || Math.abs(second.right - first.left) < 0.01) {
      return Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
    }
    if (Math.abs(first.bottom - second.top) < 0.01 || Math.abs(second.bottom - first.top) < 0.01) {
      return Math.min(first.right, second.right) - Math.max(first.left, second.left);
    }
    return 0;
  }

  function adjacentSpaceIds(spaceId: string) {
    const rect = spaceRect(spaceId);
    if (!rect) {
      return [];
    }
    return spaces
      .filter(([otherId]) => otherId !== spaceId)
      .filter(([otherId]) => {
        const other = spaceRect(otherId);
        if (!other) {
          return false;
        }
        const verticalTouch =
          (Math.abs(rect.right - other.left) < 0.01 || Math.abs(other.right - rect.left) < 0.01) &&
          Math.min(rect.bottom, other.bottom) - Math.max(rect.top, other.top) > 0.01;
        const horizontalTouch =
          (Math.abs(rect.bottom - other.top) < 0.01 || Math.abs(other.bottom - rect.top) < 0.01) &&
          Math.min(rect.right, other.right) - Math.max(rect.left, other.left) > 0.01;
        return verticalTouch || horizontalTouch;
      })
      .map(([otherId]) => otherId);
  }

  function connectionTargetSpaceId(subject: string) {
    const wallPair = selectedWallSpacePair();
    if (wallPair) {
      return wallPair.find((spaceId) => spaceId !== subject) ?? "";
    }
    return adjacentSpaceIds(subject)[0] ?? spaces.find(([spaceId]) => spaceId !== subject)?.[0] ?? "";
  }

  function spaceRect(spaceId: string) {
    const space = spaces.find(([id]) => id === spaceId)?.[1];
    if (!space) {
      return null;
    }
    if (Array.isArray(space.rect)) {
      const [x, y, w, h] = space.rect.map(Number);
      return { left: x, right: x + w, top: y, bottom: y + h };
    }
    if (Array.isArray(space.x) && Array.isArray(space.y)) {
      const left = datumValue("x", space.x[0]);
      const right = datumValue("x", space.x[1]);
      const top = datumValue("y", space.y[0]);
      const bottom = datumValue("y", space.y[1]);
      if ([left, right, top, bottom].some((value) => Number.isNaN(value))) {
        return null;
      }
      return {
        left: Math.min(left, right),
        right: Math.max(left, right),
        top: Math.min(top, bottom),
        bottom: Math.max(top, bottom)
      };
    }
    return null;
  }

  function datumValue(axis: "x" | "y", value: unknown) {
    if (typeof value === "number") {
      return value;
    }
    if (typeof value === "string") {
      const numeric = Number(value);
      if (!Number.isNaN(numeric)) {
        return numeric;
      }
      return Number(datums[axis]?.[value]);
    }
    return Number.NaN;
  }

  function selectedSpaceIds(): string[] {
    if (selected.level !== activeLevel) {
      return [];
    }
    if (selected.kind === "space") {
      return [selected.id];
    }
    if (selected.kind === "opening" && selectedObject?.space) {
      return [selectedObject.space];
    }
    if (selected.kind === "connection" && connection?.between) {
      return connection.between;
    }
    const wallPair = selectedWallSpacePair();
    if (wallPair) {
      return wallPair;
    }
    return [];
  }

  function connectionIsScoped(item: AnyRecord | string[], index: number) {
    if (selected.kind === "connection" && selected.level === activeLevel) {
      return connectionIndex() === index;
    }
    const wallPair = selectedWallSpacePair();
    if (wallPair) {
      return relationIncludesPair(connectionData(item), wallPair);
    }
    const ids = selectedSpaceIds();
    return ids.length > 0 && ids.some((id) => connectionData(item).between?.includes?.(id));
  }

  function openingIsScoped(item: AnyRecord, index: number) {
    if (selected.kind === "opening" && selected.level === activeLevel) {
      return (selected.index ?? -1) === index;
    }
    if (selected.kind === "wall") {
      return item.wall === selected.id;
    }
    return false;
  }

  function accessIsScoped(item: AnyRecord | string[]) {
    const wallPair = selectedWallSpacePair();
    if (wallPair) {
      return relationIncludesPair(accessData(item), wallPair);
    }
    const ids = selectedSpaceIds();
    return ids.length > 0 && ids.some((id) => accessData(item).between?.includes?.(id));
  }

  function constraintIsScoped(item: AnyRecord) {
    return item.members?.includes?.(selectedRef());
  }

  function spaceDisplayName(id: string) {
    const space = spaces.find(([spaceId]) => spaceId === id)?.[1];
    return space?.label || id;
  }

  function selectedDisplayName() {
    if (!selected.kind) {
      return "Related";
    }
    if (selected.kind === "space") {
      return spaceDisplayName(selected.id);
    }
    if (selected.kind === "opening" && selectedObject?.space) {
      return spaceDisplayName(selectedObject.space);
    }
    if (selected.kind === "stair") {
      return selected.id;
    }
    return selectedObject?.label || selected.id;
  }

  function subjectSpaceId() {
    return selectedSpaceIds()[0] ?? "";
  }

  function otherConnectionEndpoint(item: AnyRecord | string[]) {
    const subject = subjectSpaceId();
    const between = connectionData(item).between ?? [];
    return between.find((id: string) => id !== subject) ?? between[0] ?? "";
  }

  function otherAccessEndpoint(item: AnyRecord | string[]) {
    const subject = subjectSpaceId();
    const between = accessData(item).between ?? [];
    return between.find((id: string) => id !== subject) ?? between[0] ?? "";
  }

  function connectionDisplayName(item: AnyRecord | string[]) {
    const other = otherConnectionEndpoint(item);
    return `Connection to ${spaceDisplayName(other)}`;
  }

  function updateConnectionOtherEndpoint(index: number, value: string) {
    const subject = subjectSpaceId();
    updateConnectionAt(index, "between", subject ? [subject, value] : splitList(value));
  }
</script>

<PulloutTab {open} variant="inspector" icon="search" labelOpen="Hide inspector" labelClosed="Show inspector" {onToggle} />

<aside class:open class="inspector">
  <div class="properties-grid">
    <section class="panel inspector-main">
      <InspectorHeader {selected} onRemove={selected.kind === "wall" ? removeSelectedWall : deleteSelected} />

      {#if selected.kind === "space" && selectedObject}
        <div class="field-label">ID</div>
        <input value={selected.id} disabled />
        <div class="field-label">Label</div>
        <input
          value={selectedObject.label ?? ""}
          on:input={(event) =>
            updateField(["levels", selected.level, "spaces", selected.id, "label"], event.currentTarget.value)}
        />
        <div class="field-label">Privacy</div>
        <select
          value={selectedObject.privacy ?? ""}
          on:change={(event) =>
            updateField(["levels", selected.level, "spaces", selected.id, "privacy"], event.currentTarget.value)}
        >
          <option value="">unset</option>
          <option value="public">public</option>
          <option value="semi_private">semi_private</option>
          <option value="private">private</option>
          <option value="service">service</option>
          <option value="circulation">circulation</option>
        </select>

        <div class="field-label">Walls</div>
        <div class="button-row">
          <button type="button" on:click={() => addPartitionWall("vertical")}>Add vertical</button>
          <button type="button" on:click={() => addPartitionWall("horizontal")}>Add horizontal</button>
        </div>

        {#if Array.isArray(selectedObject.rect)}
          <div class="field-grid">
            {#each ["x", "y", "w", "h"] as field, index}
              <label>{field}<input type="number" step="0.5" value={selectedObject.rect[index]} on:input={(event) => updateNumber(["levels", selected.level, "spaces", selected.id, "rect", index], event.currentTarget.value)} /></label>
            {/each}
          </div>
        {:else}
          <div class="field-label">x datums</div>
          <input
            value={(selectedObject.x ?? []).join(", ")}
            on:input={(event) =>
              updateField(["levels", selected.level, "spaces", selected.id, "x"], splitList(event.currentTarget.value))}
          />
          <div class="field-label">y datums</div>
          <input
            value={(selectedObject.y ?? []).join(", ")}
            on:input={(event) =>
              updateField(["levels", selected.level, "spaces", selected.id, "y"], splitList(event.currentTarget.value))}
          />
        {/if}
      {:else if selected.kind === "feature" && selectedObject}
        {#key selectedFeatureKey}
          <div class="field-label">ID</div>
          <input value={selected.id} disabled />
          <div class="field-label">Kind</div>
          <select value={effectiveSelectedFeature.kind ?? "rectangle"} on:change={(event) => updateFeatureKind(event.currentTarget.value)}>
            {#if effectiveSelectedFeature.kind && !featureKindOptions.some((option) => option.value === effectiveSelectedFeature.kind)}
              <option value={effectiveSelectedFeature.kind}>{effectiveSelectedFeature.kind}</option>
            {/if}
            {#each featureKindOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
          <div class="field-label">Label</div>
          <input
            value={featureLabel}
            on:input={(event) =>
              updateField(["levels", selected.level, "features", selected.id, "label"], event.currentTarget.value)}
          />
          <div class="field-label">Within</div>
          <select
            value={effectiveSelectedFeature.within ?? ""}
            on:change={(event) => updateFeatureWithin(event.currentTarget.value)}
          >
            <option value="">unset</option>
            {#each spaces as [spaceId]}
              <option value={spaceId}>{spaceId}</option>
            {/each}
          </select>
          <div class="field-grid">
            <label>x<input type="number" step="0.5" bind:value={featureXValue} on:input={(event) => updateFeatureNumber("x", event.currentTarget.value)} /></label>
            <label>y<input type="number" step="0.5" bind:value={featureYValue} on:input={(event) => updateFeatureNumber("y", event.currentTarget.value)} /></label>
            <label>w<input type="number" step="0.5" bind:value={featureWidthValue} on:input={(event) => updateFeatureNumber("w", event.currentTarget.value)} /></label>
            <label>h<input type="number" step="0.5" bind:value={featureHeightValue} on:input={(event) => updateFeatureNumber("h", event.currentTarget.value)} /></label>
          </div>
          <div class="field-label">Rotation</div>
          <input
            type="number"
            step="1"
            value={featureRotation}
            on:input={(event) =>
              updateNumber(["levels", selected.level, "features", selected.id, "rotation"], event.currentTarget.value)}
          />
          <div class="field-label">Margin</div>
          <input type="number" step="0.5" value={featureMargin} on:input={(event) => updateFeatureMargin(event.currentTarget.value)} />
        {/key}
      {:else if selected.kind === "opening" && selectedObject}
        <div class="field-label">ID</div>
        <input
          value={selectedObject.id ?? ""}
          on:input={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "id"], event.currentTarget.value)}
        />
        <div class="field-label">Kind</div>
        <select
          value={selectedObject.kind ?? "window"}
          on:change={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "kind"], event.currentTarget.value)}
        >
          <option value="window">window</option>
          <option value="door">door</option>
          <option value="arch">arch</option>
          <option value="open">open</option>
        </select>
        <div class="field-label">Space</div>
        <input
          value={selectedObject.space ?? ""}
          on:input={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "space"], event.currentTarget.value)}
        />
        <div class="field-label">Side</div>
        <select
          value={selectedObject.side ?? "north"}
          on:change={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "side"], event.currentTarget.value)}
        >
          <option value="north">north</option>
          <option value="east">east</option>
          <option value="south">south</option>
          <option value="west">west</option>
        </select>
        <div class="field-label">Width</div>
        <input type="number" step="0.5" value={selectedObject.width ?? 3} on:input={(event) => updateNumber(["levels", selected.level, "openings", selected.index ?? 0, "width"], event.currentTarget.value)} />
      {:else if selected.kind === "connection" && connection}
        <div class="field-label">Connection</div>
        <input value={`#${connectionIndex() + 1}`} disabled />
        <div class="field-label">Kind</div>
        <select
          value={connection.kind ?? "door"}
          on:change={(event) => updateConnectionField("kind", event.currentTarget.value)}
        >
          <option value="door">door</option>
          <option value="open">open</option>
          <option value="arch">arch</option>
        </select>
        <div class="field-label">Between</div>
        <input
          value={(connection.between ?? []).join(", ")}
          on:input={(event) => updateConnectionField("between", splitList(event.currentTarget.value))}
        />
        <div class="field-label">Width</div>
        <input type="number" step="0.5" value={connection.width ?? 3} on:input={(event) => updateConnectionNumber("width", event.currentTarget.value)} />
        <div class="field-label">Offset</div>
        <input type="number" step="0.5" value={connection.offset ?? ""} on:input={(event) => updateConnectionNumber("offset", event.currentTarget.value)} />
        <div class="field-label">Position</div>
        <select
          value={connection.position ?? ""}
          on:change={(event) => updateConnectionField("position", event.currentTarget.value || undefined)}
        >
          <option value="">center</option>
          <option value="start">start</option>
          <option value="end">end</option>
        </select>
        <div class="field-label">Swing</div>
        <select
          value={connection.swing ?? ""}
          on:change={(event) => updateConnectionField("swing", event.currentTarget.value || undefined)}
        >
          <option value="">unset</option>
          <option value="in-left">in-left</option>
          <option value="in-right">in-right</option>
          <option value="out-left">out-left</option>
          <option value="out-right">out-right</option>
        </select>
      {:else if selected.kind === "stair" && selectedStair}
        <div class="field-label">ID</div>
        <input value={selected.id} disabled />

        <div class="field-label">Spaces</div>
        <div class="field-grid stair-field-grid">
          <label>lower<input value={selectedStair.spaces?.lower ?? ""} on:input={(event) => updateField(["stairs", selected.id, "spaces", "lower"], event.currentTarget.value)} /></label>
          <label>upper<input value={selectedStair.spaces?.upper ?? ""} on:input={(event) => updateField(["stairs", selected.id, "spaces", "upper"], event.currentTarget.value)} /></label>
        </div>

        <div class="field-label">Dimensions</div>
        <div class="field-grid stair-field-grid">
          <label>width<input type="number" step="0.5" value={selectedStair.width ?? 3} on:input={(event) => updateStairNumber(["width"], event.currentTarget.value)} /></label>
          <label>story<input type="number" step="0.5" value={storyHeight} on:input={(event) => updateStoryHeight(event.currentTarget.value)} /></label>
        </div>

        <div class="field-label">Lower Entry</div>
        <div class="field-grid stair-field-grid">
          <label>from<input value={selectedStair.lower_entry?.from ?? ""} on:input={(event) => updateField(["stairs", selected.id, "lower_entry", "from"], event.currentTarget.value)} /></label>
          <label>side
            <select value={selectedStair.lower_entry?.side ?? "south"} on:change={(event) => updateField(["stairs", selected.id, "lower_entry", "side"], event.currentTarget.value)}>
              {#each sideOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>pos
            <select value={selectedStair.lower_entry?.position ?? "east"} on:change={(event) => updateField(["stairs", selected.id, "lower_entry", "position"], event.currentTarget.value)}>
              {#each positionOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>kind
            <select value={selectedStair.lower_entry?.kind ?? "arch"} on:change={(event) => updateField(["stairs", selected.id, "lower_entry", "kind"], event.currentTarget.value)}>
              {#each openingKindOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>width<input type="number" step="0.5" value={selectedStair.lower_entry?.width ?? 3} on:input={(event) => updateStairNumber(["lower_entry", "width"], event.currentTarget.value)} /></label>
        </div>

        <div class="field-label">Upper Exit</div>
        <div class="field-grid stair-field-grid">
          <label>to<input value={selectedStair.upper_exit?.to ?? ""} on:input={(event) => updateField(["stairs", selected.id, "upper_exit", "to"], event.currentTarget.value)} /></label>
          <label>side
            <select value={selectedStair.upper_exit?.side ?? "south"} on:change={(event) => updateField(["stairs", selected.id, "upper_exit", "side"], event.currentTarget.value)}>
              {#each sideOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>pos
            <select value={selectedStair.upper_exit?.position ?? "west"} on:change={(event) => updateField(["stairs", selected.id, "upper_exit", "position"], event.currentTarget.value)}>
              {#each positionOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>kind
            <select value={selectedStair.upper_exit?.kind ?? "arch"} on:change={(event) => updateField(["stairs", selected.id, "upper_exit", "kind"], event.currentTarget.value)}>
              {#each openingKindOptions as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
          </label>
          <label>width<input type="number" step="0.5" value={selectedStair.upper_exit?.width ?? 3} on:input={(event) => updateStairNumber(["upper_exit", "width"], event.currentTarget.value)} /></label>
        </div>

        <div class="field-label">Steps</div>
        <div class="field-grid stair-field-grid">
          <label>rise<input type="number" step="0.25" value={selectedStair.steps?.target?.rise_in ?? 7} on:input={(event) => updateStairNumber(["steps", "target", "rise_in"], event.currentTarget.value)} /></label>
          <label>run<input type="number" step="0.25" value={selectedStair.steps?.target?.run_in ?? 13} on:input={(event) => updateStairNumber(["steps", "target", "run_in"], event.currentTarget.value)} /></label>
          <label>minR<input type="number" step="0.25" value={selectedStair.steps?.limits?.rise_in?.[0] ?? 6.5} on:input={(event) => updateStairNumber(["steps", "limits", "rise_in", 0], event.currentTarget.value)} /></label>
          <label>maxR<input type="number" step="0.25" value={selectedStair.steps?.limits?.rise_in?.[1] ?? 8} on:input={(event) => updateStairNumber(["steps", "limits", "rise_in", 1], event.currentTarget.value)} /></label>
          <label>minT<input type="number" step="0.25" value={selectedStair.steps?.limits?.run_in?.[0] ?? 10} on:input={(event) => updateStairNumber(["steps", "limits", "run_in", 0], event.currentTarget.value)} /></label>
          <label>maxT<input type="number" step="0.25" value={selectedStair.steps?.limits?.run_in?.[1] ?? 13} on:input={(event) => updateStairNumber(["steps", "limits", "run_in", 1], event.currentTarget.value)} /></label>
          <label>min#
            <input type="number" step="1" value={selectedStair.steps?.min_treads_per_run ?? 2} on:input={(event) => updateStairNumber(["steps", "min_treads_per_run"], event.currentTarget.value)} />
          </label>
          <label>wind
            <input type="checkbox" checked={Boolean(selectedStair.layout?.winders)} on:change={(event) => updateField(["stairs", selected.id, "layout", "winders"], event.currentTarget.checked)} />
          </label>
        </div>
      {:else if selected.kind === "wall"}
        <p class="muted">Wall inspection is available. Wall moving uses constrained orthogonal handles for supported shared and exterior edges.</p>
        <dl>
          <dt>Wall</dt>
          <dd>{selected.id}</dd>
        </dl>
        <div class="field-label">Action</div>
        <div class="button-row">
          <button type="button" on:click={addWindowToSelectedWall}>Add window</button>
          <button type="button" disabled={!canAddConnection()} on:click={() => addConnection("door", 3)}>Add door</button>
          <button type="button" class="danger" disabled={!selectedWallCanBeRemoved()} on:click={removeSelectedWall}>Remove wall</button>
        </div>
      {:else}
        <p class="muted">Select a room, feature, opening, or wall.</p>
      {/if}
    </section>

    <section class="panel relations-panel">
      <div class="panel-title">
        <h2>{selected.kind ? `Related - ${selectedDisplayName()}` : "Related"}</h2>
        <span>{activeLevel}</span>
      </div>

      {#if !selected.kind}
        <p class="muted">Select an item to inspect its relations.</p>
      {:else if !hasScopedRelations}
        <p class="muted">No connections or constraints reference this item.</p>
      {/if}

      {#if scopedConnectionRows.length}
        <div class="relation-list">
          {#each scopedConnectionRows as { item, index }}
            {@const current = connectionData(item)}
            <div class="relation-card">
              <div class="relation-card-title">
                <button type="button" class="relation-heading" on:click={() => selectObject("connection", String(index), index)}>
                  {connectionDisplayName(item)}
                </button>
                <button type="button" class="relation-remove" aria-label="Remove connection" on:click={() => removeConnectionAt(index)}>x</button>
              </div>
              <div class="relation-fields">
                <div class="field-label">Kind</div>
                <select value={current.kind ?? "door"} on:change={(event) => updateConnectionAt(index, "kind", event.currentTarget.value)}>
                  <option value="door">door</option>
                  <option value="open">open</option>
                  <option value="arch">arch</option>
                </select>
                <div class="field-label">To</div>
                <select value={otherConnectionEndpoint(item)} on:change={(event) => updateConnectionOtherEndpoint(index, event.currentTarget.value)}>
                  {#each spaces as [spaceId]}
                    {#if spaceId !== subjectSpaceId()}
                      <option value={spaceId}>{spaceDisplayName(spaceId)}</option>
                    {/if}
                  {/each}
                </select>
                <div class="field-label">Width</div>
                <input type="number" step="0.5" value={current.width ?? ""} on:input={(event) => updateConnectionNumberAt(index, "width", event.currentTarget.value)} />
                <div class="field-label">Offset</div>
                <input type="number" step="0.5" value={current.offset ?? ""} on:input={(event) => updateConnectionNumberAt(index, "offset", event.currentTarget.value)} />
                <div class="field-label">Position</div>
                <select value={current.position ?? ""} on:change={(event) => updateConnectionAt(index, "position", event.currentTarget.value)}>
                  <option value="">center</option>
                  <option value="start">start</option>
                  <option value="end">end</option>
                </select>
                <div class="field-label">Swing</div>
                <select value={current.swing ?? ""} on:change={(event) => updateConnectionAt(index, "swing", event.currentTarget.value)}>
                  <option value="">unset</option>
                  <option value="in-left">in-left</option>
                  <option value="in-right">in-right</option>
                  <option value="out-left">out-left</option>
                  <option value="out-right">out-right</option>
                </select>
              </div>
            </div>
          {/each}
          {#if canAddConnection()}
            <button type="button" class="relation-add" on:click={() => addConnection()}>+</button>
          {/if}
        </div>
      {:else if canAddConnection()}
        <button type="button" class="relation-add" on:click={() => addConnection()}>+</button>
      {/if}

      {#if scopedOpeningRows.length}
        <div class="relation-list">
          {#each scopedOpeningRows as { item, index }}
            <div class="relation-card">
              <div class="relation-card-title">
                <button type="button" class="relation-heading" on:click={() => selectObject("opening", item.id, index)}>
                  Opening {item.id ?? index + 1}
                </button>
                <button type="button" class="relation-remove" aria-label="Remove opening" on:click={() => removeOpeningAt(index)}>x</button>
              </div>
              <div class="relation-fields">
                <div class="field-label">Kind</div>
                <select value={item.kind ?? "window"} on:change={(event) => updateOpeningAt(index, "kind", event.currentTarget.value)}>
                  <option value="window">window</option>
                  <option value="door">door</option>
                  <option value="arch">arch</option>
                  <option value="open">open</option>
                </select>
                <div class="field-label">Width</div>
                <input type="number" step="0.5" value={item.width ?? ""} on:input={(event) => updateOpeningNumberAt(index, "width", event.currentTarget.value)} />
                <div class="field-label">Offset</div>
                <input type="number" step="0.5" value={item.offset ?? ""} on:input={(event) => updateOpeningNumberAt(index, "offset", event.currentTarget.value)} />
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if scopedDatumRows.length}
        <div class="relation-list">
          <div class="relation-card">
            <div class="relation-card-title">
              <div class="relation-heading">Datums</div>
            </div>
            <div class="datum-fields">
              <div class="datum-header">datum label</div>
              <div class="datum-header">value</div>
              {#each scopedDatumRows as row}
                <div class="field-label">{row.label}</div>
                <label class="datum-pair">
                  <select class="datum-link" value={row.linked ? row.name : "__unlinked"} on:change={(event) => changeDatumSelection(row, event.currentTarget.value)}>
                    <option value="__new">new...</option>
                    {#if !row.linked}
                      <option value="__unlinked" disabled>unlinked</option>
                    {/if}
                    {#each datumOptions(row.axis) as datumName}
                      <option value={datumName}>{datumName}</option>
                    {/each}
                  </select>
                  <input type="number" step="0.5" value={row.value ?? ""} on:input={(event) => updateDatumRowValue(row, event.currentTarget.value)} />
                </label>
              {/each}
            </div>
          </div>
        </div>
      {/if}

      {#if scopedAccessRows.length}
        <h3>Access</h3>
        <div class="relation-list">
          {#each scopedAccessRows as { item, index }}
            <label class="relation-card relation-inline">To
              <select value={otherAccessEndpoint(item)} on:change={(event) => updateAccessOtherEndpoint(index, event.currentTarget.value)}>
                {#each spaces as [spaceId]}
                  {#if spaceId !== subjectSpaceId()}
                    <option value={spaceId}>{spaceDisplayName(spaceId)}</option>
                  {/if}
                {/each}
              </select>
            </label>
          {/each}
        </div>
      {/if}

      {#if scopedStackRows.length}
        <h3>Stacks</h3>
        <div class="relation-list">
          {#each scopedStackRows as { item, index }}
            <div class="relation-card">
              <div class="relation-fields">
                <div class="field-label">ID</div>
                <input value={item.id ?? ""} on:input={(event) => updateConstraintAt("stacks", index, "id", event.currentTarget.value)} />
                <div class="field-label">First</div>
                <select value={item.members?.[0] ?? ""} on:change={(event) => updateConstraintMember("stacks", index, 0, event.currentTarget.value)}>
                  <option value="">choose item</option>
                  {#if item.members?.[0] && !constraintRefs.some((ref) => ref.value === item.members[0])}
                    <option value={item.members[0]}>{constraintMemberLabel(item.members[0])}</option>
                  {/if}
                  {#each constraintRefs as ref}
                    <option value={ref.value}>{ref.label}</option>
                  {/each}
                </select>
                <div class="field-label">Second</div>
                <select value={item.members?.[1] ?? ""} on:change={(event) => updateConstraintMember("stacks", index, 1, event.currentTarget.value)}>
                  <option value="">choose item</option>
                  {#if item.members?.[1] && !constraintRefs.some((ref) => ref.value === item.members[1])}
                    <option value={item.members[1]}>{constraintMemberLabel(item.members[1])}</option>
                  {/if}
                  {#each constraintRefs as ref}
                    <option value={ref.value}>{ref.label}</option>
                  {/each}
                </select>
                <div class="field-label">Same</div>
                <select value={sameKey(item.same)} on:change={(event) => updateConstraintSame("stacks", index, event.currentTarget.value)}>
                  {#if sameKey(item.same) && !sameOptions.some((option) => option.value === sameKey(item.same))}
                    <option value={sameKey(item.same)}>{sameLabel(item.same)}</option>
                  {/if}
                  {#each sameOptions as option}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      {#if scopedAlignmentRows.length}
        <h3>Alignments</h3>
        <div class="relation-list">
          {#each scopedAlignmentRows as { item, index }}
            <div class="relation-card">
              <div class="relation-fields">
                <div class="field-label">ID</div>
                <input value={item.id ?? ""} on:input={(event) => updateConstraintAt("alignments", index, "id", event.currentTarget.value)} />
                <div class="field-label">First</div>
                <select value={item.members?.[0] ?? ""} on:change={(event) => updateConstraintMember("alignments", index, 0, event.currentTarget.value)}>
                  <option value="">choose item</option>
                  {#if item.members?.[0] && !constraintRefs.some((ref) => ref.value === item.members[0])}
                    <option value={item.members[0]}>{constraintMemberLabel(item.members[0])}</option>
                  {/if}
                  {#each constraintRefs as ref}
                    <option value={ref.value}>{ref.label}</option>
                  {/each}
                </select>
                <div class="field-label">Second</div>
                <select value={item.members?.[1] ?? ""} on:change={(event) => updateConstraintMember("alignments", index, 1, event.currentTarget.value)}>
                  <option value="">choose item</option>
                  {#if item.members?.[1] && !constraintRefs.some((ref) => ref.value === item.members[1])}
                    <option value={item.members[1]}>{constraintMemberLabel(item.members[1])}</option>
                  {/if}
                  {#each constraintRefs as ref}
                    <option value={ref.value}>{ref.label}</option>
                  {/each}
                </select>
                <div class="field-label">Same</div>
                <select value={sameKey(item.same)} on:change={(event) => updateConstraintSame("alignments", index, event.currentTarget.value)}>
                  {#if sameKey(item.same) && !sameOptions.some((option) => option.value === sameKey(item.same))}
                    <option value={sameKey(item.same)}>{sameLabel(item.same)}</option>
                  {/if}
                  {#each sameOptions as option}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  </div>
</aside>
