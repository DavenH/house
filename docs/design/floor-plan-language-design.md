# Floor Plan Language Design

This project needs a descriptive language for precise, repeatable floor-plan output. The goal is not a general CAD replacement. It is a compact way to describe residential plans that mostly use axis-aligned walls, common wall thicknesses, repeated room modules, stacked vertical features, and simple openings.

The language should sit below the abstract room-topology search described in `house-dsl-spec.md` and `room-layout-search.md`. Those documents are about adjacency graphs. This layer is about concrete geometry.

## Core Idea

Represent the plan as a small set of named geometric facts:

- levels
- grids and defaults
- room footprints
- wall runs
- openings
- labels
- vertical stack constraints
- derived/shared walls

The user should specify the few things that matter. The renderer should infer the repetitive things:

- exterior walls use a default thickness
- interior partitions use a default thickness
- adjacent rectangles share walls
- labels are centered unless overridden
- doors cut wall openings
- dimensions can be derived from level extents
- stacked elements must share footprint geometry unless explicitly varied

## Design Bias

Use a Python-native model first, with YAML/TOML/JSON export later.

Reasoning:

- Python gives validation, assertions, geometry helpers, and readable diffs immediately.
- A pure data format is attractive, but the first versions will need computed coordinates and reusable helpers.
- Once the concepts stabilize, the same objects can serialize to a minimal YAML form.

## Units And Coordinates

Use feet as semantic units and convert to pixels only in the renderer.

```python
Plan(scale=16)  # 1 ft = 16 px in SVG output
```

Coordinate system:

- `x` increases right
- `y` increases down
- origin is arbitrary per level
- all wall geometry is measured to face-of-wall or centerline, but choose one globally

Recommended default: model room footprints by clear interior rectangles, then let the renderer add wall thickness. This makes room sizes intuitive.

## Minimal Vocabulary

### Level

A level is a named drawing plane with defaults.

```python
Level(
    id="L1",
    title="Level 1",
    wall=WallDefaults(exterior=0.75, interior=0.5),
)
```

### Footprints

Most spaces can be rectangles. Irregular spaces should be polygons. Towers can be circles or rounded rectangles.

```python
Room("office", Rect(x=0, y=22, w=13, h=11), label="OFFICE/STUDIO")
Room("closet", Rect(x=21, y=22, w=6, h=11), label="CLOSET")
Room("tower", Circle(cx=17, cy=27.5, r=4.5), label="TOWER")
Room("great", Rect(x=43, y=6, w=21, h=14), label="GREAT ROOM")
```

Use explicit geometry for primary rooms. Avoid vague commands like “beside kitchen” at this layer. Those belong in a higher-level layout solver.

### Anchored Placement

To reduce repetitive coordinates, allow anchored construction:

```python
office = Rect.at("office", x=0, y=22, w=13, h=11)
tower = Circle.left_of("closet", gap=0, r=4.5, cy=office.cy)
closet = Rect.right_of(tower.bounds, w=6, h=office.h)
entrance = Rect.right_of(closet, w=9, h=office.h)
```

This keeps the concrete model precise while making edits like “move tower left” simple.

### Openings

Openings are tied to a wall side or a segment between two spaces.

```python
Door(room="entrance", side="S", offset=2.0, width=3.0, swing="in-left")
Opening(between=("entrance", "hall"), width=4.0)
```

The renderer should draw the wall gap and optional swing arc.

### Shared Walls

The user should not specify every partition line manually. If two room footprints touch exactly or overlap by a wall thickness tolerance, the renderer derives a shared wall.

Rules:

- same-level adjacent rooms share an interior partition
- room boundary against exterior outline gets exterior wall thickness
- duplicate wall segments are merged
- openings subtract from wall segments

### Exterior Envelope

There are two workable modes.

Mode A: derive envelope from room union.

```python
Level(..., envelope="room_union")
```

Mode B: specify envelope explicitly.

```python
Envelope(Polygon([...]))
```

For these house studies, explicit envelope is usually better. It preserves gables, extrusions, and exterior topology even when interior rooms shift.

### Stacking

Stacked features are first-class constraints, not comments.

