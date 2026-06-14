import type { PaletteItem } from "./types";

export const palette: PaletteItem[] = [
  { label: "Room", noun: "space" },
  { label: "Piano", noun: "feature", kind: "piano_5x7" },
  { label: "Desk/Counter", noun: "feature", kind: "desk_counter" },
  { label: "Couch", noun: "feature", kind: "couch_7x3" },
  { label: "Chair", noun: "feature", kind: "chair_3x3" },
  { label: "Dining Table", noun: "feature", kind: "dining_table_3x7" },
  { label: "Refrigerator", noun: "feature", kind: "refrigerator" },
  { label: "Bed", noun: "feature", kind: "queen_bed" },
  { label: "Storage", noun: "feature", kind: "storage" },
  { label: "Window", noun: "opening", openingKind: "window" },
  { label: "Door", noun: "opening", openingKind: "door" },
  { label: "Arch", noun: "connection", openingKind: "arch" },
  { label: "Open Connection", noun: "connection", openingKind: "open" }
];
