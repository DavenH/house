# Goals

## Overall goal

Build a beautiful craftsman house using $300k CAD in Keswick Ridge.

The house constraints and specifications are in 

The best aligned visual reference is this set of visual references:
    image-refs/double-gable-175-storey


## Evaluate the best room layout topology

I want to be able to quantify how "good" alterations to room layout structure are. Instrumentally
we need a way to easily represent room layouts. Could be topological, as in pairwise nodes.

Then we also need a metric to evaluate these. I think it would involve enumerating daily usage patterns, "user stories"
as we call it in software engineering.

E.g.
- arrive home with heavy bags of groceries in hand and drop them off 
- spend a day in the office, visiting the bathroom two or three times, the piano twice, the kitchen once
- carry in firewood from outdoors
- host a dinner party and retire to living room
- host a games night with big game spread out 
- etc

With these, we could understand pain points and minimize costs.

After creating a metric, some genetic algorithm search could be how we evaluate options.

## Create house DSL spec

This should be able to express a house design in yaml, in the most compressed possible form: without 
explicit mesh geometry, which if obeying conventions is very compressible due to parallel lines, parallel planes, 
and implied factors; but in a form that has enough specification so that precise mesh geometry can be 
concretely compiled for visualization.

The interactive editor design for making these YAML plans editable without chat-driven round trips is in:
    docs/design/floor-plan-editor-webapp.md

## Evaluate house design against Canadian National Building Code 

This is a huge PDF and needs RAG-ifying:
/home/daven/Documents/Paperwork/Engineering/NBC2025p1.pdf

Then it would be useful for validating house designs against, e.g. load cases, acceptable roof pitch, setbacks and so on.


## Define foundation pad perimeter

Understand the size of the concrete pad from room layouts.
Calculate load requirements.

## Create an architecture plan

## Create an engineering plan

I need a plan that can be approved by an engineer before we can begin pouring the pad, as everything will be 
loading on top of this, so its specifications need to be known. Unless we can overbuild so much that there won't be
any impact on pad design, but I think knowledge of load will be required due to materials used.  
