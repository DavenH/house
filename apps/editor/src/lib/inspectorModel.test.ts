import { describe, expect, it } from "vitest";

import { relationData, relationIncludesPair, roundHalf, sameKey, splitList, uniqueListId } from "./inspectorModel";

describe("inspectorModel", () => {
  it("normalizes compact relation data", () => {
    expect(relationData(["hall", "kitchen"])).toEqual({ between: ["hall", "kitchen"] });
    expect(relationData({ between: ["hall", "kitchen"], kind: "arch" })).toEqual({
      between: ["hall", "kitchen"],
      kind: "arch"
    });
  });

  it("formats common inspector list and id values", () => {
    expect(splitList(" hall, kitchen ,, pantry ")).toEqual(["hall", "kitchen", "pantry"]);
    expect(sameKey(["x", "w"])).toBe("x,w");
    expect(roundHalf(2.74)).toBe(2.5);
    expect(uniqueListId([{ id: "front_door" }, { id: "front_door_2" }], "front door")).toBe("front_door_3");
  });

  it("matches relation endpoint pairs regardless of order", () => {
    expect(relationIncludesPair({ between: ["hall", "kitchen"] }, ["kitchen", "hall"])).toBe(true);
    expect(relationIncludesPair({ between: ["hall", "kitchen"] }, ["kitchen", "pantry"])).toBe(false);
  });
});
