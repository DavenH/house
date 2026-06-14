# Ridgestone — Evolutionary Room-Topology Search

This repo builds an evolutionary search engine that generates **room adjacency graphs** (topologies) for the Ridgestone house, guided by **adjacency priors**, a few **hard constraints**, and optional **Pattern-Language-inspired** soft rules.

The output is not a floor plan; it’s a **topology**: which rooms connect by door/opening, optionally with corridor nodes.

---

## 1) Problem statement

We want to evolve graphs where:

- Nodes are rooms (e.g., `K`, `G`, `Pa`, `Pi`, `Rm`, etc.)
- Undirected edges mean **direct adjacency** (a doorway/opening).
- A special generic corridor node `Δ` stands for hallway / connecting area during search.
- After evolution, `Δ` can be **expanded** into `△1, △2, ...` via a post-pass (corridor splitting).

The engine should generate many candidates, score them, keep strong ones, and mutate/crossover them to improve.

---

## 2) Domain rules (rooms, priors, constraints)

### Room symbols

```text
U   mudroom / front entrance
UC  mudroom closet
T   tower (spans floors; lower use varies)
K   kitchen
Pa  pantry
D   dining
G   great room / living
H   hearth (central thermal mass)
Pi  piano area
Lb  library
O   office (can unify with Lb)
Fi  flex room
MR  machine room (can unify with La)
La  laundry
B   main bathroom
S   staircase
Mu  music studio
Lo  lounge (pool table)
Rm  master bedroom
W   walk-in closet
EB  ensuite bath
Ri  ith bedroom
Δ   corridor (generic during search)
```

### Priors

`p(A,B) ∈ [0,1]` is the prior probability that A directly connects to B.

These are independent priors; they do not sum to 1.

Use priors for:

- mutation edge-add / edge-drop bias, and/or
- scoring: reward edges that match priors, penalize edges that violate them.

The current priors are stored in `ridgestone/priors.py` as `PRIORS` and `PRIORS_SYM`.

If you treat graphs as undirected, always score using the symmetric `PRIORS_SYM`.

### Hard constraints (baseline)

Edges that must exist:

- `Pa—K` — pantry touches kitchen
- `H—G` — hearth touches great room
- `Rm—W` and `Rm—EB` — master suite adjacency

Edges that should be forbidden, or heavily penalized:

- `Ri—K` — kids’ bedroom directly off kitchen
- `Rm—K` — master directly off kitchen

These live in `ridgestone/priors.py` as `HARD_REQUIRE_EDGES` and `HARD_FORBID_EDGES`.

---

## 3) What the engine should produce

### Core deliverable

A `Topology` object representing:

- a set of rooms / nodes present on the level or levels being solved
- an undirected edge set
- optional metadata:
  - floor assignment per node, if doing multi-floor search
  - special node tags such as service, social, private

### Useful outputs

A list of the best N graphs with:

- score breakdown:
  - priors score
  - constraint penalties
  - structural heuristic scores
- adjacency list
- optional visualization:
  - Graphviz `.dot` export
  - networkx draw for quick sanity checks

---

## 4) Approach

### 4.1 Representation

Use a small immutable-ish graph representation for speed and hashing:

- `nodes: tuple[str, ...]` — fixed for a run
- `edges: frozenset[tuple[str, str]]` — store edges with `(min(a,b), max(a,b))`
- helper:
  - `neighbors(node) -> set[str]`

Corridor handling:

- During evolution include **at most one `Δ` node** as a generic corridor.
- After evolution, post-process to split `Δ` into multiple corridor nodes if needed.

### 4.2 Search modes

Implement at least these modes:

1. **Single-level topology**
   - evolve adjacency graphs for one floor’s room set

2. **Multi-level topology** — optional extension
   - assign nodes to floors, e.g. main vs upper
   - enforce `S` and vertical-stacking constraints
   - score cross-floor adjacency indirectly via stairs / stacked rooms

Start with single-level search. Build multi-level search later.

---

## 5) Fitness function

Total fitness is a weighted sum of terms.

### 5.1 Hard constraints — dominant

- If any required edge is missing:
  - apply a large penalty, or mark the individual invalid.
- If any forbidden edge is present:
  - apply a large penalty, or mark the individual invalid.

### 5.2 Prior likelihood — soft

For each unordered pair `(a,b)`, or for each possible edge candidate, define:

- If edge exists:
  - add `log(p(a,b) + eps)`
- Else:
  - add `log(1 - p(a,b) + eps)`

Where `p(a,b)` comes from:

```python
PRIORS_SYM.get(a, {}).get(b, default)
```

