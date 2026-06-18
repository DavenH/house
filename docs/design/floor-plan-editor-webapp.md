# Floor Plan Editor Webapp Design

## Purpose

The floor-plan YAML workflow is good for versioned architectural intent, but it is too slow for spatial editing. Moving a couch, fixing a window, testing a stair opening, or adjusting wall thickness should not require a conversation, a patch, a render, a screenshot, and another patch.

This webapp should be a direct-manipulation editor for `intent_plan` artifacts. The YAML remains the durable source of truth. The webapp gives fast visual editing, validation, and preview.

## Core Goals

- Edit floor plans visually while preserving clean `intent_plan` YAML.
- Drag rooms, walls, openings, labels, and features with snapping.
- Change room/opening/feature properties from inspector panels.
- Render exterior and interior wall thickness accurately.
- Make wall topology, openings, windows, doors, and arches visually unambiguous.
- Keep changes explainable as small YAML diffs.
- Support fast iteration on Ridgestone-specific plans before any CAD/BIM export.

## Non-Goals

- Not a full CAD replacement.
- Not structural engineering software.
- Not a general-purpose BIM modeler.
- Not a photorealistic renderer.
- Not initially a multi-user collaborative editor.

## Primary User Workflows

### Move Furniture And Fixtures

User can select a feature such as a piano, couch, desk, island, refrigerator, bed, table, or washer/dryer and drag it within its containing room.

Expected behavior:

- Show clearance boundary while dragging.
- Snap to grid, room centerlines, wall offsets, and other feature edges.
- Highlight validation failures in real time.
- Update `features.<id>.at`.
- Preserve compact YAML where possible:

```yaml
piano: {kind: piano_5x7, within: library, at: [10.5, 24], avoid_openings: true}
```

### Edit Windows, Doors, And Openings

User can click a wall and add:

- window
- door
- open passage
- arch

Expected behavior:

- Openings are attached to a wall segment or inferred from `between: [room_a, room_b]`.
- Dragging along a wall changes `offset`.
- Drag handles change `width`.
- Inspector changes `kind`, `position`, `swing`, and arch style.
- Exterior windows/doors render on the exterior wall thickness, not halfway through the room face.
- Interior openings use interior wall mask thickness.

Compact examples:

```yaml
- {between: [hall, stair], kind: arch, width: 3.5, position: end}
- {id: kitchen_window, space: kitchen, side: south, width: 8, kind: window}
- {id: front_door, space: entrance, side: south, width: 5, kind: door, swing: in-left}
```

### Edit Rooms And Partitions

User can select a room rectangle and drag its edges.

Expected behavior:

- Shared edges move neighboring rooms where the user chooses linked-edge editing.
- If not linked, validation flags overlaps or uncovered mass cells.
- Room labels update from room ids unless overridden.
- Topology changes are visible immediately.
- A room can be split into two rooms or merged with another room.
- Service rooms such as storage are modeled as rooms, not fixture boxes.

### Edit Massing And Perimeter

User can edit mass rectangles and see derived exterior walls update.

Expected behavior:

- Perimeter is rendered as continuous wall solids, not independent line caps.
- Exterior wall thickness is configurable, default `1.0 ft`.
- Interior wall thickness is configurable, default `0.3 ft`.
- The user can toggle inside-face, centerline, and outside-face overlays.
- The editor shows the pad footprint separately from clear interior room dimensions.

### Compare Variants

User can duplicate a plan and create named variants.

Expected behavior:

- `ridgestone-intent.yaml` can be promoted, duplicated, or forked.
- Variants can be viewed side by side.
- A diff panel shows changes in rooms, openings, features, masses, stacks, and alignments.
- User can mark variants as principal candidates.

## Interaction Model

## Canvas

The central workspace is an SVG-based floor-plan canvas.

Reasons for SVG:

- The existing renderer outputs SVG.
- Plan elements are semantic objects, not raw pixels.
- Browser hit testing is straightforward.
- Visual diffs and export remain simple.

Canvas capabilities:

- Pan and zoom.
- Smooth wheel/trackpad zoom centered on cursor.
- Zoom-to-selection and zoom-to-fit-level.
- Minimum editing zoom threshold before small handles are active.
- Screen-space handles that stay clickable regardless of plan scale.
- Multi-level vertical layout.
- Optional single-level focus mode.
- Grid with configurable spacing.
- Snap to datums, room edges, centers, and wall faces.
- Measurement overlay.
- Toggle labels, dimensions, clearances, wall thickness, and mass overlays.

