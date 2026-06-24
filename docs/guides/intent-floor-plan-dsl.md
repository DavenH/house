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

## Shared Defaults

Intent plans can import shared YAML defaults before applying local overrides:

```yaml
type: intent_plan
imports:
  - shared-structural.yaml
plan: compact-study
roof:
  eave_margin: 1.5
structural:
  bearing:
    point_loads: []
```

Imports are resolved relative to the importing YAML file. Multiple imports are applied in order. Nested mappings deep-merge, while lists and scalar values are replaced by the later file. Use shared files for global assumptions such as `compass`, `story`, `roof.pitch`, `costing`, `catalog`, `structural.materials`, `structural.design_loads`, and `structural.rafters`. Keep house-specific geometry, datums, spaces, masses, foundations, stairs, and configured load locations in the leaf plan.

The Ridgestone variants currently import `shared-structural.yaml`, which itself imports `shared-costs.yaml`. This keeps estimating assumptions and material prices shared without flattening them into each house variant.

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

## Stairs

Use top-level `stairs` for cross-level staircases. A stair references the semantic stair spaces on both levels, generates the lower/upper access openings, solves the riser/tread layout, and renders realistic runs with flat landings and tread lines.

```yaml
story: {floor_to_floor: 10}
stairs:
  main_stair:
    spaces: {lower: L1.stair, upper: L2.stair}
    width: 3
    lower_entry: {from: hall, side: south, position: east, kind: arch, width: 3.5}
    upper_exit: {to: upper_landing, side: south, position: west, kind: arch, width: 3.5}
    layout: {mode: solve, hug: perimeter, preferred_shape: u, turn_landings: flat, winders: false}
    steps:
      target: {rise_in: 7, run_in: 13}
      limits: {rise_in: [6.5, 8], run_in: [10, 13]}
      min_treads_per_run: 2
```

Fields:

- `spaces.lower` and `spaces.upper`: level-qualified stair spaces, such as `L1.stair`.
- `floor_to_floor`: optional per-stair override; otherwise uses top-level `story.floor_to_floor`.
- `width`: stair width in feet, defaulting by convention to 3 ft.
- `lower_entry.from`: lower-level room that enters the stair.
- `upper_exit.to`: upper-level room that exits the stair.
- `side` and `position`: semantic endpoint placement on the stair room perimeter.
- `steps.target`: preferred rise/run in inches.
- `steps.limits`: acceptable rise/run ranges in inches.
- `steps.min_treads_per_run`: avoids awkward one-step runs in U-shaped solutions.

The current solver enumerates perimeter-hugging paths with flat corner landings. Winders are reserved for a future fallback and are not emitted unless the solver is extended.

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

Use `wrap` when one authored fixture should hug several sides of a space. The compiler follows every wall segment on the requested sides, so interrupted interior and exterior walls both work:

```yaml
features:
  kitchen_counters:
    kind: counter
    wrap: {space: kitchen, sides: [west, south, east], depth: 2}
```

## Foundations

Use top-level `foundations` to generate a concrete-pad drawing from datum-backed mass geometry. Generated foundation levels are appended after authored floor levels, so a plan with `L1`, `L2`, and `L3` will render the pad in the fourth quadrant.

```yaml
foundations:
  F1:
    title: Concrete Pad
    source_level: L1
    masses: [shared_body]
    insulation_margin: 4
    footing_width: 2
    pad_rebar_spacing: 2
    pad_rebar_edge_cover: 0.1667
```

Fields:

- `source_level`: level whose resolved datums should be used, default `L1`.
- `masses`: optional mass ids to include; omitted means all masses active on `source_level`.
- `rect` or `rects`: optional direct rectangle specs instead of masses.
- `insulation_margin`: shaded insulation margin outside the concrete pad, in feet.
- `pad_wall_margin`: concrete-pad expansion outside the mass perimeter, defaulting to the exterior wall thickness.
- `footing_center_offset`: footing path offset outside the mass perimeter, defaulting to half the exterior wall thickness.
- `footing_width`: rendered footing band width.
- `pad_rebar_spacing`: cross-hatch rebar spacing.
- `pad_rebar_edge_cover`: distance rebar terminates before the pad edge; `0.1667` is about 2 inches.

The compiler reuses the same rect-union perimeter strategy as exterior-wall generation, so the pad, footing paths, insulation margin, and rebar move when referenced datums move.

Costing uses `insulation_margin` to estimate the pad insulation apron area as the difference between the insulation-margin perimeter and the concrete pad perimeter.

## Costing

Use top-level `costing` to declare estimating assumptions that are not directly rendered in plan. The cost estimator still falls back to defaults when this block is omitted.