Recommended default:

```python
default = 0.03
eps = 1e-9
```

Practical tips:

- Only score pairs inside the current node set.
- For speed, precompute the `p(a,b)` table for all pairs at the start of a run.

### 5.3 Structural heuristics — Pattern-Language-ish

These should be soft and tunable.

#### Connectivity

The graph should be connected, or each floor component should be connected.

#### Degree sanity

Avoid very high degree in private rooms, such as:

- `Rm`
- `Ri`
- `EB`
- `W`

Discourage `Mu` becoming a junction.

#### Corridor discipline

Discourage `Δ` connecting strongly to everything.

Avoid `Δ` being the only route between `K—D—G`; the social triangle should be directly knit rather than hallway-mediated.

#### Intimacy gradient proxy

Prefer paths from entry `U` to private rooms such as `Rm` and `Ri` to pass through at least one transition node or public room, rather than direct adjacency.

Good transitional nodes include:

- `Δ`
- `G`
- `S`
- possibly `Lo`, depending on floor

Discourage direct adjacency from entry/service areas to deeply private rooms.

#### Service clustering

Mildly reward if `MR` and `La` cluster near:

- `U`
- `T`
- `Δ`

Rather than being deep in the social core.

Keep all heuristic terms simple and switchable.

---

## 6) Genetic operators

### 6.1 Initialization

Generate an initial population by:

1. Starting from an empty graph.
2. Force-adding all required edges.
3. Probabilistically adding edges:
   - for each candidate pair `(a,b)`, add with probability proportional to `p(a,b)` and a global density factor.
4. Optionally enforcing connectivity:
   - if disconnected, connect components via `Δ` or low-cost plausible edges.

### 6.2 Mutation

Provide several mutation moves, sampled randomly.

#### Edge flip

Choose `(a,b)` and add/remove the edge with bias using `p(a,b)`.

#### Degree-bounded add

Attempt to add an edge incident to a low-degree node.

#### Corridor rewiring

Move one connection from `Δ` to a direct connection, or vice versa.

This is useful to explore the tradeoff between hallway-mediated plans and more open-plan / half-open social spaces.

#### Swap a room identity — optional

Only implement this if using unification features later.

Examples:

- `O` vs `Lb`
- `La` vs `MR`

After every mutation, run a repair step.

Always preserve required edges after mutation.

### 6.3 Crossover

Implement a simple set-union / set-intersection crossover.

Possible strategy:

- child edges are sampled from `E1 ∪ E2`
- edges shared by both parents have higher survival probability
- optionally start with `E1 ∩ E2` and add a few sampled extras

Then:

- repair hard constraints
- optionally repair connectivity

---

## 7) API and project structure

Suggested structure:

```text
ridgestone/
  __init__.py
  priors.py              # PRIORS, PRIORS_SYM, helpers, hard constraints
  graph.py               # Topology representation + utilities
  scoring.py             # fitness terms
  evolve.py              # GA loop: selection, mutation, crossover
  postpass.py            # Δ splitting / corridor instantiation
  viz.py                 # dot / networkx export, optional

scripts/
  run_search.py          # CLI entry point
  show_best.py           # print + visualize topologies

tests/
  test_graph.py
  test_scoring.py
```

### CLI

Provide a CLI like:

```bash
python -m scripts.run_search \
  --rooms U UC T K Pa D G H Pi Lb O B MR La S St \
  --pop 500 \
  --gens 500 \
  --seed 0 \
  --density 0.18 \
  --topk 25 \
  --out out/best.json
```

Rooms passed are the nodes present in this run, i.e. one level’s room set.

---

## 8) Acceptance checks — what “good” looks like

A good run should produce topologies where:

- Hard constraints are always satisfied.
- `K—Pa` and `G—H` are present.
- The social triangle tends to be present:
  - `K—D`
  - `D—G`
  - `K—G`
- Not necessarily all three social edges are required, but they should appear often.
- Bathrooms connect via transition `Δ` more than directly to `G`.
- Studio `Mu` is reachable from `G` and/or `Pi`, but is not a central junction.
- Private rooms connect through `Δ` rather than directly to the kitchen.
- The hearth behaves like a place / anchor, not like a corridor node.
- The piano is visually and socially connected to the great room, but does not become circulation.
- The library can form a quiet edge or alcove near the social/music core.

---

## 9) Implementation notes / gotchas

- Use `PRIORS_SYM` for scoring if edges are undirected.
- Use `eps = 1e-9` in log-likelihood to avoid `log(0)`.
- Do not score pairs involving nodes not in the current run’s node set.
- Keep `Δ` optional:
  - allow solutions with no corridor node at all.
