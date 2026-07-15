# Repository working rules

These rules apply to the entire repository. They capture product decisions that must remain consistent across implementation, review, documentation, and generated visuals.

## Product language

- Use plain, complete professional language in user-facing text.
- Do not make the user decode abbreviations. Expand an unfamiliar organization, standard, calculation, material, or construction abbreviation on first use. Prefer the full name when space permits.
- Familiar drawing units such as `ft`, `in`, `psf`, `lb`, and `psi` may be used in schedules and fields. Do not use trade shorthand such as `o.c.` or `lin ft` when a clear label such as `Joist spacing (inches)` or `Cost per linear foot` fits.
- Put units and qualifiers in field labels, table headings, or dedicated unit columns. Do not place them inside editable values or as detached text after an input.
- Internal YAML IDs, implementation terminology, provenance mechanics, and formulas must not be the primary label on a drawing.
- Do not add editorial commentary, implementation commentary, conversational explanations, apologies, design-process notes, or developer instructions to the UI.
- Do not place secondary captions, explanatory microcopy, provenance notes, derivation notes, repeated input values, or qualifiers beneath panel values. Examples to avoid include `Plan geometry`, `Before waste`, repeated spacing, and `Governing check` captions.
- Present necessary information as concise labels, values, sources, statuses, schedules, warnings, or structured lists. Put longer rationale and workflow documentation in `docs/`, not in the application surface.
- Empty states should identify the missing item or unavailable result directly. They should not lecture the user or narrate why the implementation behaves that way.
- Framing-scheme names in selectors are limited to two words. Put distinctions and technical descriptions in schedules or detail fields.

## Structural data integrity

- Never display invented structural numbers, fake calculations, placeholder reactions, fabricated costs, or plausible-looking defaults without provenance.
- Every displayed value must be authored, deterministically derived, taken from an identified catalog/standard/source, or shown as an explicit editable project assumption.
- Unknown inputs produce `Not set`, `Not calculated`, `Unresolved`, or an equivalent state. Unknown must never silently become zero, a generic material property, infinite capacity, or a passing result.
- Assumptions must be configurable in the UI at the appropriate project, system, or member scope. Show the full source name; do not assume the user knows an acronym.
- Separate normal occupancy loading from exceptional objects. Distributed occupancy live load covers people and ordinary movable furniture. Heavy furniture/equipment may carry authored mass and footprint data and must affect the members under that footprint.
- Roof dead, snow, wind, and concentrated loads must follow actual roof-plane, ridge, hip, valley, wall, beam, post, and foundation topology. Do not spread roof load over a floor or invent a load path because topology is missing.
- A sizing recommendation must state which candidate passes the implemented checks, what load case and assumptions drive it, and what relevant checks remain unimplemented. Do not call a screening result engineer-approved or construction-ready.
- Costs must come from purchasable pieces and visible rates. Keep material, waste, labour, delivery, equipment, engineering, and foundation consequences distinguishable.

## Structural visualization

- Follow professional architectural and structural CAD conventions.
- Reuse the actual architectural geometry as the structural underlay. Do not approximate the house with room bounding boxes when real walls, openings, stairs, dimensions, and roof geometry are available.
- Present one useful drawing scale at a time. Text must remain readable at whole-plan zoom.
- Use a disciplined lineweight hierarchy: screened architectural context, analysis fields, secondary framing, primary framing/supports, connections/openings, dimensions/member marks, then selection/warnings.
- Keep annotations minimal. Prevent collisions. Prefer member marks connected to schedules over repeated prose.
- Use existing imperial measurement ticks and consistent feet-and-inches formatting.
- Colour may assist screen reading but must not be the sole information carrier. Printed output must remain understandable in monochrome.
- Compatible information may be composited as layers. Do not divide views rigidly by designer, engineer, carpenter, or estimator when one coherent drawing can serve several roles.
- Framing views must support quantity, cut preparation, placement, bearing, openings, connectors, cost, load transmission, and engineering review—not merely draw repeated joist or rafter lines.
- Roof framing begins with roof-plane intersections and classified ridge/hip/valley/eave topology. Never generate perpendicular rafter fields through intersecting gables.

## Performance and implementation

- Plan/Structure and structural layer switches must operate on cached local scene data. Do not make an analysis or render request for each view toggle.
- Recompute structural geometry only after relevant model changes. Keep cached view switching effectively immediate.
- Detailed calculations belong in a calculation inspector or structured detail panel, not scattered across the drawing.
- Preserve user-authored plan changes and unrelated dirty-worktree edits.
- Use `apply_patch` for hand edits, `rg` for searches, and verify TypeScript changes with type checking, focused tests, and a production build.
- Visually inspect substantial drawing or UI changes at normal whole-plan zoom before declaring them complete.

## Scope and completion

- Do not describe a single-bay prototype as a complete structural implementation for the house.
- State implemented and unresolved scope precisely in documentation and handoff notes.
- A structural region is complete only when its geometry, supports, loads, member/product definition, openings, connections, quantities, costs, checks, and downstream load path are represented or explicitly marked unresolved.
- Never disguise missing whole-house, roof, foundation, lateral, torsional, vibration, connection, or construction-detail work behind a polished visualization.
