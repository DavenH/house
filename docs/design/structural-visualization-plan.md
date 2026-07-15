# Structural workspace: first-principles product and visualization plan

Status: active implementation. The previous structural-analysis prototype was removed; the replacement uses the architecture SVG as its underlay and an authored, provenance-aware structural model.

## Implementation record

Implemented in the first production slice:

- cached client-side Plan / Structure switching over the same architectural SVG;
- professional screened-underlay line hierarchy and one-level structural presentation;
- composable Framing, Load path, and Checks presets;
- an explicitly authored right-gable floor concept zone;
- deterministic joist layout, member count, cut length, and total linear length from that zone and user-set spacing;
- member, rim-board, and blocking schedule rows which remain unresolved where products/details are absent;
- configurable imperial framing, load, material-property, deflection-limit, waste, price, and price-source inputs;
- transparent simple-span screening checks for bending, shear, and deflection, gated on complete inputs;
- calculation formulas and intermediate results in an expandable calculation trace; and
- explicit unresolved support-below, foundation, connection, roof-topology, and code-combination states.

The L2 structural-zone model now includes the left gable floor, central stair-core floor, tower spiral-stair opening, right gable floor, and master balcony floor. Joists are clipped to the union of the actual floor spaces, so the central main-stair void, tower opening, and irregular gable edges are not counted or drawn as solid floor framing.

The right-gable plan also carries a `structural.scheme_sets.right_gable` comparison model. It defines clear-span solid-sawn, clear-span engineered wood I-joist, and hearth-spine alternatives against one shared L2 floor-depth constraint. The hearth spine follows the architectural hearth centre at x=44 and divides the gable into approximately 6-foot and 12-foot joist bays. Product selections, sections, connections, reactions, foundations, and unsupported calculations remain null or explicitly unresolved.

The first floor-framing slice also supports exceptional feature loads through an authored `structural_mass_lb` property. Normal occupants and movable furniture are covered by the configurable occupancy live load; unusually heavy objects can therefore be located and calculated without pretending that every decorative feature has a known mass.

No roof pieces, reactions, costs, or pass/fail results are generated from missing inputs. Later stages below remain the acceptance roadmap rather than being represented as completed work.

## 1. Why this workspace exists

The Structure workspace is not a place to display every fact the software can calculate. It is a place where three audiences make different decisions about the same building.

### Designer

The designer needs to answer:

- Can this room layout be supported without unwanted posts, dropped beams, or excessive floor depth?
- Where do upper walls, masonry, large openings, and roof intersections create difficult load paths?
- What structural choices materially affect ceiling height, room layout, stairs, services, cost, and appearance?
- Which parts of the design remain structurally undefined?

### Structural engineer

The engineer needs to answer:

- What is the complete load path from each floor and roof surface to soil?
- Where are reactions concentrated?
- What loads, spans, support conditions, materials, and combinations were assumed?
- Which strength, stability, deflection, vibration, connection, diaphragm, and foundation checks govern?
- Which assumptions are inferred, unresolved, or overridden?
- Can the calculation be reproduced and audited?

### Carpenter / timber framer

The builder needs to answer:

- Exactly which pieces are required?
- What are their imperial dimensions, grades/products, quantities, and cut lengths?
- Where does each piece go?
- What bears on what?
- How are openings framed?
- Which hangers, fasteners, straps, blocking, and temporary bracing are required?
- What sequence or detail is unusual?

These audiences inform the requirements; they do not require separate drawings or modes. A well-designed framing drawing can simultaneously support design review, engineering interpretation, estimating, and construction preparation. Information should be organized by coherent layers and questions, not artificially partitioned by job title.

## 2. Product principle

The canvas communicates **where**. The side panel communicates **what, how much, why, and whether it works**. Detailed calculations live in a calculation inspector. Construction details live on dedicated sheets.

The default view should show only information needed for the active question. Changing views or layers must not add piles of labels to the same plan.

## 2.1 Hard rule: no invented values

The application must never display a plausible-looking number that was fabricated merely to complete a drawing or calculation.

Every displayed value must be one of:

- **authored**: explicitly entered in the plan or Structure UI;
- **derived**: calculated deterministically from identified authored inputs;
- **catalogued**: taken from a named manufacturer, standard, supplier, or cost source;
- **assumed**: an explicit, configurable project assumption with visible provenance; or
- **unavailable**: shown as `Not set`, `Not calculated`, or an equivalent empty state.

Examples of legitimate configurable assumptions include:

