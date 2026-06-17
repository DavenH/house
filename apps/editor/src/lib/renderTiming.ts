export const YAML_RENDER_DEBOUNCE_MS = 250;
export const LIVE_RENDER_INTERVAL_MS = 90;

export function liveRenderWait(now: number, lastRenderAt: number, interval = LIVE_RENDER_INTERVAL_MS) {
  return Math.max(0, interval - (now - lastRenderAt));
}