```python
Stack("tower_stack", members=["L1.tower", "L2.tower"], same=["center", "radius"])
Stack("stair_stack", members=["L1.stair", "L2.stair"], same=["bbox"])
```

Validation should fail if stacked geometry drifts.

For the tower-left case:

```python
assert L1["tower"].shape.center == L2["tower"].shape.center
assert L1["tower"].shape.radius == L2["tower"].shape.radius
```

The drawing can offset levels vertically on the page, but model coordinates should remain comparable.

### Alignments

Some constraints are not stacked features but still need to stay coordinated. Gable bays are the clearest example: a front gable and back gable may need the same `x` and `w`, and the corresponding first-floor and second-floor gables need to line up even when their room labels differ.

Use alignments for these repeated architectural datums:

```yaml
alignments:
  - id: left_front_gable_stack
    members: [L1.bathroom, L2.ensuite_bathroom]
    same: [x, w]
  - id: level_2_left_gables_front_back
    members: [L2.ensuite_bathroom, L2.gym]
    same: [x, w]
```

Supported alignment attributes are `x`, `y`, `w`, `h`, `left`, `right`, `top`, `bottom`, `cx`, and `cy`.

### Masses

Masses are higher-level architectural structures that imply repeated alignment and containment rules. A gable is not just a visual label on a room. It is a building mass whose footprint should align across levels and whose contained rooms should remain inside that footprint.

```yaml
masses:
  left_gable:
    roof: gable
    levels:
      L1:
        rect: [6, 0, 15, 35]
        contains: [bathroom, office_studio]
      L2:
        rect: [6, 0, 15, 35]
        contains: [ensuite_bathroom, gym]

  right_gable:
    roof: gable
    levels:
      L1:
        rect: [35, 7, 25, 28]
        contains: [great_room, kitchen, dining]
        fills_width: [great_room, kitchen]
      L2:
        rect: [35, 7, 25, 28]
        contains: [room_1, room_2, lounge]
        fills_width: [lounge]
```

For `roof: gable`, the YAML loader defaults to `align: [x, w]` unless an explicit `align` list is provided. This keeps the source artifact high-level while still compiling down to measurable validation rules.

Shared perimeters can be modeled as masses too. Use `align: [shape]` when the entire polygon should match between levels, then model one-level projections separately.

```yaml
masses:
  shared_body:
    align: [shape]
    levels:
      L1:
        fills: true
        poly: [[0, 7], [6, 7], [6, 0], [60, 7], [60, 35], [0, 25]]
      L2:
        fills: true
        poly: [[0, 7], [6, 7], [6, 0], [60, 7], [60, 35], [0, 25]]

  dining_extrusion:
    levels:
      L1:
        rect: [60, 15, 8, 13]
        contains: [dining]
```

Mass validation checks:

- referenced levels exist
- contained rooms exist on that level
- contained room bounding boxes fit inside the mass placement
- `fills_width` rooms share the mass placement `x` and `w`
- `fills: true` mass placements have no unexplained cells inside the mass footprint
- repeated mass placements satisfy their `align` attributes

Level validation also rejects unexplained overlaps between rooms, zones, circulation cells, and tower footprints. `kind: feature` items such as a hearth or island are allowed to sit inside rooms. For rare intentional overlaps, tag one participant with `allow_overlap`.

Use explicit `alignments` when a datum is important but is not naturally owned by a mass.

### Zones And Divisions

Not every named area is a full room. Some areas are functional divisions inside open space, such as a piano area, hearth, or island. Encode these as rooms with a non-room `kind`.

```yaml
piano:
  rect: [29, 8, 9.5, 10]
  label: PIANO
  kind: zone
```

The renderer treats `kind: zone` as a dashed outline and `kind: feature` as a lighter solid outline.

### Axes And Cells

The preferred layout representation is wall-line first. Define named x/y axes once per level, then define rooms as cells bounded by those axis names. This avoids copying `x`, `y`, `w`, and `h` into every room.

```yaml
levels:
  L1:
    axes:
      x:
        west: 0
        service: 6
        stair_e: 30
        piano_e: 38
        east: 60
      y:
        main_top: 7
        entry_n: 20
        back: 35
    rooms:
      stair:
        cell: {x: [service, stair_e], y: [main_top, entry_n]}
        label: STAIR
      piano:
        cell: {x: [stair_e, piano_e], y: [main_top, entry_n]}
        label: PIANO
        kind: zone
```