- Repair step after any operator:
  - enforce required edges
  - remove forbidden edges
  - optionally enforce connectivity
- Avoid making pairwise priors do all the work:
  - use heuristic penalties for things like “studio became a junction” or “private room has too many doors.”
- Keep all weights configurable.
- Prefer deterministic reproducibility:
  - every run should accept a random seed.
- Store full score breakdowns:
  - debugging evolutionary search is much easier when the score is explainable.

---

## 10) Next extensions — optional

After single-level topology works:

### Multi-floor topology

Add:

- node → floor assignment
- stair constraints
- vertical path constraints
- stacking preferences for:
  - bathrooms
  - laundry / mechanical
  - plumbing walls

### Corridor splitting post-pass

Replace `Δ` with multiple corridor nodes to reduce degree.

Example:

- one `Δ` connected to eight rooms may become:
  - `△1` for entry/service
  - `△2` for private bedrooms
  - `△3` for upstairs distribution

The post-pass should preserve reachability while improving intimacy-gradient structure.

### Room unification mode

Allow optional merged nodes:

- `O = Lb`
- `La = MR`

This can be done as a mutation that toggles the merge state, or as a preprocessing choice.

### Floor-specific prior overrides

Some priors should change by floor.

For example:

- `Lo` likely upstairs
- `Rm`, `Ri`, `EB`, `W` likely upstairs
- `K`, `Pa`, `D`, `G`, `H`, `Pi` likely main floor
- `MR`, `La`, `U`, `UC` likely main floor

Add floor-aware scoring only after the graph search works.

---

## 11) Current priors source of truth

The prior adjacency table and hard constraints are in:

```text
ridgestone/priors.py
```

This file is treated as authoritative.

A representative priors file should include:

- `Room`
- `Priors`
- `DELTA`
- `PRIORS`
- `symmetrize_priors`
- `get_p`
- `HARD_REQUIRE_EDGES`
- `HARD_FORBID_EDGES`
- `PRIORS_SYM`

---

## 12) Recommended implementation order for Codex

Implement in this order:

1. `priors.py`
   - copy in current `PRIORS`
   - implement `symmetrize_priors`
   - implement `get_p`

2. `graph.py`
   - implement `Topology`
   - implement normalized undirected edges
   - implement neighbor queries
   - implement connectivity check

3. `scoring.py`
   - implement hard constraint score
   - implement prior likelihood score
   - implement simple structural heuristic score
   - return a score breakdown object

4. `evolve.py`
   - implement initialization
   - implement mutation
   - implement crossover
   - implement tournament selection or truncation selection
   - implement best-N tracking

5. `scripts/run_search.py`
   - parse CLI args
   - run evolution
   - write JSON output

6. `viz.py`
   - optional but useful
   - export `.dot`

7. `postpass.py`
   - optional later
   - split generic `Δ` into instantiated corridor nodes

---

## 13) Minimal scoring breakdown shape

Prefer a score breakdown like:

```python
@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    prior: float
    hard: float
    connectivity: float
    degree: float
    corridor: float
    intimacy: float
    service: float
```

This makes debugging much easier.

---

## 14) Minimal output JSON shape

Use a format like:

```json
{
  "seed": 0,
  "rooms": ["U", "UC", "T", "K", "Pa", "D", "G", "H", "Pi", "Lb", "O", "B", "MR", "La", "S", "St"],
  "best": [
    {
      "rank": 1,
      "score": {
        "total": -42.31,
        "prior": -38.20,
        "hard": 0.0,
        "connectivity": 0.0,
        "degree": -1.1,
        "corridor": -2.0,
        "intimacy": -0.7,
        "service": -0.3
      },
      "edges": [
        ["K", "Pa"],
        ["K", "D"],
        ["D", "G"],
        ["G", "H"],
        ["G", "Pi"],
        ["G", "St"]
      ]
    }
  ]
}
```

---

## 15) Philosophical design target

The search should not merely maximize adjacency probability.

It should prefer topologies that feel like:

- a warm central hearth / great-room anchor
- a bright kitchen-dining-social core
- a grand piano visible from multiple social views
- a semi-decoupled studio that is easy to reach but not a pass-through
- a quiet library / office edge
- service spaces grouped near the entry/mudroom/mechanical side
- a gradual transition from public to private
- minimal “warehouse plan” feel
- enough asymmetry and hierarchy to support the Ridgestone aesthetic

The engine should search for plausible room relationships, not finished architecture.
