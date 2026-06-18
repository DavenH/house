import type { AnyRecord } from "./types";

export type DatumRow = {
  label: string;
  axis: "x" | "y";
  name: string;
  value: unknown;
  linked: boolean;
  spaceId: string;
  edgeIndex: 0 | 1;
};

export function splitList(value: string) {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function relationData(item: AnyRecord | string[]) {
  return Array.isArray(item) ? { between: item } : item;
}

export function sameKey(value: unknown) {
  return Array.isArray(value) ? value.join(",") : "";
}

export function relationIncludesPair(item: AnyRecord, pair: [string, string]) {
  return pair.every((id) => item.between?.includes?.(id));
}

export function uniqueListId(items: AnyRecord[], prefix: string) {
  const existing = new Set(items.map((item) => item.id).filter(Boolean));
  let index = 1;
  let id = cleanId(prefix);
  while (existing.has(id)) {
    index += 1;
    id = cleanId(`${prefix}_${index}`);
  }
  return id;
}

export function roundHalf(value: number) {
  return Math.round(value * 2) / 2;
}

function cleanId(value: string) {
  return value.replace(/[^A-Za-z0-9_-]+/g, "_");
}