## Selection

Selectable objects:

- spaces
- masses
- exterior perimeter segments
- interior partitions
- openings
- features
- labels
- stacks and alignment references

Selection behavior:

- Click selects the topmost object.
- Shift-click adds to selection.
- Double-click enters edit mode for a compound object.
- Escape clears selection.
- Hover shows semantic id and dimensions.
- At low zoom, select larger semantic objects first: room, wall, feature.
- At high zoom, expose fine handles: wall endpoints, opening jambs, feature resize handles.
- If multiple objects are under the cursor, show a small pick menu ordered by semantic relevance.

The editor should avoid requiring pixel-perfect clicks. Handles should be drawn in screen pixels, not model feet, so they remain grabbable at every zoom level.

## Zoom And Precision Editing

Zoom is part of the editing model, not only viewing. The canvas should support fast coarse editing when zoomed out and precise handle editing when zoomed in.

Recommended behavior:

- wheel or pinch zooms around the cursor, preserving the model point under the pointer
- middle-drag or space-drag pans without changing selection
- `F` zooms to selected object; `Shift+F` zooms to full level
- wall endpoints, opening jambs, and feature resize handles remain `10-14 px` on screen regardless of zoom
- hover hit areas may be larger than visible handles, but the highlighted object must show exactly what will move
- low zoom prioritizes whole-object selection; high zoom exposes endpoint/jamb/corner handles
- overlapping hits show a pick menu instead of selecting the wrong object silently

The editor should have an editing zoom threshold. Below that threshold, dragging a wall selects or moves the semantic wall/room edge only. Above it, the user can grab endpoints, junctions, opening jambs, and feature resize handles with confidence.

## Inspector

Right-side inspector changes based on selection.

For a space:

- id
- label
- privacy
- x and y bounds
- label position
- daylight
- window preferences
- requires access

For an opening:

- id
- kind: door, window, open, arch
- attached wall or `between`
- width
- offset / position
- swing
- arch style

For a feature:

- id
- kind
- containing room
- position
- size
- clearance
- avoid openings
- label

Features should be resizable from corner/edge handles when selected. Resize should update explicit feature `size` if the feature is custom, or offer to create a variant catalog item if the feature uses a shared catalog kind.

## Feature Resizing

Features are model objects, not decorative symbols. A selected feature should show a bounding box with edge and corner handles:

- edge handle: resize one dimension
- corner handle: resize both dimensions
- modifier key: preserve aspect ratio
- snap to grid, room centerlines, nearby fixture edges, and wall clearances
- show clearance and overlap warnings live
- keep feature inside its containing room by default, with an explicit override if temporarily invalid placement is needed

For fixtures with catalog dimensions, resizing should create an explicit plan-level size override or prompt to save a named variant. For custom rectangles, resizing directly updates `features.<id>.size`.

For a mass:

- id
- levels
- rects
- roof hint
- one-level or shared

## Left Sidebar

Plan browser:

- principal plans
- baseline variations
- clean-sheet concepts
- unsaved experiments

Tools:

- select
- room
- split room
- opening
- window
- door
- arch
- feature
- label
- measure
- validate

Catalog:

- piano
- couch
- chair
- dining table
- bed
- desk/counter
- refrigerator
- washer/dryer
- storage
- mechanicals
- pool table
- custom feature

## Bottom Panel

Tabs:

- Problems
- YAML Diff
- Topology
- Metrics
- History

Problems should include:

- overlapping rooms
- uncovered mass cells
- inaccessible closed rooms
- feature clearance failures
- feature overlaps opening
- invalid stack/alignment constraints
- windows not on exterior walls
- disconnected access graph

## Data Model

The browser should work against a structured JSON version of the intent YAML.

Recommended pipeline:

```text
YAML file
  -> parse to IntentDocument
  -> normalize into EditorModel
  -> derive WallPlan preview
  -> render SVG layers
  -> user edits EditorModel
  -> validate
  -> serialize back to compact YAML
```

## Editor Model

The editor should keep stable object ids. It should not treat the rendered SVG as the model.

Core types:

```ts
type IntentDocument = {
  type: "intent_plan";
  plan: string;
  unit: "ft";
  scale: number;
  datums: DatumSet;
  catalog: Record<string, CatalogItem>;
  masses: Record<string, MassSpec>;
  levels: Record<string, LevelSpec>;
  stacks?: ConstraintSpec[];
  alignments?: ConstraintSpec[];
};
```