- lumber species and grade;
- engineered-member product series;
- modulus of elasticity and design strengths;
- dead- and live-load allowances;
- snow, wind, seismic, and soil values;
- deflection and vibration limits;
- support fixity and continuity;
- local material, labour, equipment, delivery, tax, waste, and markup costs; and
- price date, currency, and region.

Assumptions must be editable in the Structure UI where they are relevant. Project-wide assumptions should have a dedicated assumptions editor; member-specific overrides belong in the calculation/member inspector.

The UI must show source and status without cluttering the drawing. For example, a schedule or inspector may use unobtrusive badges such as `Plan`, `Derived`, `Manufacturer`, `Project assumption`, or `Missing`. Tooltips and detail panels can expose the full source, date, formula, and revision.

Unknown must never be converted to zero, infinite capacity, a generic material property, or a successful result. A calculation with a missing required input is `Not calculated`, not `Pass`.

## 3. Units and notation

- User-facing dimensions and takeoffs are imperial by default.
- Lengths use feet and inches, matching the architectural plan: `18'-6"`.
- Lumber uses familiar nominal and actual descriptions: `2×10 SPF No. 2`, with actual dimensions available in details.
- Area loads may be displayed as psf; line loads as plf; point reactions as lb or kip.
- Metric values may be available as a preference, never mixed casually into an imperial drawing.
- Internal calculations may use SI, but conversion is confined to the analysis boundary.
- Internal YAML IDs never appear as primary drawing labels.

## 4. Information architecture

Keep the existing top-level **Plan / Structure** switch and the Structure pullout icon.

Within Structure, provide a shared drawing and several useful starting configurations. They are saved layer presets over one structural model and one CAD scene, not independent renderers or rigid actor-specific experiences.

A user may combine layers where the result remains legible. For example, a rafter layout can show spacing and member marks while also displaying a restrained stress/utilization overlay. The same geometry remains selectable, and its detailed values remain in the inspector.

Suggested presets:

- **Framing**: structural geometry, dimensions, member marks, openings, and bearing.
- **Loads**: framing plus tributary regions, applied loads, selected reactions, and load path.
- **Performance**: framing plus a selected deflection, force, stress, pressure, or utilization result.
- **Fabrication**: framing plus cut marks, member schedule, connection details, and assembly information.

Users can add or remove compatible layers from any preset.

### 4.1 Overview preset

Audience: designer and engineer.

Purpose: show whether the building has a complete, plausible load path and identify the few places needing attention.

Canvas:

- faithful grey architectural underlay using the existing wall renderer;
- structural floor and roof zones;
- bearing lines, primary beams, posts, masonry masses, and foundation support zones;
- incomplete regions shown as quiet neutral masks;
- a selected load path highlighted from source to soil;
- no individual joists unless selected or required to explain an opening;
- no calculation values scattered across the plan.

Panel:

- unresolved structural regions;
- largest reactions and why they occur;
- beams/posts affecting architecture;
- floor/roof depth and headroom effects;
- structural alternatives and rough cost difference;
- warnings such as unsupported wall, interrupted bearing line, or load terminating on an ordinary slab.

### 4.2 Framing and takeoff preset

Audience: carpenter, estimator, designer.

Purpose: describe a buildable framing system and derive credible material quantities.

Canvas:

- one level or roof at a time, not several tiny plans on one page;
- actual architectural walls, openings, stairs, chimney, and grids below;
- joist/rafter/truss layout clipped at real supports and openings;
- headers, trimmers, rim boards, blocking rows, beams, posts, and ledgers;
- member tags only; exact descriptions live in the schedule;
- existing architectural measurement ticks and datum dimensions;
- optional cut-length labels shown only while preparing a cut list;
- conventional ridge, hip, valley, jack-rafter, and opening geometry on roof plans.

Panel:

- system selector: floor, roof plane, wall, beam line, or opening;
- member schedule in plain language;
- piece count grouped by identical product and cut length;
- total linear feet, board feet or product-specific quantity;
- waste allowance shown separately;
- connectors and fasteners;
- supply cost, labour allowance, equipment allowance, and confidence range;
- missing information that prevents a construction takeoff.

Example schedule row:

| Mark | Description | Quantity | Cut length | Location |
|---|---|---:|---:|---|
| FJ-1 | 14-inch wood I-joist, selected series | 24 | 18'-0" | Master-wing floor |

The mark is useful because it connects the drawing to the schedule. The drawing does not need to spell out the entire row 24 times.

### 4.3 Load-path preset

