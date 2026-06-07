I am going to build an evolutionary search engine for generating room topologies for each level in the Ridgestone house. 

There is this set of rooms by symbol:

U - mudroom / front entrance room
UC - mudroom closet for hanging coats, boots etc
T - tower, spans 2+ floors; at lower level can be storage, mudroom closet, or pantry depending on what is next to it
D - dining room
K - kitchen
Pa - pantry
Pi - piano
G - great room / living room
Li - library 
O - office
B - main bathroom
MR - machine room
Fi - ith flex room
S - staircase
La - laundry room
H - hearth
Rm - master bedroom
W - walk in closet
EB - ensuite bathroom
Lo - lounge
Ri - ith bedroom
△i - a connecting hallway or area (the ith one if there are several)

So, to effectively and efficiently search through possibilities, I am thinking a pairwise map of probabilities representing the likelihood of choosing these rooms as neighbours or direct connections. 

For instance:
- p(Rm, W) should be near 1, because the walk-in closet should be right off the master bedroom almost all the time
- p(Rm, EB) should also be near 1
- so, connections[Rm] would be something like { ... W: 0.9, EB: 0.9, ... S: 0.02, K: 0.01, ...  } (note these don't have to sum to one, because multiple rooms can be connected to one another
- connections[S] would be something like { ... G: 0.4, △4: 0.3, ... } (I am not clear on how to decide which if any hallway area to be assigned to a particular item, in a context-free manner..., choosing 4 for example)
- connections[G] could be like { ... K: 0.7, D: 0.5, S: 0.5, Li: 0.5, Pi: 0.8, B: 0.4... }

Could you please give me a matrix of connection probabilities, possibly defined sparsely if you decide most of the entries would be zero. This way I can use it for evolutionary search. Thank you!




------
Initial Results: 

# Ridgestone evolutionary topology priors
# Sparse adjacency priors: p(A,B) in [0,1] is the prior probability that A directly connects to B.
# Unlisted pairs can be treated as ~0.00–0.05 (your choice) for exploration.

from __future__ import annotations
from typing import Dict, Mapping

Room = str
Priors = Dict[Room, Dict[Room, float]]

# Use a single generic corridor node "Δ" during search.
# You can later expand it to △1, △2, ... in a post-pass.
DELTA: Room = "Δ"

PRIORS: Priors = {
    # Entry / service cluster
    "U":  {"UC":0.95, "T":0.40, "S":0.45, "B":0.25, "La":0.30, "MR":0.25, DELTA:0.55, "Fi":0.20},
    "UC": {"U":0.95, "T":0.55, DELTA:0.20},
    "T":  {"UC":0.55, "U":0.40, "Pa":0.45, "K":0.25, "MR":0.25, "La":0.20, DELTA:0.25},
    "MR": {"La":0.55, "B":0.25, "U":0.25, "T":0.25, DELTA:0.40, "Fi":0.20},
    "La": {"MR":0.55, "U":0.30, "B":0.35, DELTA:0.35, "Fi":0.20},

    # Kitchen / dining / pantry core
    "K":  {"Pa":0.95, "D":0.70, "G":0.65, DELTA:0.35, "T":0.25, "B":0.20},
    "Pa": {"K":0.95, "D":0.20, "T":0.45, "U":0.10, "MR":0.20},
    "D":  {"K":0.70, "G":0.55, DELTA:0.20, "Pi":0.25, "Li":0.20},

    # Social / view core
    "G":  {"H":0.95, "K":0.65, "D":0.55, "S":0.55, "Pi":0.75, "Li":0.45, "B":0.25, DELTA:0.35},
    "H":  {"G":0.95, DELTA:0.25},
    "Pi": {"G":0.75, "D":0.25, "Li":0.25, DELTA:0.20},
    "Li": {"G":0.45, "O":0.45, "Pi":0.25, DELTA:0.25, "D":0.20},

    # Office / flex
    "O":  {"Li":0.45, DELTA:0.55, "B":0.25, "Fi":0.35},
    "Fi": {DELTA:0.55, "O":0.35, "Lo":0.25, "U":0.20, "MR":0.20, "La":0.20},

    # Bathrooms (main/shared)
    "B":  {DELTA:0.60, "G":0.25, "U":0.25, "O":0.25, "La":0.35, "MR":0.25, "S":0.25},

    # Stairs + circulation
    "S":  {"G":0.55, "U":0.45, DELTA:0.65, "Lo":0.35, "Rm":0.15},
    DELTA: {"S":0.65, "B":0.60, "U":0.55, "O":0.55, "Lo":0.55, "Ri":0.60, "Rm":0.45,
            "G":0.35, "K":0.35, "MR":0.40, "La":0.35},

    # Upper private zone (master suite + bedrooms + lounge)
    "Rm": { "W":0.95, "EB":0.95, DELTA:0.45, "S":0.15},
    "W":  { "Rm":0.95, "EB":0.20, DELTA:0.10},
    "EB": { "Rm":0.95, "W":0.20, DELTA:0.35},
    "Lo": { DELTA:0.55, "S":0.35, "Fi":0.25, "B":0.20},
    "Ri": { DELTA:0.60, "B":0.30, "S":0.20},
}

# --- Optional helpers ---------------------------------------------------------

def symmetrize_priors(priors: Mapping[Room, Mapping[Room, float]]) -> Priors:
    """
    Ensure PRIORS is symmetric: p(A,B) == p(B,A) == max(original values).
    Useful if you treat adjacency as undirected.
    """
    out: Priors = {a: dict(neis) for a, neis in priors.items()}
    for a, neis in priors.items():
        out.setdefault(a, {})
        for b, p in neis.items():
            out.setdefault(b, {})
            out[a][b] = max(out[a].get(b, 0.0), p)
            out[b][a] = max(out[b].get(a, 0.0), p)
    return out

def get_p(priors: Mapping[Room, Mapping[Room, float]],
          a: Room, b: Room,
          default: float = 0.03) -> float:
    """Fetch p(a,b) with a small exploration default for missing entries."""
    if a == b:
        return 0.0
    return priors.get(a, {}).get(b, priors.get(b, {}).get(a, default))

# Example "hard-ish" constraints you might enforce separately
HARD_REQUIRE_EDGES = {
    ("Pa", "K"),  # pantry must touch kitchen
    ("H", "G"),   # hearth must touch great room
    ("Rm", "W"),  # master suite closet adjacency
    ("Rm", "EB"), # master ensuite adjacency
}

# Example "hard forbid" edges (can be penalties instead if you want exploration)
HARD_FORBID_EDGES = {
    ("Ri", "K"), ("K", "Ri"),
    ("Rm", "K"), ("K", "Rm"),
}

# If you want the canonical symmetric version:
PRIORS_SYM = symmetrize_priors(PRIORS)