```ts
type SpaceSpec = {
  x?: [DatumRef, DatumRef];
  y?: [DatumRef, DatumRef];
  rect?: [number, number, number, number];
  label?: string | false;
  label_at?: [number, number];
  label_size?: number;
  privacy?: "public" | "semi_private" | "private" | "service" | "circulation";
  daylight?: "none" | "low" | "medium" | "high";
  window_sides?: number;
  window_width?: number;
  requires_access?: boolean;
};
```

```ts
type OpeningSpec = {
  id?: string;
  between?: [string, string];
  space?: string;
  side?: "north" | "east" | "south" | "west";
  wall?: string;
  offset?: number;
  width?: number;
  kind?: "door" | "window" | "open" | "arch";
  position?: "center" | "start" | "end" | "north" | "east" | "south" | "west";
  swing?: string;
};
```

## Rendering Layers

Use layered SVG groups:

1. page background
2. mass overlays
3. exterior wall solids
4. floor/room interior masks
5. interior wall solids
6. opening masks
7. window/door/arch glyphs
8. room zones
9. features
10. clearances
11. labels
12. handles and hover state
13. dimensions

This prevents windows, dashed arches, and wall thickness from visually fighting each other.

## Wall Editing Workflow

Wall editing is the highest-risk interaction in the app. Users expect a wall drag to behave like a physical plan edit: attached walls stretch, openings stay attached, rooms remain closed, and the editor does not silently create slivers, overlaps, or disconnected topology.

The editor should treat most visible walls as handles on semantic boundaries, not as independent line segments.

## Wall Object Types

The editor should distinguish these cases:

- exterior mass edge
- exterior room edge inside a fixed mass
- interior partition between two spaces
- partial partition not derived from touching rooms
- opening edge, such as one jamb of a door/window/arch
- fixture edge, which is not a wall

The hover label should say what will be edited:

```text
Move datum right_e
Resize kitchen / storage shared wall
Move exterior mass edge dining_e
Resize window kitchen_window
Move opening along wall
```

This prevents the user from grabbing something that looks like a wall but edits the wrong source object.

## Grabbable Wall Parts

For any selected wall or boundary, expose different handles:

- center strip: offset the entire wall parallel to itself by dragging orthogonal to the wall axis
- endpoint handles: change wall length or junction position while preserving orthogonal topology
- corner handle: move both connected wall endpoints together
- opening body: drag opening along wall
- opening jamb handles: resize opening width
- wall thickness handle: inspect/change wall thickness, not usually shown by default

Hover behavior:

- highlight the wall or boundary segment under the cursor
- highlight adjoining walls that will extend/retract
- highlight spaces that will change dimensions
- show a dimension tooltip before drag starts

Dragging behavior:

- default snap: 0.5 ft
- fine snap with modifier: 0.125 ft or 1 inch
- hold modifier to temporarily disable snapping
- when dragging a wall center strip, project pointer movement onto the wall normal and ignore movement along the wall axis
- do not let a wall center-strip drag slide endpoints sideways along the wall axis
- endpoint and corner handles may change lengths, but should remain axis-aligned unless the plan is explicitly in a non-orthogonal mode
- show live dimensions for affected rooms and wall movement delta

Pointer handling should be deterministic:

1. On pointer down, identify the semantic object and handle kind.
2. Cache the starting wall axis, wall normal, connected endpoints, affected spaces, and related datums.
3. Convert screen pointer movement into model-space delta using the current zoom transform.
4. For center-strip wall drags, compute `signed_offset = dot(delta, wall_normal)` and ignore `dot(delta, wall_axis)`.
5. Apply the offset to the selected boundary and update only the connected endpoints needed to preserve room closure.
6. Preview invalid geometry, but do not save it silently.

## Orthogonal Wall Constraints

The default floor-plan editor should be orthogonal. A selected wall has two possible edit families:

- offset edit: move the wall parallel to itself, using only pointer movement perpendicular to the wall
- length/junction edit: move an endpoint, corner, or T-junction to extend/retract connected walls

These must not be collapsed into one ambiguous drag. If the user grabs the middle of a vertical wall and drags left/right, the wall offsets left/right and connected horizontal walls extend/retract. If the same grab moves up/down, the editor should either ignore that component or show a small constrained cursor hint.

