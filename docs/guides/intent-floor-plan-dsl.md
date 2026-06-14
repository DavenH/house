# Intent Floor-Plan DSL Guide

This guide is the short reference for authoring `intent_plan` YAML files. Use it when starting a new floor-plan conversation or when converting an image/reference into a compact, editable house layout.

The intent DSL is a source language. It compiles to the explicit `wall_plan` representation used by the renderer. Prefer editing intent files for semantic layout changes; use compiled wall plans only when debugging exact generated geometry.

## Core Idea

Write architectural intent:

- shared masses and one-level projections
- named datums
- semantic spaces
- access relationships
- fixture intent
- daylight intent
- validation rules

Let the compiler derive:

- exterior walls from shrink-wrapped mass rectangles
- room zones from semantic space bounds
- labels from zone centroids
- interior partitions from touching spaces
- door/opening offsets from adjacent-space relationships
- wall-side counters and windows from the related space side
- daylight windows from exterior wall availability

## Minimal Shape

```yaml
type: intent_plan
plan: compact-study
unit: ft
scale: 16
datums:
  x: {west: 0, middle: 10, east: 20}
  y: {north: 0, south: 12}
masses:
  body:
    levels: [L1]
    rect: {x: [west, east], y: [north, south]}
levels:
  L1:
    title: First Floor
    derive_partitions: true
    spaces:
      left: {x: [west, middle], y: [north, south], privacy: private}
      right: {x: [middle, east], y: [north, south], privacy: public}
    connections:
      - [left, right]
```

This compiles into an exterior perimeter, two semantic zones, labels, a shared partition wall, and a centered door in that partition.

## Datums

Use datums for all meaningful repeated coordinates:

```yaml
datums:
  x:
    west: 0
    stair_w: 21
    stair_e: 30
    east: 57
  y:
    north: 7
    public_split: 22
    south: 35
```

A datum is better than a repeated number because moving it updates every space, mass, window, and fixture that references it.

## Masses

Masses describe the building envelope. Use rectangles; the compiler shrink-wraps their union into exterior walls.

```yaml
masses:
  shared_body:
    levels: [L1, L2]
    rects:
      - {x: [west, east], y: [north, south]}
      - {x: [gable_w, gable_e], y: [front, gable_s]}
  dining_projection:
    level: L1
    rect: {x: [east, dining_e], y: [dining_n, dining_s]}
```

Use shared masses for perimeter alignment between floors. Use one-level masses for sanctioned differences such as a dining projection.

## Spaces

Spaces are semantic areas. They compile to zones and labels.

```yaml
spaces:
  kitchen:
    x: [right_w, right_e]
    y: [public_split, south]
    privacy: public
    daylight: high
  pantry:
    x: [pantry_w, pantry_e]
    y: [pantry_n, pantry_s]
    privacy: service
    daylight: none
```

Common fields:

- `x: [left, right]` and `y: [top, bottom]`
- `rect: [x, y, w, h]` for one-off geometry
- `label: CUSTOM/LABEL`, or `label: false` to suppress an area label
- `label_at: [x, y]` to manually move a label
- `label_size: 10`
- `privacy: public | semi_private | private | service | circulation`
- `daylight: none | low | medium | high`
- `window_sides: 1` or `2`
- `window_width: 8`
- `requires_access: false` for rare intentionally inaccessible regions

## Partitions

Set `derive_partitions: true` to generate interior walls between touching spaces:

```yaml
levels:
  L1:
    derive_partitions: true
```

Use explicit partitions only when the wall is not implied by touching spaces:

```yaml
partitions:
  - {id: stair_guard, from: [stair_e, north], to: [stair_e, stair_s]}
```

Avoid encoding gaps in walls. Doors, windows, and open connections are separate semantic objects.

## Connections And Doors

Use `connections` for room-to-room access. The compiler finds the shared wall and places the door/opening.

```yaml
connections:
  - [foyer, great_room]
  - {between: [great_room, kitchen], kind: open}
  - {between: [mudroom, hall], kind: arch}
  - {between: [room_2, lounge], width: 3, position: east}
```