```yaml
costing:
  exterior_wall:
    height_ft: 10
    icf:
      block: {length_ft: 4, height_ft: 1.3333}
      insulation_thickness_in: 2.5
      concrete_thickness_in: 6
      waste_percent: 8
    cladding:
      type: fieldstone
      thickness_in: 4
      waste_percent: 10
  plumbing:
    pex_per_wet_space_ft: 60
  materials:
    concrete: {label: Concrete, unit: yd3, unit_cost: 220}
    windows: {label: Windows, unit: sq ft, unit_cost: 70}
```

Fields:

- `exterior_wall.height_ft`: wall height used for exterior wall area.
- `icf.block.length_ft` / `icf.block.height_ft`: nominal ICF block face size used to estimate block count.
- `icf.insulation_thickness_in`: insulation thickness on each side of the ICF sandwich.
- `icf.concrete_thickness_in`: concrete core thickness used to estimate ICF core concrete volume.
- `icf.waste_percent`: extra ICF blocks for cuts and waste.
- `cladding.type`: label for the exterior cladding estimate, such as `brick`, `fieldstone`, or `shingles`.
- `cladding.thickness_in`: cladding thickness added to the total exterior wall thickness estimate.
- `cladding.waste_percent`: extra cladding area for cuts and waste.
- `plumbing.pex_per_wet_space_ft`: first-pass PEX allowance for each inferred wet space.
- `materials`: unit-cost table used by the editor Costs pane. It is keyed by material id; each row has `label`, `unit`, and `unit_cost`.

Interior doors are estimated from room-to-room `connections` and interior-wall `openings` whose `kind` is omitted or set to `door`. `open`, `arch`, and `window` entries are not counted as interior doors.

Shared defaults can be layered with imports:

```yaml
type: intent_plan_defaults
imports:
  - shared-costs.yaml
roof:
  pitch: '8:12'
costing:
  exterior_wall:
    cladding: {type: brick, thickness_in: 3.5}
```

The Materials tab writes unit-cost edits back to the shared costs YAML rather than marking the active house plan dirty.

## Structural Preparation

Use top-level `structural` to describe assumptions and load-path candidates before doing code-level structural calculations. This block is intended to prepare engineer-facing static load work; it is not a replacement for stamped design.

```yaml
structural:
  materials:
    concrete_slab: {density_pcf: 150}
    icf_concrete: {density_pcf: 150}
    fieldstone_veneer: {dead_load_psf: 45}
    brick_masonry: {density_pcf: 120}
    roof_assembly: {dead_load_psf: 15}
    timber_roof_framing: {dead_load_psf: 4}
    floor_assembly: {dead_load_psf: 12}
    interior_partition: {dead_load_psf: 8}
  design_loads:
    floor_live_psf: 40
    bedroom_live_psf: 30
    roof_dead_psf: 15
    roof_snow_psf: null
    wind_psf: null
    soil_bearing_psf: null
  rafters:
    spacing_in: 16
    purchase_length_threshold_ft: 16
  bearing:
    point_loads:
      - {id: hearth_chimney, kind: masonry_mass, level: L1, at: [43, 17], size: [6, 2], height_ft: 20, material: brick_masonry}
    line_loads:
      - {id: tower_brick_walls, kind: masonry_perimeter, level: L1, space: tower_closet, height_ft: 30, wall_thickness_in: 8, material: brick_masonry}
    slab_zones:
      - {id: hearth_pad, level: L1, at: [43, 17], size: [6, 2], reason: masonry hearth/chimney bearing}
      - {id: tower_pad, level: L1, space: tower_closet, reason: masonry tower bearing}
```

Fields:

- `materials.*.density_pcf`: material density in pounds per cubic foot for volume-based load estimates.
- `materials.*.dead_load_psf`: dead load in pounds per square foot for area-based assemblies.
- `design_loads`: project assumptions and missing code/site inputs. Leave values as `null` until confirmed from site/code data.
- `rafters.spacing_in`: assumed rafter spacing for early count and length estimates.
- `rafters.purchase_length_threshold_ft`: flags rafter lengths that likely need purchased lumber instead of milled stock.
- `bearing.point_loads`: concentrated masonry or post loads that should map to local slab/footing reinforcement.
- `bearing.line_loads`: continuous loads such as masonry tower walls.
- `bearing.slab_zones`: named zones expected to need local slab or grade-beam attention.

The editor-side structural estimator currently derives configured masonry point/line loads and rafter counts/lengths from this block. Snow, wind, seismic, and soil-bearing values remain explicit missing inputs until supplied.

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

- `artifacts/floorplans/master-south.yaml`
- `artifacts/floorplans/studio-wing.yaml`