Dragging a wall along its own axis should not move endpoints sideways, because that creates surprising angled or sheared adjoining walls. Sliding a wall segment along its axis should only exist as an explicit advanced command for partial partitions, and it should refuse to operate when connected rooms would become non-orthogonal.

## Dragging A T-Junction Or Elbow

For a shape like:

```text
_|
```

when the vertical pipe is dragged sideways, the default behavior should be:

- move the selected vertical boundary parallel to itself
- extend/retract the connected horizontal walls so endpoints remain connected
- preserve room closure
- preserve openings attached to the moved wall by moving them with the wall
- preserve openings attached to extended/retracted walls by keeping their offsets unless they would no longer fit

This is the expected physical editing behavior.

The same selected vertical pipe should not slide up or down in Move Wall mode. Up/down pointer movement is along the pipe axis, so it should be ignored for center-strip wall drags. To move the junction vertically, the user must grab the relevant endpoint, corner, or T-junction handle so the intent is unambiguous.

Example:

```text
before:  ─────┐
              │

after:   ─────────┐
                  │
```

The top horizontal wall extends; the selected vertical wall moves.

## When Default Wall Drag Should Diverge

There are semantic cases where moving the pipe should not simply stretch connected walls.

### Fixed Exterior Mass

If the selected wall is an interior partition inside a fixed exterior mass:

- moving it resizes adjacent rooms
- exterior walls do not move
- uncovered or overlapping mass cells are shown as validation errors

### Moving Exterior Mass Edge

If the selected wall is an exterior mass edge:

- dragging changes the mass rectangle/datum
- exterior perimeter changes
- adjoining exterior segments extend/retract
- rooms attached to that edge either resize or detach depending on mode

The editor should show a mode pill:

```text
Mass Edge: Resize Mass | Resize Rooms | Detach Rooms
```

Default: resize rooms that explicitly use the moved datum.

### Stacked Or Aligned Wall

If the wall participates in stack/alignment constraints:

- default drag should move all constrained members
- alternate action should allow local override only after confirmation
- show a warning if moving only one level breaks stack/alignment

Example prompt:

```text
This edge is aligned with L2.lounge.right. Move both, or detach this edge?
```

### Datum Shared By Many Things

If a wall edge is controlled by a datum used by many spaces:

- default should move the datum if the usage set is local and visible
- otherwise show affected references before applying

The user should see:

```text
Moving datum right_e affects: great_room, kitchen, lounge, shared_body.
```

### Door Or Window Constraints

If moving a wall would make an opening invalid:

- keep the opening attached if possible
- clamp opening offset if necessary
- if width no longer fits, show it in red and offer resize

Never silently delete an opening.

### Minimum Room Dimensions

If moving a wall makes a room too narrow:

- allow preview into invalid state
- show red room fill and exact failing dimension
- block save until fixed unless user explicitly marks as temporary draft

## Wall Drag Modes

The toolbar should expose clear wall-edit modes:

- Select
- Move Wall
- Resize Room
- Split Room
- Move Mass Edge
- Add Opening
- Add Window
- Add Door
- Add Arch

But the default Select tool should still support common direct actions:

- drag a feature
- drag an opening along a wall
- drag a room edge
- drag a wall endpoint

Advanced modes are for precision and disambiguation, not required for common edits.

## Wall Editing Inspector

When a wall/boundary is selected, inspector should show:

- semantic source: mass edge, room boundary, derived partition, explicit partition
- related datums
- affected rooms
- wall type: exterior/interior/feature
- thickness
- length
- openings on this wall
- constraints and alignments

For a shared partition:

```text
Wall: library / hall
Source: derived shared boundary
Thickness: 0.3 ft
Openings: hall_library_arch
Actions: split, make explicit, delete partition, add opening
```

For an exterior edge:

```text
Wall: shared_body north edge
Source: mass rectangle
Inside face: y = main_n
Exterior thickness: 1.0 ft outward
Actions: move datum, detach room, add window, add door
```

## Opening Editing

Openings should feel like objects attached to walls.

Common user flow:

1. Select `Add Window`.
2. Hover exterior wall.
3. Preview window centered under cursor.
4. Click to place.
5. Drag along wall to position.
6. Drag jamb handles to resize.
7. Inspector can switch between `space + side` and `wall + offset` representation.

Opening representation preference:

- use `space + side` when semantic side placement is enough
- use `wall + offset` for precise wall segment placement
- use `between` for interior door/open/arch connections

The app should show which one is being saved.

## Fixtures From Palette

Adding fixtures should be drag-from-sidebar, not YAML editing.

Common user flow:

1. Drag `Desk/Counter` from catalog.
2. Hover a room.
3. Room highlights if the fixture can fit.
4. Drop into room.
5. Fixture snaps to grid and common offsets.
6. Inspector shows size, clearance, label, and containing room.

Palette items:

- piano
- desk/counter
- refrigerator
- island
- couch
- chair
- dining table
- bed
- washer/dryer
- mechanicals
- storage cabinet
- custom rectangle

During drag:

- invalid rooms show red outline
- valid room shows green outline
- clearance box is visible
- collision with wall/opening/feature is visible

After drop:

- create compact YAML feature
- assign `within` automatically
- choose `kind` from catalog

Example:

```yaml
studio_desk: {kind: studio_desk, within: office_studio, at: [13.5, 30]}
```

## Frustration Cases To Avoid

The editor should be designed around avoiding these failure modes:

- user drags a wall and unrelated rooms far away change
- user tries to move a couch but selects a room instead
- user places a window and it appears halfway outside the wall
- user adds storage as a fixture when they meant a room
- user opens a wall and accidentally removes the entire partition
- user moves a datum without knowing it affects another floor
- user creates invalid YAML formatting churn from one small edit
- user cannot tell whether a wall is interior or exterior
- user cannot tell which side of exterior wall is inside face
- user has to manually type exact offsets for common operations

Mitigations:

- hover previews
- explicit affected-object highlighting
- undo stack
- save only after validation
- compact diff preview
- mode labels
- semantic object breadcrumbs
- visual distinction between room, fixture, wall, and opening

## Undo And Experimentation

Every editing operation should be reversible.

Undo stack should store semantic operations:

```text
Move feature piano from [10.5, 24] to [12, 23]
Resize room great_room right edge from dining_w to storage_w
Add window kitchen_east_window
Change opening hall_stair_arch width 9 -> 3.5
```

The user should be able to:

- undo/redo
- duplicate plan before risky edits
- mark a branch as temporary
- compare current edit to last saved YAML

## Recommended Default Wall Behavior

Defaults should match architectural intuition:

- dragging a wall center strip offsets it only orthogonal to its axis
- connected endpoints move only as a consequence of that orthogonal offset, extending/retracting adjoining orthogonal walls
- dragging along the wall axis is ignored unless using an explicit endpoint, corner, junction, or advanced slide operation
- dragging an interior partition resizes adjacent rooms
- dragging an exterior wall changes massing only in mass-edge mode
- openings stay attached to their wall
- features stay in their containing room unless the room no longer contains them
- stacked/aligned edits move constrained peers unless detached
- invalid states are previewable but not silently saved

## Wall Rendering Requirements

Exterior walls:

- authored boundary is inside face
- rendered thickness defaults to `1.0 ft`
- wall solid extends outward
- perimeter corners join cleanly as one continuous envelope
- windows/doors render centered in the wall thickness, not centered on the room boundary

Interior walls:

- rendered thickness defaults to `0.3 ft`
- openings mask only interior wall thickness
- doors/arches must not use exterior opening masks

Arch rendering:

- dashed line
- default shape: `1/5` flat, `3/5` arched, `1/5` flat
- support full-span arch and partial-width arch
- support position start/end/center

## Editing Semantics

## Datums

When moving a wall or room edge tied to a datum, the editor should ask whether to:

- move the datum globally
- detach this one room edge to a numeric coordinate
- create a new datum

Default should be move datum when the datum name is clearly local; otherwise prompt.

## Compact YAML Serialization

Serializer should preserve compact style for simple objects:

```yaml
stair: {x: [left_e, stair_e], y: [main_n, stair_s], privacy: circulation}
```

Use block style only when nested fields get hard to read:

```yaml
kitchen_south_counter:
  kind: counter
  along: {space: kitchen, side: south}
  depth: 1.5
```

The app should avoid whole-file churn. It should preserve ordering and comments where practical.

## Validation

Validation should run in two modes:

- fast client-side validation for live dragging
- authoritative Python validation through the existing compiler

Client-side validation:

- bounds
- overlap
- opening within wall span
- feature inside containing room
- clearance box
- exterior side availability

