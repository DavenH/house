import { describe, expect, it } from "vitest";

import { buildConstraintRefs } from "./selectionModel";

describe("selectionModel", () => {
  it("builds room and feature refs with display labels", () => {
    expect(
      buildConstraintRefs({
        levels: {
          L1: {
            spaces: {
              great_room: { label: "GREAT/ROOM" }
            },
            features: {
              piano: { kind: "piano", label: "PIANO" },
              table: { kind: "rectangle" }
            }
          }
        }
      })
    ).toEqual([
      { value: "L1.great_room", label: "L1 room: GREAT ROOM" },
      { value: "L1.piano", label: "L1 feature: PIANO" },
      { value: "L1.table", label: "L1 feature: rectangle" }
    ]);
  });
});
