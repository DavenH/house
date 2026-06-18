"""Small geometry primitives used by the floor-plan model."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Literal


EPSILON = 1e-6


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"Rect dimensions must be positive: {self}")

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> Point:
        return Point(self.cx, self.cy)

    @property
    def bbox(self) -> Rect:
        return self

    def padded(self, amount: float) -> Rect:
        return Rect(self.x - amount, self.y - amount, self.w + amount * 2, self.h + amount * 2)

    def touches(self, other: Rect, tolerance: float = EPSILON) -> bool:
        y_overlap = min(self.bottom, other.bottom) - max(self.top, other.top)
        x_overlap = min(self.right, other.right) - max(self.left, other.left)
        vertical_touch = abs(self.right - other.left) <= tolerance or abs(other.right - self.left) <= tolerance
        horizontal_touch = abs(self.bottom - other.top) <= tolerance or abs(other.bottom - self.top) <= tolerance
        return (vertical_touch and y_overlap > tolerance) or (horizontal_touch and x_overlap > tolerance)

    def overlaps(self, other: Rect, tolerance: float = EPSILON) -> bool:
        return (
            self.left < other.right - tolerance
            and self.right > other.left + tolerance
            and self.top < other.bottom - tolerance
            and self.bottom > other.top + tolerance
        )

    def distance_to(self, other: Rect) -> float:
        dx = max(other.left - self.right, self.left - other.right, 0)
        dy = max(other.top - self.bottom, self.top - other.bottom, 0)
        return sqrt(dx * dx + dy * dy)

    def contains_point(self, point: Point, tolerance: float = EPSILON) -> bool:
        return (
            self.left - tolerance <= point.x <= self.right + tolerance
            and self.top - tolerance <= point.y <= self.bottom + tolerance
        )


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float

    def __post_init__(self) -> None:
        if self.r <= 0:
            raise ValueError(f"Circle radius must be positive: {self}")

    @property
    def center(self) -> Point:
        return Point(self.cx, self.cy)

    @property
    def area(self) -> float:
        return 3.141592653589793 * self.r * self.r

    @property
    def bbox(self) -> Rect:
        return Rect(self.cx - self.r, self.cy - self.r, self.r * 2, self.r * 2)

    def contains_point(self, point: Point, tolerance: float = EPSILON) -> bool:
        return self.center.distance_to(point) <= self.r + tolerance


@dataclass(frozen=True)
class Poly:
    points: tuple[Point, ...]

    def __init__(self, points: Iterable[Point | tuple[float, float]]) -> None:
        parsed = tuple(p if isinstance(p, Point) else Point(float(p[0]), float(p[1])) for p in points)
        if len(parsed) < 3:
            raise ValueError("Poly requires at least three points")
        object.__setattr__(self, "points", parsed)

    @property
    def bbox(self) -> Rect:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @property
    def center(self) -> Point:
        box = self.bbox
        return box.center

    def contains_point(self, point: Point, tolerance: float = EPSILON) -> bool:
        inside = False
        vertices = self.points
        j = len(vertices) - 1
        for i, pi in enumerate(vertices):
            pj = vertices[j]
            if _point_on_segment(point, pj, pi, tolerance):
                return True
            if (pi.y > point.y) != (pj.y > point.y):
                x_intersect = (pj.x - pi.x) * (point.y - pi.y) / (pj.y - pi.y) + pi.x
                if point.x < x_intersect:
                    inside = not inside
            j = i
        return inside


@dataclass(frozen=True)
class Segment:
    a: Point
    b: Point

    @property
    def orientation(self) -> Literal["horizontal", "vertical", "diagonal"]:
        if abs(self.a.y - self.b.y) <= EPSILON:
            return "horizontal"
        if abs(self.a.x - self.b.x) <= EPSILON:
            return "vertical"
        return "diagonal"


Shape = Rect | Circle | Poly


def bbox_union(boxes: Iterable[Rect]) -> Rect:
    boxes = tuple(boxes)
    if not boxes:
        raise ValueError("bbox_union requires at least one box")
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.right for box in boxes)
    bottom = max(box.bottom for box in boxes)
    return Rect(left, top, right - left, bottom - top)


def shape_contains_point(shape: Shape, point: Point, tolerance: float = EPSILON) -> bool:
    return shape.contains_point(point, tolerance)


def _point_on_segment(point: Point, a: Point, b: Point, tolerance: float) -> bool:
    cross = (point.y - a.y) * (b.x - a.x) - (point.x - a.x) * (b.y - a.y)
    if abs(cross) > tolerance:
        return False
    dot = (point.x - a.x) * (b.x - a.x) + (point.y - a.y) * (b.y - a.y)
    if dot < -tolerance:
        return False
    length_sq = (b.x - a.x) ** 2 + (b.y - a.y) ** 2
    return dot <= length_sq + tolerance
