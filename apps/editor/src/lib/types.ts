export type AnyRecord = Record<string, any>;

export type PlanData = AnyRecord & {
  levels?: Record<string, LevelData>;
  catalog?: Record<string, FeatureData>;
  datums?: Record<string, Record<string, number>>;
  stacks?: AnyRecord[];
  alignments?: AnyRecord[];
};

export type LevelData = AnyRecord & {
  spaces?: Record<string, SpaceData>;
  features?: Record<string, FeatureData>;
  connections?: Array<AnyRecord | string[]>;
  openings?: AnyRecord[];
  partitions?: AnyRecord[];
  access?: Array<AnyRecord | string[]>;
};

export type SpaceData = AnyRecord & {
  label?: string;
  rect?: number[];
  x?: Array<string | number>;
  y?: Array<string | number>;
};

export type FeatureData = AnyRecord & {
  kind?: string;
  label?: string;
  at?: [number, number];
  size?: [number, number];
  rotation?: number;
};

export type SelectionKind = "space" | "feature" | "opening" | "connection" | "wall" | "stair" | "level" | "";

export type Selection = {
  kind: SelectionKind;
  level: string;
  id: string;
  index?: number;
};

export type PaletteItem = {
  label: string;
  noun: "space" | "feature" | "opening" | "connection";
  kind?: string;
  openingKind?: string;
};

export type SpaceRect = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

export type WallLine = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type WallDirection = "N" | "E" | "S" | "W";

export type MassEdgeRef = {
  massId: string;
  rectIndex: number | null;
  edge: "left" | "right" | "top" | "bottom";
};

export type FeatureDrag = {
  type: "feature";
  id: string;
  level: string;
  startPoint: { x: number; y: number };
  startAt: [number, number];
  target: SVGGraphicsElement;
  snapshot: AnyRecord;
};

export type SharedWallDrag = {
  type: "wall";
  id: string;
  level: string;
  startPoint: { x: number; y: number };
  orientation: "vertical" | "horizontal";
  spaces: [string, string];
  startRects: [SpaceRect, SpaceRect];
  snapshot: AnyRecord;
};

export type ContainedWallDrag = {
  type: "contained-wall";
  id: string;
  level: string;
  startPoint: { x: number; y: number };
  orientation: "vertical" | "horizontal";
  innerSpace: string;
  edge: "left" | "right" | "top" | "bottom";
  startRect: SpaceRect;
  line: WallLine;
  snapshot: AnyRecord;
};

export type ExteriorWallDrag = {
  type: "exterior-wall";
  id: string;
  level: string;
  startPoint: { x: number; y: number };
  orientation: "vertical" | "horizontal";
  edgeRefs: MassEdgeRef[];
  line: WallLine;
  snapshot: AnyRecord;
};

export type OpeningDrag = {
  type: "opening";
  id: string;
  level: string;
  index: number;
  source: "opening" | "connection";
  preserveSpaceSide?: boolean;
  startPoint: { x: number; y: number };
  wall: string;
  direction: WallDirection;
  orientation: "vertical" | "horizontal";
  startOffset: number;
  width: number;
  wallLength: number;
  snapshot: AnyRecord;
};

export type DragState = FeatureDrag | SharedWallDrag | ContainedWallDrag | ExteriorWallDrag | OpeningDrag | null;