Server-side validation:

- existing `floorplan_lang` compiler validation
- stack constraints
- alignment constraints
- mass coverage
- closed space access
- render generation

## Suggested Architecture

## Frontend

Recommended stack:

- Vite
- React
- TypeScript
- SVG canvas
- Zustand or Redux Toolkit for editor state
- `@xyflow/react` only for topology graph view, not plan editing

Why not Canvas initially:

- SVG elements can be inspected and selected directly.
- Export/debug path matches current artifact format.
- Geometry counts are small.

## Backend

Recommended stack:

- FastAPI
- Python `floorplan_lang` package
- file-backed plan repository under `artifacts/floorplans`

Backend endpoints:

```text
GET  /api/plans
GET  /api/plans/{id}
POST /api/plans/{id}/validate
POST /api/plans/{id}/render
POST /api/plans/{id}/save
POST /api/plans/{id}/fork
GET  /api/catalog
```

## Persistence

Use repository files as the source of truth.

Initial persistence:

- write YAML files directly
- generate SVG/PNG artifacts
- keep autosaves in `artifacts/floorplans/.autosave`

Later persistence:

- optional SQLite index for metadata, variants, thumbnails, and edit history

## Version Control

The app should show git-aware state:

- clean / modified / untracked
- diff preview before save
- last render time
- validation status

Do not auto-commit.

## MVP Scope

MVP should solve the current pain:

1. Load one `intent_plan` YAML.
2. Render editable SVG.
3. Pan and zoom the editing canvas with cursor-centered zoom and fit-to-selection.
4. Select and drag features.
5. Resize features with screen-space corner/edge handles.
6. Drag features from a sidebar palette into rooms.
7. Select openings and edit kind/width/position.
8. Add/delete windows.
9. Add/delete doors/open/arch connections.
10. Select walls and inspect affected rooms/datums.
11. Drag simple room edges with orthogonal-only connected-wall extension/retraction.
12. Edit room labels and privacy.
13. Run validation.
14. Save YAML.
15. Regenerate SVG/PNG.

MVP can defer:

- room splitting/merging
- mass editing
- topology scoring
- advanced history
- 3D export

## Phase Plan

### Phase 1: Viewer And Inspector

- Load `ridgestone-intent-studio-wing.yaml`.
- Render existing SVG layers in browser.
- Select rooms, openings, and features.
- Show inspector values.
- No editing yet.

### Phase 2: Feature Editing

- Drag features.
- Drag new features from the sidebar catalog.
- Resize features from corner/edge handles.
- Edit feature size, label, clearance, and containing room.
- Validate feature fit live.
- Save YAML.

### Phase 3: Opening Editing

- Add, delete, drag, and resize windows/doors/arches.
- Choose opening mode from a segmented control.
- Support dashed arch style.
- Ensure exterior openings sit within exterior wall thickness.

### Phase 4: Room Editing

- Drag room edges.
- Drag wall endpoints and connected elbows.
- Offset wall center strips only orthogonal to the wall axis.
- Extend/retract adjoining walls by default for orthogonal offsets.
- Ignore along-axis movement during wall center-strip drags.
- Show affected rooms/datums before committing a drag.
- Move linked datum edges.
- Split/merge simple rectangles.
- Preserve mass coverage.

### Phase 5: Variant Workflow

- Fork plan.
- Side-by-side compare.
- Promote principal plan.
- Diff YAML changes.

### Phase 6: Metrics And Search

- Show topology graph.
- Evaluate daily user stories.
- Suggest layout changes from scoring.

## Open Questions

- Should the editor allow numeric wall-face mode per plan, or should all intent plans standardize on inside-face room rectangles?
- Should exterior windows be represented as attached to `space + side` only, or should raw `wall + offset` remain first-class for precision?
- Should datums be hidden from casual editing until needed, or always visible in a coordinate panel?
- Should room splits create new datums automatically?
- Should generated wall ids be stable enough for user-authored `wall + offset` openings, or should all authored openings prefer semantic `space + side` and `between`?

## Success Criteria

The editor is successful when these edits take seconds instead of conversation loops:

- move the piano and immediately see clearance
- drag the couch closer to the hearth
- add a refrigerator
- turn a door into an arch
- move a window flush with the exterior wall
- create a storage room instead of a storage fixture
- adjust stair opening positions
- inspect whether a room has light on two sides
- save a clean, compact YAML diff