The YAML loader compiles each `cell` into a rectangle internally, so existing validation and rendering still work. If a wall-line name is misspelled, loading fails immediately. Moving `stair_e` moves every room or mass that references it.

### Wall-Segment Plans

For open floor plans, walls should be the defining geometry. Rooms and open areas are labels at points, not closed rectangles.

```yaml
type: wall_plan
plan: ridgestone-walls
levels:
  L1:
    perimeters:
      shared_body:
        start: [0, 7]
        walk:
          - [E, 6]
          - [N, 7]
          - [E, 15]
          - [S, 7]
    walls:
      - {id: stair_w, at: [21, 7], dir: S, len: 13}
      - {id: great_kitchen_datum, at: [38, 20], dir: E, len: 22}
    areas:
      great_room: {at: [50, 13], label: GREAT ROOM, kind: open_area}
      kitchen: {at: [52, 27], label: KITCHEN, kind: open_area}
      entrance: {at: [25, 24], label: ENTRANCE, kind: open_area}
```

Supported wall forms:

- `perimeters.<id>.start` plus `walk: [[dir, len], ...]`
- individual wall segments: `{id, at: [x, y], dir, len}`

The renderer draws only walls and labels. It does not infer enclosure for open areas, three-walled spaces, hall-like circulation, or open-concept rooms.

### Design-Intent Plans

The `intent_plan` format is the compact source layer above `wall_plan`. It compiles architectural intent into the explicit wall-plan model, so the existing renderer and validators remain the target.

The intent layer keeps these concepts explicit:

- shared building masses
- one-floor projections
- symbolic datums
- semantic spaces
- fixture intent
- access/opening intent
- unusual pinned placement

It derives these concepts at compile time:

- exterior wall segments from shrink-wrapped mass rectangles
- room zones from semantic space bounds
- area labels from zone centroids
- common interior partitions from touching spaces, when `derive_partitions: true`
- door offsets from adjacent-space relationships
- wall-side fixtures such as counters from the referenced space side
- wall-side windows centered on their related room side
- daylight windows from exterior-wall availability and per-space daylight demand

Example:

```yaml
type: intent_plan
plan: compact-study
datums:
  x: {west: 0, middle: 10, east: 20}
  y: {north: 0, south: 12}
masses:
  body:
    levels: [L1, L2]
    rect: {x: [west, east], y: [north, south]}
levels:
  L1:
    derive_partitions: true
    spaces:
      left: {x: [west, middle], y: [north, south]}
      right: {x: [middle, east], y: [north, south]}
    connections:
      - [left, right]
```

This compiles to an exterior perimeter, two zones, two labels, the shared partition wall, and a centered door in that partition.

Opening inference supports:

```yaml
connections:
  - {between: [room_1, lounge], width: 3, position: end}
  - {between: [great_room, kitchen], kind: open}
openings:
  - {space: kitchen, side: south, width: 8, kind: window}
```

`position` may be `center`, `start`, `end`, `north`, `east`, `south`, or `west`. This keeps doors movable under topology changes: if two spaces are moved so their shared boundary changes from west/east to north/south, the compiler chooses the wall and offset from the new relationship.

Wall-side fixtures use the same idea:

```yaml
features:
  kitchen_south_counter:
    kind: counter
    along: {space: kitchen, side: south}
    depth: 1.5
```

The compiler finds the wall segment on the south side of `kitchen`, chooses the interior side automatically, and emits a wall extrusion in the compiled wall plan.

Strict validation is opt-in per level:

```yaml
levels:
  L2:
    validate:
      cover_masses: true
      closed_space_access: true
```

`cover_masses` rejects mass cells that are not assigned to any semantic space. `closed_space_access` rejects private, service, circulation, or explicitly closed spaces that do not have a door or open connection.

Daylight intent can be explicit or inferred:

```yaml
levels:
  L2:
    auto_windows: {window_sides: 2, width: 8, min_width: 3}
    spaces:
      dining: {x: [dining_w, dining_e], y: [front, back], daylight: high}
      pantry: {x: [pantry_w, pantry_e], y: [front, back], privacy: service}
```

The compiler searches exterior sides of the room and places centered windows on the longest available sides first. Service spaces default to low daylight demand, while public rooms, bedrooms, kitchen, dining, lounge, and gym-like rooms default higher. A room can override this with `daylight: none`, `low`, `medium`, or `high`, and can set `window_sides` or `window_width`.

### Semantic Zones

Wall-first plans still need named footprints for validation. A `zone` is a semantic area, not a drawing primitive. By default zones are invisible; set `visible: true` when a dashed review outline is useful.

```yaml
zones:
  master_bedroom:
    rect: [6, 11, 8, 13]
    label: MASTER/BEDROOM
    privacy: private
  stair:
    rect: [21, 7, 9, 11]
    privacy: circulation
```

Zones support:

- cross-floor stacks and alignments
- access graph references
- privacy/circulation annotations
- feature fit checks

They should follow the walls rather than replace them. If a wall moves, update the zone once so constraints continue to describe the intended topology.

### Features And Fixtures

Features are bounded house components inside or near spaces: islands, hearths, beds, pool tables, tubs, appliances, counters, and similar objects. They are not walls and should not be encoded as wall gaps.

```yaml
features:
  kitchen_island:
    kind: island
    size: [7, 3]
    anchor: {wall: kitchen_counter_wall, offset: 12.5, distance: 5}
    clearance: {walls: 4}
    label: ISLAND

  pool_table:
    kind: pool_table
    at: [50, 27]
    size: [8, 4]
    clearance: {walls: 5}
    label: POOL

  queen_bed:
    kind: bed_queen
    within: master_bedroom
    at: [10, 18]
    size: [5, 6.67]
    clearance: {left: 1.5, right: 1.5, foot: 2}
    avoid_openings: true
```

An anchored feature uses:

- `wall`: the wall segment it relates to
- `offset`: distance along that wall
- `distance`: clear distance from the wall to the nearest feature edge
- `side`: optional `left` or `right` side of the wall direction

This captures cases like a kitchen island whose position is determined by counter depth plus aisle clearance, instead of hard-coding four rectangle coordinates.

Feature validation currently checks:

- positive fixture dimensions
- anchor wall existence and offset range
- minimum clearance to walls when `clearance.walls` is set
- fit inside a containing zone when `within` is set
- no overlap with door/window/open openings when `avoid_openings: true`

### Access Graph

Access edges describe intended pathing between semantic zones and features without drawing extra hallway walls.

```yaml
access:
  - [suite_foyer, master_bedroom]
  - [master_bedroom, ensuite_bathroom]
  - [suite_foyer, walk_in_closet]
```

Validation rejects unknown nodes. Later versions can use these edges to check privacy rules, dead ends, required egress, and whether a room is accessible only through another private room.

### Wall-Plan Stacks And Alignments

The wall-first artifact supports the same constraint ideas as the earlier rectangle model, but members refer to zones, features, labels, or wall ids.

```yaml
stacks:
  - id: tower_stack
    members: [L1.tower_closet, L2.tower]
    same: [x, y, w, h]

alignments:
  - id: right_gable_width
    members: [L1.kitchen, L2.lounge]
    same: [x, w]
```

Supported attributes are `x`, `y`, `w`, `h`, `left`, `right`, `top`, `bottom`, `cx`, and `cy`.

## Proposed Python API

```python
from floorplan_lang import Plan, Level, Rect, Circle, Room, Door, Stack

plan = Plan(name="tower-left", unit="ft", scale=16)

l1 = plan.level("L1", title="Level 1")
l2 = plan.level("L2", title="Level 2")

l1.add(Room("office", Rect(0, 22, 13, 11), label="OFFICE/STUDIO"))
l1.add(Room("tower", Circle(17, 27.5, 4.5), label="TOWER"))
l1.add(Room("closet", Rect(21.5, 22, 6, 11), label="CLOSET"))
l1.add(Room("entrance", Rect(28, 22, 9, 11), label="ENTRANCE"))
l1.add(Room("pantry", Rect(39, 16, 6, 8), label="PANTRY"))

l2.add(Room("tower", Circle(17, 27.5, 4.5), label="TOWER"))

plan.stack("tower", ["L1.tower", "L2.tower"], same=["center", "radius"])
plan.render_svg("output/tower-left.svg")
```

