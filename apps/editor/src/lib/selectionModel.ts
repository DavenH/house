import { entries } from "./planEditing";
import type { AnyRecord, PlanData } from "./types";

export function buildConstraintRefs(source: PlanData) {
  const refs: Array<{ value: string; label: string }> = [];
  const levels = (source.levels as AnyRecord | undefined) ?? {};
  for (const [levelId, levelData] of Object.entries(levels)) {
    const levelRecord = levelData as AnyRecord;
    for (const [id, object] of entries(levelRecord.spaces)) {
      refs.push({ value: `${levelId}.${id}`, label: `${levelId} room: ${displayLabel(object.label || id)}` });
    }
    for (const [id, object] of entries(levelRecord.features)) {
      refs.push({
        value: `${levelId}.${id}`,
        label: `${levelId} feature: ${displayLabel(object.label || object.kind || id)}`
      });
    }
  }
  return refs;
}

function displayLabel(value: unknown) {
  return String(value).replace(/\//g, " ");
}