Audience: designer and engineer.

Purpose: understand where loads originate, how they are collected, and where they reach the foundation.

Canvas interaction:

- hover/select a floor, wall, roof plane, beam, post, or foundation;
- everything unrelated fades;
- the selected object's upstream tributary region is shaded;
- downstream supporting objects are highlighted in order;
- reactions appear at the selected interfaces only;
- vertical level transitions are shown with a compact section or stacked-level strip;
- support discontinuities appear as explicit breaks, not guessed arrows.

Panel:

- breadcrumb such as `Master floor → west bearing line → transfer beam → two posts → reinforced pads → soil`;
- tributary area and assumed unfactored loads;
- service and factored reactions;
- load combination selector;
- foundation receiving area and pressure;
- unresolved connections in the path.

No generic `P1` or `P2` appears without context. Selecting a post should show “North end of master-wing transfer beam,” its location, reaction, member description, and receiving foundation.

### 4.4 Engineering/performance preset

Audience: engineer and technically engaged designer.

Purpose: compare demand, capacity, and serviceability for a selected structural object and load combination.

Canvas:

- selected result type: deflection, bending, shear, axial load, torsion, bearing pressure, or utilization;
- one clear legend with imperial units;
- restrained continuous colour scale where appropriate;
- unknown/unanalysed is visually distinct from pass;
- selecting a member opens its calculation inspector;
- deformed shapes are available on demand and clearly exaggerated.

Panel:

- load-combination selector with plain-language description;
- selected member/system and boundary conditions;
- demand, capacity, utilization, and governing check;
- typical-load deflection and configured limit;
- sensitivity or alternatives where useful;
- missing inputs and confidence.

Calculation inspector:

- geometry and support diagram;
- material/product properties and sources;
- applied point, line, and area loads;
- combination factors;
- formulas or solver method;
- intermediate values;
- results for every relevant failure/serviceability mode;
- provenance and model revision;
- explicit list of excluded checks.

This inspector is a peer to the existing Inspector/YAML panels. It is not drawn over the plan.

## 5. Roof framing must begin with topology

Roof framing cannot be generated by filling every rectangular mass with independent parallel rafters.

Required process:

1. Compile the finished roof envelope into actual roof planes.
2. Compute plane intersections.
3. Classify intersection edges as ridge, hip, valley, step, eave, or wall abutment.
4. Determine which edges provide bearing and which require structural ridge/valley members.
5. Divide each plane into rafter/truss tributary regions.
6. Generate common and jack members between valid endpoints.
7. Frame openings, tower penetrations, chimneys, and discontinuities.
8. Check member spans, accumulated valley/ridge loads, thrust, uplift, and support below.
9. Only then produce rafter counts and cut lengths.

Until that topology exists, the application should show “Roof framing not resolved” and produce no roof-lumber quantity.

## 6. Visual assets needed

Build these as reusable SVG components sharing the architectural renderer's scale, typography, dimensions, zoom, and selection system.

### 6.1 CAD presentation principles

The Structure canvas should follow professional architectural/structural CAD conventions rather than dashboard or infographic conventions.

- Maintain a stable model-space coordinate system and drawing scale.
- Reuse the architectural plan's geometry; do not approximate rooms with bounding boxes.
- Use disciplined lineweight hierarchy: cut/primary structure, secondary framing, context, dimensions, and analysis overlays.
- Use conventional linetypes consistently for hidden, centre, bearing, overhead, temporary, and unresolved geometry.
- Keep text horizontal where practicable and sized for the target plotted scale.
- Use member marks connected to schedules instead of repeated prose.
- Prevent label collisions with deterministic placement, leaders, suppression, and detail-scale thresholds.
- Use grids, datums, levels, dimensions, sections, and detail callouts consistently across Plan and Structure.
- Keep architectural context screened back but legible.
- Use colour as an optional screen aid, never as the only carrier of meaning; plotted output must work in monochrome.
- Analysis contours sit below structural linework and above the architectural underlay.
- Loads, reactions, and result labels appear only at the selected scope or appropriate detail scale.
- Provide layer visibility, isolation, object snapping, selection highlighting, and a clear drawing legend.
- Respect paper-space concerns: sheet size, viewport scale, title block, revision, drawing number, plotted lineweight, and printable schedules.
- Avoid decorative gradients, oversized badges, dashboard cards over drawings, arbitrary transparency, and unbounded label density.
- Use imperial architectural formatting consistently unless the user explicitly changes the project display units.

Layer order should normally be:

1. architectural underlay;
2. analysis field or tributary fill;
3. secondary framing;
4. primary framing and supports;
5. openings, connections, and detail marks;
6. dimensions, member marks, and selected result annotations;
7. selection and warning highlights.

### Architectural context

- faithful walls, openings, stairs, chimney, grids, and measurement ticks;
- grey structural-underlay theme;
- level and roof-plane clipping masks.

### Structural geometry

- bearing wall/line;
- beam by material family;
- post/column;
- joist, rafter, truss, stud and blocking;
- rim board, ledger, header and trimmer;
- ridge, hip, valley and jack rafter;
- diaphragm, chord, collector, shear wall and hold-down;
- footing, pad, grade beam and slab thickening;
- connection and hanger marks;
- section/elevation callout;
- unresolved-region mask.

### Analysis

- tributary-area fill;
- selected load-path highlight;
- point, line and area loads;
- reaction marker;
- force and deflection diagrams;
- utilization/deflection/pressure legend;
- unknown and not-analysed states;
- load-combination badge.

### Schedules and details

- member schedule;
- cut list;
- connector/fastener schedule;
- reaction/foundation schedule;
- assumptions/missing-input list;
- calculation trace;
- framing section and opening detail.

## 7. Structural model required before visualization

Do not infer a complete framing system solely from room rectangles.

The authored/approved model eventually needs:

- floor and roof structural zones;
- framing family and direction;
- exact supports and bearing lengths;
- member/product selections;
- real openings and required framing around them;
- primary beams and posts;
- connection intent;
- wall stacking and discontinuities;
- roof-plane topology;
- diaphragms and lateral-resisting systems;
- foundation elements and soil assumptions;
- construction versus conceptual status;
- source/approval metadata.

Derived members must retain their source zone and be editable/overridable.

Every numerical property must also retain:

- value and unit;
- status: authored, derived, catalogued, assumed, or unavailable;
- source identifier or formula;
- source date/revision where applicable;
- scope: project, system, member, connection, or load case;
- uncertainty or confidence where meaningful; and
- override history.

## 8. Quantity and cost rules

A credible framing quantity is the sum of actual purchasable pieces, not area multiplied by an arbitrary density.

For each framing system:

1. Generate members with real endpoints after openings and support conditions are resolved.
2. Group by product, grade, section, and cut length.
3. Convert cut lengths to available stock lengths.
4. Optimize cuts where appropriate.
5. Add separately modelled rim board, blocking, headers, trimmers, plates, hangers, fasteners, beams and posts.
6. Add configurable waste explicitly.
7. Price supply, labour, delivery, equipment, engineering and foundation consequences separately.
8. Show source, date, region, currency, and uncertainty.

Never label linear length as cubic volume. Never price an undefined product as if it were selected.

### 8.1 Framing families and alternatives

Framing alternatives must be separate structural schemes over the same zone, not cosmetic changes to one member list.

- **Solid-sawn lumber:** rectangular section properties may be calculated from actual width and depth. A board-foot regional price is an acceptable transparent fallback when no supplier stock table exists.
- **Engineered wood I-joists:** do not use solid-rectangle inertia, section modulus, or area. Capacity, stiffness, vibration limits, hole zones, bearing details, and price must come from a named manufacturer product and series.
- **Steel beams:** use a named steel section with catalogued area, mass, moments of inertia, section moduli, torsional properties, grade, connection assumptions, fire protection, and supplier price or weight-based regional price.
- **Built-up timber and engineered beams:** use the selected product or layup properties and connection model rather than treating the total bounding rectangle as solid wood.

An alternative comparison must report at least:

- beam count, beam lines, spans, and support reactions;
- joist family, joist span, spacing, count, and depth;
- posts, pads, hangers, blocking, connections, and bearing lengths;
- floor depth and architectural conflicts;
- strength, deflection, vibration, and other implemented checks;
- purchasable quantities and itemized cost; and
- unresolved inputs and excluded checks.

For example, a clear-span east-west joist scheme and a scheme with a north-south intermediate steel beam are different load-path graphs. The intermediate beam may reduce an 18-foot joist span to approximately 9 feet, but it also introduces end reactions, support/footing requirements, connections, fire protection, and coordination below. The application must compare all of those consequences rather than comparing joist depth alone.

Cost assumptions must be configurable in the UI and itemized. A regional default may seed a project assumption, but it must be visibly labelled with its location, currency, price date, source, and uncertainty. Changing an assumption must immediately identify which takeoff and total-cost rows it affects.