## Proposed Data Format

After the Python model stabilizes, a compact YAML form could look like this:

```yaml
plan: tower-left
unit: ft
scale: 16
defaults:
  exterior_wall: 0.75
  interior_wall: 0.5
  door_width: 3

levels:
  L1:
    title: Level 1
    rooms:
      office:   {rect: [0, 22, 13, 11], label: "OFFICE/STUDIO"}
      tower:   {circle: [17, 27.5, 4.5], label: "TOWER"}
      closet:  {rect: [21.5, 22, 6, 11], label: "CLOSET"}
      entrance:{rect: [28, 22, 9, 11], label: "ENTRANCE"}
      pantry:  {rect: [39, 16, 6, 8], label: "PANTRY"}
    doors:
      - {room: entrance, side: S, offset: 2, width: 3, swing: in-left}

  L2:
    title: Level 2
    rooms:
      tower: {circle: [17, 27.5, 4.5], label: "TOWER"}

stacks:
  - id: tower
    members: [L1.tower, L2.tower]
    same: [center, radius]
```

## Renderer Pipeline

1. Load Python plan object or YAML.
2. Validate room ids, level ids, units, and shape values.
3. Validate topology rules:
   - required rooms exist
   - required adjacencies exist
   - forbidden labels on wrong levels fail, such as `ENTRANCE` on L2
4. Validate geometry rules:
   - stacked features match
   - rooms do not unintentionally overlap
   - pantry touches or is near kitchen
   - tower center changed only along allowed axis if editing from a baseline
5. Derive wall graph:
   - exterior envelope segments
   - room boundary segments
   - shared interior segments
   - opening cuts
6. Render SVG:
   - walls
   - openings
   - labels
   - optional dimensions
   - optional debug overlays

## Geometry Primitives

Start with only:

- `Rect`
- `Circle`
- `Poly`
- `Segment`
- `Point`

Add rounded rectangles later if needed. A tower can be a true circle or ellipse; if the actual plan has clipped sides, use `Poly` plus a label saying it is tower-shaped.

## Validation Rules Worth Adding Early

These catch exactly the kind of mistakes image generation made:

```python
same_center("L1.tower", "L2.tower")
same_radius("L1.tower", "L2.tower")
label_not_on_level("ENTRANCE", "L2")
near("L1.pantry", "L1.kitchen", max_distance=6)
adjacent("L1.tower", "L1.office")
adjacent("L1.tower", "L1.closet")
not_tiny("L1.closet", min_area=35)
```

For edits from an existing baseline:

```python
translated_only("tower", from_plan=baseline, dx=-12, dy=0)
```

## Relationship To Topology Search

The previous evolutionary graph can still matter, but it should feed constraints rather than directly draw a plan.

Topology layer:

```text
Pa -- K
G -- H
Rm -- W
Rm -- EB
T -- O
T -- UC
```

Geometry layer:

```text
Pa is a 6x8 rectangle near kitchen.
T is a circle at shared center on L1 and L2.
UC/closet is the rectangle beside T.
```

The topology engine can rank possible adjacencies. The floor-plan language can then encode one selected layout precisely.

## Initial Implementation Plan

1. Implement geometry dataclasses.
2. Implement `Plan`, `Level`, `Room`, `Door`, and `Stack`.
3. Implement validation first, before rendering.
4. Implement a minimal SVG renderer with:
   - room outlines
   - labels
   - wall thickness styling
   - level page offsets
5. Recreate the tower-left study as Python data.
6. Add debug overlays:
   - room ids
   - bounding boxes
   - stacked footprint markers
7. Add YAML export once the Python API feels stable.

## Non-Goals For The First Version

- automatic layout solving
- photorealistic architectural drafting
- furniture placement
- roof geometry
- stairs drawn with accurate tread counts
- dimension-perfect construction documents

The first milestone should be a clear, editable, topologically consistent plan diagram.
