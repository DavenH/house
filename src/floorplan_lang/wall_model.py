"""Domain objects for wall-segment-first floor plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from floorplan_lang.geometry import Point, Rect
from floorplan_lang.wall_geometry import Direction, direction_delta, direction_normal, direction_unit

EXTERIOR_WALL_THICKNESS_FT = 1.0
INTERIOR_WALL_STROKE_FT = 0.3
CLEARANCE_PALETTE = ("#a9d4dc", "#d2bde0", "#ddca9f", "#afd5ad", "#ddb2ae", "#b7c6e3")


@dataclass(frozen=True)
class WallSegment:
    id: str
    at: Point
    direction: Direction | None
    length: float
    kind: str = "interior"
    offset: float | None = None
    to: Point | None = None

    @property
    def end(self) -> Point:
        if self.to is not None:
            return self.to
        if self.direction is None:
            raise ValueError(f"Wall {self.id} needs either direction or endpoint")
        dx, dy = direction_delta(self.direction, self.length)
        return Point(self.at.x + dx, self.at.y + dy)

    @property
    def unit(self) -> tuple[float, float]:
        if self.to is not None:
            dx = self.to.x - self.at.x
            dy = self.to.y - self.at.y
            length = max((dx * dx + dy * dy) ** 0.5, 1e-9)
            return (dx / length, dy / length)
        if self.direction is None:
            raise ValueError(f"Wall {self.id} needs either direction or endpoint")
        return direction_unit(self.direction)

    @property
    def normal(self) -> tuple[float, float]:
        return direction_normal(self.unit)

    @property
    def is_axis_aligned(self) -> bool:
        return self.direction in {"N", "E", "S", "W"}

    @property
    def bbox(self) -> Rect:
        left = min(self.at.x, self.end.x)
        top = min(self.at.y, self.end.y)
        right = max(self.at.x, self.end.x)
        bottom = max(self.at.y, self.end.y)
        return Rect(left, top, max(right - left, 0.001), max(bottom - top, 0.001))

    def point_at(self, offset: float) -> Point:
        dx, dy = direction_delta(self.unit, offset)
        return Point(self.at.x + dx, self.at.y + dy)


@dataclass(frozen=True)
class AreaLabel:
    id: str
    at: Point
    label: str
    kind: str = "area"
    size: float = 16
    angle: float = 0
    anchor: str = "middle"
    vertical_anchor: str = "middle"


@dataclass(frozen=True)
class Zone:
    id: str
    rect: Rect
    label: str | None = None
    kind: str = "zone"
    privacy: str | None = None
    visible: bool = False


@dataclass(frozen=True)
class FeatureAnchor:
    wall: str
    offset: float
    distance: float
    side: str = "left"


@dataclass(frozen=True)
class WallExtrusion:
    wall: str
    depth: float
    offset: float = 0
    length: float | None = None
    side: str = "left"


@dataclass(frozen=True)
class Feature:
    id: str
    kind: str
    size: tuple[float, float] | None = None
    at: Point | None = None
    anchor: FeatureAnchor | None = None
    extrude: WallExtrusion | None = None
    label: str | None = None
    within: str | None = None
    clearance: dict[str, float] = field(default_factory=dict)
    avoid_openings: bool = False
    rotation: float = 0


@dataclass(frozen=True)
class WallOpening:
    id: str
    wall: str
    offset: float
    width: float
    kind: str = "door"
    swing: str = "in"


@dataclass(frozen=True)
class OverlayLine:
    id: str
    layer: str
    points: tuple[Point, ...]
    kind: str = "line"
    label: str | None = None
    color: str = "#2b78c2"
    width: float = 0.18
    dash: str | None = None


@dataclass(frozen=True)
class RoofSection:
    id: str
    rect: Rect
    mode: str = "hip"
    pitch: float | None = None
    eave_height: float | None = None
    eave_margin: float = 2.0
    start: str = "open"
    end: str = "open"
    ridge: str | None = None


@dataclass(frozen=True)
class StairRun:
    rect: Rect
    direction: Direction
    treads: int


@dataclass(frozen=True)
class Stair:
    id: str
    lower_level: str
    upper_level: str
    lower_space: str
    upper_space: str
    width: float
    floor_to_floor: float
    risers: int
    rise: float
    tread_depth: float
    runs: list[StairRun] = field(default_factory=list)
    landings: list[Rect] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WallLevel:
    id: str
    title: str | None = None
    walls: list[WallSegment] = field(default_factory=list)
    areas: list[AreaLabel] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    openings: list[WallOpening] = field(default_factory=list)
    access: list[tuple[str, str]] = field(default_factory=list)
    overlays: list[OverlayLine] = field(default_factory=list)
    roofs: list[RoofSection] = field(default_factory=list)