## 9. Performance architecture

Changing Structure subviews must be immediate.

- Structural compilation runs only after relevant plan/model changes.
- Analysis runs in a worker or server task and produces one versioned result bundle.
- Canvas subviews use that cached bundle locally.
- Changing level, result type, load combination, or selected member performs no network request and no structural recompilation.
- SVG assets are retained and restyled through layers/data attributes rather than regenerated for every toggle.
- Expensive roof topology or solver work is incremental and cancellable.
- Target view-switch latency: under 16 ms for cached data.
- Target selection/highlight latency: under 50 ms.
- The UI shows analysis progress only when the underlying model is actually recomputing.

## 10. Progressive implementation plan

Each stage must be useful on its own and reviewed visually before proceeding.

### Stage 1 — Structure shell and faithful underlay

- Keep Plan/Structure switch and pullout icon.
- Structure canvas reuses the real architectural drawing in a quiet underlay theme.
- One level at a time.
- Imperial dimensions only.
- No generated structural members.
- Review typography, spacing, selection, empty states, and visual hierarchy.
- Establish CAD layer names, lineweights, linetypes, plotted text sizes, monochrome output, and label-collision behaviour.

Acceptance: Structure view looks like the same house and is visually calm before structural data is added.

### Stage 2 — Authored primary load path

- Manually author bearing lines, primary beams, masonry loads, posts, and foundation receiving zones for one test bay.
- Overview and interactive load-path selection only.
- No automatic member sizing.

Acceptance: designer and engineer can agree on what supports what, with no unexplained labels.

### Stage 3 — One complete floor-framing bay

- Select one simple bay, likely the right-gable upper floor.
- Resolve walls/openings, supports, exact product candidate, joist endpoints, rim board, blocking, headers, trimmers and connectors.
- Produce a correct imperial member schedule, cut list, total linear feet and transparent cost.

Acceptance: a carpenter can review the bay and identify every missing construction decision; estimator can reproduce quantities.

All product and price inputs used in this stage must be entered or selected in the UI and retain visible provenance. Missing values must remain missing.

### Stage 4 — Gravity engineering for that bay

- Add code/site inputs and selectable combinations.
- Calculate reactions, bending, shear, bearing, deflection and vibration.
- Add calculation inspector and typical-load deflection view.
- Connect post reactions to defined pads.

Acceptance: engineer can reproduce the screening calculations and distinguish unknown from pass.

All material properties, load assumptions, limits, and combination inputs must be editable or catalog-linked. No fallback property may be used without becoming an explicit project assumption.

### Stage 5 — Roof topology

- Implement actual roof-plane intersections and ridge/hip/valley graph.
- Review topology visually before generating a single rafter.
- Add bearing/support decisions.
- Generate common/jack framing and takeoff for one roof region.

Acceptance: no member crosses a ridge, valley, hip, opening, or incompatible roof plane incorrectly.

### Stage 6 — Whole-house gravity and construction package

- Extend reviewed patterns across all floors and roofs.
- Add construction sheets, schedules, sections, details and revision control.
- Coordinate services and height impacts.

### Stage 7 — Lateral and advanced analysis

- Diaphragms, collectors, shear walls/frames, uplift, overturning, drift, torsional response and detailed foundations.
- Use a selected trusted solver and engineer-reviewed benchmarks.

## 11. First review artifact

Before writing another structural solver or generated-member renderer, create a static high-fidelity mockup for Stage 2 using the right-gable bay:

- faithful L1 and L2 architectural underlays;
- one selected upper-floor tributary zone;
- its two bearing lines;
- proposed west transfer element;
- alternate post arrangements;
- receiving foundation zones;
- a compact, plain-language side panel;
- imperial measurements;
- no calculations and no roof framing.

Review that mockup for comprehension and visual quality. Only after approval should the data model and interactive implementation begin.

## 12. Definition of success

The workspace succeeds when:

- a designer can locate structural consequences before they become architectural surprises;
- an engineer can audit assumptions, load paths, combinations and calculations;
- a carpenter can derive where each specified piece goes and how it connects;
- an estimator can reproduce quantities and costs;
- unresolved work is obvious without looking like failure or completed design;
- switching views is instantaneous;
- drawings remain readable at whole-level scale;
- no generated geometry claims more certainty than the model actually contains;
- no displayed number lacks provenance, an identified derivation, or an explicit assumption;
- compatible framing, load, and performance information can be layered on the same coherent CAD drawing;
- plotted drawings remain legible in monochrome at their stated scale.