Fields:

- `between: [a, b]`
- `kind: door | open | arch`, default `door`
- `width: 3`, ignored for `open`; `arch` uses the whole shared span unless a width is provided
- `position: center | start | end | north | east | south | west`
- `swing: in-left`, currently only affects rendered door styling lightly

Use `arch` for a doorless opening that should still read as architecturally defined, such as a masonry or timber archway.

Use `position` when privacy/pathing suggests a non-centered door. Let the compiler calculate exact offsets.

## Exterior Openings

Use `openings` for exterior doors, pinned windows, or other openings that are not just room-to-room access.

```yaml
openings:
  - {id: front_door, space: foyer, side: south, width: 6, kind: door}
  - {id: great_window, space: great_room, side: south, width: 10, kind: window}
```

Prefer `space` plus `side` over raw `wall` plus `offset`; it survives mass/layout edits better.

## Auto Windows

Enable daylight-derived windows per level:

```yaml
levels:
  L1:
    auto_windows: {window_sides: 2, width: 8, min_width: 3}
```

The compiler searches exterior sides of each room and places centered windows on the longest available sides first.

Default daylight behavior:

- service spaces such as storage, pantry, closet, stair, hall, and tower default low
- public rooms, bedrooms, kitchens, dining rooms, lounges, great rooms, and gyms default higher
- explicit `daylight` always wins

Pinned explicit windows and auto windows can coexist.

## Fixtures

Use a catalog for repeated fixture defaults:

```yaml
catalog:
  queen_bed: {size: [6.67, 5], label: BED, clearance: {left: 1, right: 1, foot: 2}}
  pool_table_4x8: {size: [8, 4], label: POOL TABLE, clearance: {walls: 5}}
  counter: {label: COUNTER}
```

Place free fixtures by center:

```yaml
features:
  bed:
    kind: queen_bed
    within: master_bedroom
    at: [10, 17]
```

Place wall-side fixtures with `along`:

```yaml
features:
  kitchen_south_counter:
    kind: counter
    along: {space: kitchen, side: south}
    depth: 1.5
```

The compiler finds the wall on that side of the space and extrudes inward.

## Validation

Strict validation is opt-in per level:

```yaml
validate:
  cover_masses: true
  closed_space_access: true
```

`cover_masses` rejects any cell inside the level mass that is not assigned to a semantic space.

`closed_space_access` rejects private, service, circulation, or explicitly closed spaces that have no door/open access.

Also use cross-floor constraints:

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

## Image-Derived Workflow

When proposing a plan from an exterior image:

1. Identify visible masses: main body, gables, tower/cupola, dormers, wings, projections.
2. Convert those masses into shared and one-level `masses`.
3. Define datums for repeated edges and centers.
4. Assign first-floor spaces to visible facade clues:
   - central door -> foyer/entry
   - large gable window -> great room, library, dining, or primary public room
   - chimney -> hearth/fireplace stack
   - tower/cupola -> stair, tower landing, or vertical feature
   - dormer -> sparse upper room, loft, or eave storage
5. Make the second floor sparse for 1.5-storey designs: use gable rooms, dormer rooms, lofts, storage, and circulation.
6. Enable `cover_masses` and `closed_space_access` once the first draft compiles.
7. Render to SVG/PNG and visually review before refining.

Useful commands:

```bash
python -m floorplan_lang artifacts/floorplans/example-intent.yaml artifacts/floorplans/example-intent.svg
python - <<'PY'
import cairosvg
cairosvg.svg2png(
    url='artifacts/floorplans/example-intent.svg',
    write_to='artifacts/floorplans/example-intent-review.png',
)
PY
```

Run checks after compiler or artifact changes:

```bash
pytest -q
ruff check src tests
```

## Current Example Files

- `artifacts/floorplans/ridgestone-intent.yaml`
- `artifacts/floorplans/ridgestone-intent-studio-wing.yaml`
- `artifacts/floorplans/ridgestone-intent-upper-alt.yaml`
- `artifacts/floorplans/fieldstone-manor-intent.yaml`
