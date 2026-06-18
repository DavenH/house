import { describe, expect, it } from "vitest";

import { liveRenderWait } from "./renderTiming";

describe("renderTiming", () => {
  it("calculates remaining throttle delay", () => {
    expect(liveRenderWait(100, 20, 90)).toBe(10);
    expect(liveRenderWait(120, 20, 90)).toBe(0);
  });
});
