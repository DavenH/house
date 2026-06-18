"""Floor-plan model objects and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from floorplan_lang.geometry import Circle, Point, Poly, Rect, Shape, shape_contains_point


Side = Literal["N", "E", "S", "W"]


@dataclass(frozen=True)
class WallDefaults:
    exterior: float = 0.75
    interior: float = 0.5
    door_width: float = 3.0


@dataclass(frozen=True)
class Room:
    id: str
    shape: Shape
    label: str | None = None
    kind: str = "room"
    tags: tuple[str, ...] = ()

    @property
    def display_label(self) -> str:
        return self.label or self.id.replace("_", " ").upper()

    @property
    def bbox(self) -> Rect:
        return self.shape.bbox

    @property
    def area(self) -> float:
        return getattr(self.shape, "area", self.bbox.area)


@dataclass(frozen=True)
class Door:
    room: str
    side: Side
    offset: float
    width: float = 3.0
    swing: str | None = None


@dataclass(frozen=True)
class Opening:
    between: tuple[str, str]
    width: float


@dataclass(frozen=True)
class Stack:
    id: str
    members: tuple[str, ...]
    same: tuple[str, ...] = ("center",)


@dataclass(frozen=True)
class Alignment:
    id: str
    members: tuple[str, ...]
    same: tuple[str, ...]
    tolerance: float = 0.01


@dataclass(frozen=True)
class MassPlacement:
    level: str
    shape: Shape
    contains: tuple[str, ...] = ()
    fills_width: tuple[str, ...] = ()
    fills: bool = False

    @property
    def bbox(self) -> Rect:
        return self.shape.bbox


@dataclass(frozen=True)
class Mass:
    id: str
    placements: tuple[MassPlacement, ...]
    roof: str | None = None
    align: tuple[str, ...] = ()
    tolerance: float = 0.01
    notes: tuple[str, ...] = ()


@dataclass
class Level:
    id: str
    title: str | None = None
    wall: WallDefaults = field(default_factory=WallDefaults)
    envelope: Rect | Poly | None = None
    rooms: dict[str, Room] = field(default_factory=dict)
    doors: list[Door] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)

    def add(self, room: Room) -> Room:
        if room.id in self.rooms:
            raise ValueError(f"Duplicate room id on {self.id}: {room.id}")
        self.rooms[room.id] = room
        return room

    def door(self, room: str, side: Side, offset: float, width: float | None = None, swing: str | None = None) -> Door:
        door = Door(room=room, side=side, offset=offset, width=width or self.wall.door_width, swing=swing)
        self.doors.append(door)
        return door

    def opening(self, a: str, b: str, width: float) -> Opening:
        opening = Opening(between=(a, b), width=width)
        self.openings.append(opening)
        return opening

    def __getitem__(self, room_id: str) -> Room:
        return self.rooms[room_id]


@dataclass
class Plan:
    name: str
    unit: str = "ft"
    scale: float = 16.0
    defaults: WallDefaults = field(default_factory=WallDefaults)
    levels: dict[str, Level] = field(default_factory=dict)
    masses: dict[str, Mass] = field(default_factory=dict)
    stacks: list[Stack] = field(default_factory=list)
    alignments: list[Alignment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def level(self, id: str, title: str | None = None, **kwargs: object) -> Level:
        if id in self.levels:
            raise ValueError(f"Duplicate level id: {id}")
        level = Level(id=id, title=title, wall=self.defaults, **kwargs)
        self.levels[id] = level
        return level

    def stack(self, id: str, members: Iterable[str], same: Iterable[str] = ("center",)) -> Stack:
        stack = Stack(id=id, members=tuple(members), same=tuple(same))
        self.stacks.append(stack)
        return stack

    def alignment(
        self,
        id: str,
        members: Iterable[str],
        same: Iterable[str],
        tolerance: float = 0.01,
    ) -> Alignment:
        alignment = Alignment(id=id, members=tuple(members), same=tuple(same), tolerance=tolerance)
        self.alignments.append(alignment)
        return alignment

    def mass(
        self,
        id: str,
        placements: Iterable[MassPlacement],
        roof: str | None = None,
        align: Iterable[str] = (),
        tolerance: float = 0.01,
        notes: Iterable[str] = (),
    ) -> Mass:
        if id in self.masses:
            raise ValueError(f"Duplicate mass id: {id}")
        mass = Mass(
            id=id,
            placements=tuple(placements),
            roof=roof,
            align=tuple(align),
            tolerance=tolerance,
            notes=tuple(notes),
        )
        self.masses[id] = mass
        return mass

    def room_ref(self, ref: str) -> Room:
        level_id, room_id = ref.split(".", 1)
        return self.levels[level_id].rooms[room_id]

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.unit != "ft":
            errors.append(f"Only unit='ft' is currently supported, got {self.unit!r}")
        for level in self.levels.values():
            errors.extend(_validate_level(level))
        for mass in self.masses.values():
            errors.extend(_validate_mass(self, mass))
        for stack in self.stacks:
            errors.extend(_validate_stack(self, stack))
        for alignment in self.alignments:
            errors.extend(_validate_alignment(self, alignment))
        return errors

    def require_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ValueError("Invalid plan:\n- " + "\n- ".join(errors))


def _validate_level(level: Level) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_room_overlaps(level))
    for door in level.doors:
        if door.room not in level.rooms:
            errors.append(f"{level.id} door references missing room {door.room!r}")
        if door.width <= 0:
            errors.append(f"{level.id}.{door.room} door width must be positive")
    for opening in level.openings:
        for room_id in opening.between:
            if room_id not in level.rooms:
                errors.append(f"{level.id} opening references missing room {room_id!r}")
        if opening.width <= 0:
            errors.append(f"{level.id} opening width must be positive")
    return errors


def _validate_room_overlaps(level: Level) -> list[str]:
    errors: list[str] = []
    checked = [
        room for room in level.rooms.values() if room.kind != "feature" and "allow_overlap" not in room.tags
    ]
    for index, first in enumerate(checked):
        for second in checked[index + 1 :]:
            if first.bbox.overlaps(second.bbox):
                errors.append(
                    f"{level.id}.{first.id} overlaps {level.id}.{second.id}; "
                    "split the shape, resize it, or tag one room allow_overlap"
                )
    return errors


def _validate_mass(plan: Plan, mass: Mass) -> list[str]:
    errors: list[str] = []
    if not mass.placements:
        errors.append(f"Mass {mass.id!r} must have at least one placement")
        return errors

    for placement in mass.placements:
        level = plan.levels.get(placement.level)
        if level is None:
            errors.append(f"Mass {mass.id!r} references missing level {placement.level!r}")
            continue
        for room_id in placement.contains:
            room = level.rooms.get(room_id)
            if room is None:
                errors.append(
                    f"Mass {mass.id!r} placement {placement.level} contains missing room {room_id!r}"
                )
            elif not _rect_contains(placement.bbox, room.bbox, tolerance=placement_tolerance(mass)):
                errors.append(
                    f"Mass {mass.id!r} placement {placement.level} does not contain "
                    f"{placement.level}.{room_id}"
                )
        for room_id in placement.fills_width:
            room = level.rooms.get(room_id)
            if room is None:
                errors.append(
                    f"Mass {mass.id!r} placement {placement.level} fills_width missing room {room_id!r}"
                )
            elif (
                abs(room.bbox.x - placement.bbox.x) > mass.tolerance
                or abs(room.bbox.w - placement.bbox.w) > mass.tolerance
            ):
                errors.append(
                    f"Mass {mass.id!r} placement {placement.level} width is not filled by "
                    f"{placement.level}.{room_id}"
                )
        if placement.fills:
            errors.extend(_validate_mass_fill(plan, mass, placement, level))

    if len(mass.placements) >= 2:
        first = mass.placements[0]
        for other in mass.placements[1:]:
            for attr in mass.align:
                if attr == "shape":
                    if not _shapes_match(first.shape, other.shape, mass.tolerance):
                        errors.append(
                            f"Mass {mass.id!r} shape mismatch: {first.level} vs {other.level}"
                        )
                    continue

                first_value = _bbox_value(first.bbox, attr)
                other_value = _bbox_value(other.bbox, attr)
                if first_value is None or other_value is None:
                    errors.append(f"Mass {mass.id!r} has unknown alignment rule {attr!r}")
                elif abs(first_value - other_value) > mass.tolerance:
                    errors.append(
                        f"Mass {mass.id!r} {attr} mismatch: "
                        f"{first.level}={first_value:g}, {other.level}={other_value:g}"
                    )
    return errors


def _validate_mass_fill(
    plan: Plan,
    mass: Mass,
    placement: MassPlacement,
    level: Level,
) -> list[str]:
    del plan
    fill_rooms = [
        level.rooms[room_id]
        for room_id in placement.contains
        if room_id in level.rooms
        and level.rooms[room_id].kind != "feature"
        and "non_fill" not in level.rooms[room_id].tags
    ]
    x_cuts = {placement.bbox.left, placement.bbox.right}
    y_cuts = {placement.bbox.top, placement.bbox.bottom}
    if isinstance(placement.shape, Poly):
        for point in placement.shape.points:
            x_cuts.add(point.x)
            y_cuts.add(point.y)
    for room in fill_rooms:
        box = room.bbox
        x_cuts.update((max(box.left, placement.bbox.left), min(box.right, placement.bbox.right)))
        y_cuts.update((max(box.top, placement.bbox.top), min(box.bottom, placement.bbox.bottom)))

    errors: list[str] = []
    xs = sorted(x_cuts)
    ys = sorted(y_cuts)
    for left, right in zip(xs, xs[1:], strict=False):
        if right - left <= mass.tolerance:
            continue
        for top, bottom in zip(ys, ys[1:], strict=False):
            if bottom - top <= mass.tolerance:
                continue
            center = Point((left + right) / 2, (top + bottom) / 2)
            if not shape_contains_point(placement.shape, center, tolerance=mass.tolerance):
                continue
            if not any(shape_contains_point(room.shape, center, tolerance=mass.tolerance) for room in fill_rooms):
                errors.append(
                    f"Mass {mass.id!r} placement {placement.level} has unfilled cell "
                    f"[{left:g}, {top:g}, {right - left:g}, {bottom - top:g}]"
                )
    return errors


def _validate_stack(plan: Plan, stack: Stack) -> list[str]:
    errors: list[str] = []
    rooms: list[Room] = []
    for ref in stack.members:
        try:
            rooms.append(plan.room_ref(ref))
        except KeyError:
            errors.append(f"Stack {stack.id!r} references missing room {ref!r}")
        except ValueError:
            errors.append(f"Stack {stack.id!r} member must look like LEVEL.room: {ref!r}")
    if len(rooms) < 2:
        return errors
    first = rooms[0]
    for other in rooms[1:]:
        for attr in stack.same:
            if attr == "center" and first.shape.center != other.shape.center:
                errors.append(f"Stack {stack.id!r} center mismatch: {first.id} vs {other.id}")
            elif attr == "radius":
                if not isinstance(first.shape, Circle) or not isinstance(other.shape, Circle):
                    errors.append(f"Stack {stack.id!r} radius rule requires circles")
                elif first.shape.r != other.shape.r:
                    errors.append(f"Stack {stack.id!r} radius mismatch")
            elif attr == "bbox" and first.bbox != other.bbox:
                errors.append(f"Stack {stack.id!r} bbox mismatch")
            elif attr not in {"center", "radius", "bbox"}:
                errors.append(f"Stack {stack.id!r} has unknown sameness rule {attr!r}")
    return errors


def _validate_alignment(plan: Plan, alignment: Alignment) -> list[str]:
    errors: list[str] = []
    rooms: list[Room] = []
    for ref in alignment.members:
        try:
            rooms.append(plan.room_ref(ref))
        except KeyError:
            errors.append(f"Alignment {alignment.id!r} references missing room {ref!r}")
        except ValueError:
            errors.append(f"Alignment {alignment.id!r} member must look like LEVEL.room: {ref!r}")
    if len(rooms) < 2:
        return errors

    first = rooms[0]
    for other in rooms[1:]:
        for attr in alignment.same:
            first_value = _alignment_value(first, attr)
            other_value = _alignment_value(other, attr)
            if first_value is None or other_value is None:
                errors.append(f"Alignment {alignment.id!r} has unknown rule {attr!r}")
            elif abs(first_value - other_value) > alignment.tolerance:
                errors.append(
                    f"Alignment {alignment.id!r} {attr} mismatch: "
                    f"{first.id}={first_value:g}, {other.id}={other_value:g}"
                )
    return errors


def _alignment_value(room: Room, attr: str) -> float | None:
    return _bbox_value(room.bbox, attr)


def _bbox_value(box: Rect, attr: str) -> float | None:
    values = {
        "x": box.x,
        "y": box.y,
        "w": box.w,
        "h": box.h,
        "left": box.left,
        "right": box.right,
        "top": box.top,
        "bottom": box.bottom,
        "cx": box.cx,
        "cy": box.cy,
    }
    return values.get(attr)


def _rect_contains(container: Rect, item: Rect, tolerance: float = 0.01) -> bool:
    return (
        item.left >= container.left - tolerance
        and item.right <= container.right + tolerance
        and item.top >= container.top - tolerance
        and item.bottom <= container.bottom + tolerance
    )


def placement_tolerance(mass: Mass) -> float:
    return max(mass.tolerance, 0.01)


def _shapes_match(a: Shape, b: Shape, tolerance: float) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, Rect) and isinstance(b, Rect):
        return all(
            abs(left - right) <= tolerance
            for left, right in ((a.x, b.x), (a.y, b.y), (a.w, b.w), (a.h, b.h))
        )
    if isinstance(a, Circle) and isinstance(b, Circle):
        return all(
            abs(left - right) <= tolerance
            for left, right in ((a.cx, b.cx), (a.cy, b.cy), (a.r, b.r))
        )
    if isinstance(a, Poly) and isinstance(b, Poly):
        if len(a.points) != len(b.points):
            return False
        return all(
            abs(left.x - right.x) <= tolerance and abs(left.y - right.y) <= tolerance
            for left, right in zip(a.points, b.points, strict=True)
        )
    return False
