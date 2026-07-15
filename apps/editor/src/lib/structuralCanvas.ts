import type { StructuralPreset, StructuralResult, StructuralSystem } from "./structuralWorkspace";

const NS = "http://www.w3.org/2000/svg";

export function applyStructuralCanvas(root: HTMLElement | undefined, system: StructuralSystem | null, preset: StructuralPreset, result: StructuralResult) {
  const svg = root?.querySelector("svg");
  if (!svg) return;
  svg.querySelector("#structural-overlay")?.remove();
  svg.classList.add("structural-drawing");
  svg.querySelectorAll<SVGGElement>('[data-fp-kind="level"]').forEach((group) => {
    group.style.display = system && group.dataset.fpLevel !== system.level ? "none" : "";
  });
  if (!system) return;
  const level = svg.querySelector<SVGGElement>(`[data-fp-kind="level"][data-fp-level="${cssEscape(system.level)}"]`);
  if (!level) return;
  const scale = drawingScale(level, system);
  if (!scale) return;
  const overlay = element("g", { id: "structural-overlay", "data-structural-preset": preset });
  const { x, y, width, height } = system.bounds;
  if (!system.authored) {
    overlay.append(element("rect", { class: "st-unresolved", x: x * scale, y: y * scale, width: width * scale, height: height * scale }));
    const title = element("text", { class: "st-system-label", x: (x + 0.6) * scale, y: (y + 1.1) * scale });
    title.textContent = `${system.name.toUpperCase()} · UNRESOLVED`;
    overlay.append(title);
    level.append(overlay);
    cropToLevel(svg, level);
    return;
  }
  if (system.kind === "stair_opening") {
    overlay.append(element("rect", { class: "st-opening", x: x * scale, y: y * scale, width: width * scale, height: height * scale }));
    const title = element("text", { class: "st-system-label", x: (x + 0.4) * scale, y: (y + 1) * scale });
    title.textContent = `${system.name.toUpperCase()}`;
    overlay.append(title);
    level.append(overlay);
    cropToLevel(svg, level);
    return;
  }
  if (preset === "loads") overlay.append(element("rect", { class: "st-tributary", x: x * scale, y: y * scale, width: width * scale, height: height * scale }));
  if (preset === "performance" && result) overlay.append(element("rect", { class: utilizationClass(Math.max(result.bendingUtilization, result.shearUtilization, result.deflectionUtilization)), x: x * scale, y: y * scale, width: width * scale, height: height * scale }));
  for (const opening of system.voidRects) overlay.append(element("rect", { class: "st-opening", x: opening.left * scale, y: opening.top * scale, width: (opening.right - opening.left) * scale, height: (opening.bottom - opening.top) * scale }));
  const supportClass = (kind: string) => kind.includes("steel") || kind.includes("transfer") ? "st-steel" : "st-bearing";
  const west = system.direction === "x"
    ? element("line", { class: supportClass(system.supports.west), x1: x * scale, y1: y * scale, x2: x * scale, y2: (y + height) * scale })
    : element("line", { class: supportClass(system.supports.west), x1: x * scale, y1: y * scale, x2: (x + width) * scale, y2: y * scale });
  const east = system.direction === "x"
    ? element("line", { class: supportClass(system.supports.east), x1: (x + width) * scale, y1: y * scale, x2: (x + width) * scale, y2: (y + height) * scale })
    : element("line", { class: supportClass(system.supports.east), x1: x * scale, y1: (y + height) * scale, x2: (x + width) * scale, y2: (y + height) * scale });
  overlay.append(west, east);
  for (const member of system.primaryMembers) {
    overlay.append(element("line", { class: "st-primary-scheme", x1: member.x1 * scale, y1: member.y1 * scale, x2: member.x2 * scale, y2: member.y2 * scale }));
  }
  if (system.coreRect) overlay.append(element("rect", { class: "st-core", x: system.coreRect.x * scale, y: system.coreRect.y * scale, width: system.coreRect.width * scale, height: system.coreRect.height * scale }));
  if (system.members.length) {
    const framing = element("g", { class: "st-secondary" });
    system.members.forEach((member) => framing.append(element("line", { x1: member.x1 * scale, y1: member.y1 * scale, x2: member.x2 * scale, y2: member.y2 * scale })));
    overlay.append(framing);
    const middle = system.direction === "x" ? x + width / 2 : y + height / 2;
    for (const interval of canvasIntervals(system, middle)) {
      overlay.append(system.direction === "x"
        ? element("line", { class: "st-blocking", x1: middle * scale, y1: interval[0] * scale, x2: middle * scale, y2: interval[1] * scale })
        : element("line", { class: "st-blocking", x1: interval[0] * scale, y1: middle * scale, x2: interval[1] * scale, y2: middle * scale }));
    }
  }
  if (system.zoneRects.length === 1) overlay.append(element("rect", { class: "st-rim", x: x * scale, y: y * scale, width: width * scale, height: height * scale }));
  if (preset === "loads") {
    overlay.append(element("path", { class: "st-load-path", d: `M ${(x + width / 2) * scale} ${(y + height / 2) * scale} H ${x * scale}` }));
  }
  const title = element("text", { class: "st-system-label", x: (x + 0.6) * scale, y: (y + 1.1) * scale });
  title.textContent = `${system.name.toUpperCase()} · ${system.status.toUpperCase()}`;
  overlay.append(title);
  level.append(overlay);
  cropToLevel(svg, level);
}

export function clearStructuralCanvas(root: HTMLElement | undefined) {
  const svg = root?.querySelector("svg");
  svg?.querySelector("#structural-overlay")?.remove();
  svg?.classList.remove("structural-drawing");
  svg?.querySelectorAll<SVGGElement>('[data-fp-kind="level"]').forEach((group) => (group.style.display = ""));
  if (svg) restoreSheet(svg);
}

function cropToLevel(svg: SVGSVGElement, level: SVGGElement) {
  if (!svg.dataset.structuralOriginalViewBox) {
    svg.dataset.structuralOriginalViewBox = svg.getAttribute("viewBox") ?? "";
    svg.dataset.structuralOriginalWidth = svg.getAttribute("width") ?? "";
    svg.dataset.structuralOriginalHeight = svg.getAttribute("height") ?? "";
  }
  const box = level.getBBox();
  const matrix = level.transform.baseVal.consolidate()?.matrix;
  const tx = matrix?.e ?? 0, ty = matrix?.f ?? 0, margin = 48;
  const width = Math.ceil(box.width + margin * 2), height = Math.ceil(box.height + margin * 2);
  const previousWidth = Number(svg.getAttribute("width")) || width;
  const displayedWidth = Number.parseFloat(svg.style.width) || previousWidth;
  const zoom = displayedWidth / previousWidth;
  svg.setAttribute("viewBox", `${box.x + tx - margin} ${box.y + ty - margin} ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.style.width = `${width * zoom}px`;
  svg.style.height = `${height * zoom}px`;
}

function restoreSheet(svg: SVGSVGElement) {
  const viewBox = svg.dataset.structuralOriginalViewBox;
  const width = svg.dataset.structuralOriginalWidth;
  const height = svg.dataset.structuralOriginalHeight;
  const croppedWidth = Number(svg.getAttribute("width")) || Number(width) || 0;
  const displayedWidth = Number.parseFloat(svg.style.width) || croppedWidth;
  const zoom = croppedWidth ? displayedWidth / croppedWidth : 1;
  if (viewBox !== undefined) svg.setAttribute("viewBox", viewBox);
  if (width !== undefined) svg.setAttribute("width", width);
  if (height !== undefined) svg.setAttribute("height", height);
  const restoredWidth = Number(width) || 0;
  if (restoredWidth) svg.style.width = `${restoredWidth * zoom}px`;
  if (height) svg.style.height = `${Number(height) * zoom}px`;
  delete svg.dataset.structuralOriginalViewBox;
  delete svg.dataset.structuralOriginalWidth;
  delete svg.dataset.structuralOriginalHeight;
}

function drawingScale(level: SVGGElement, system: StructuralSystem) {
  const space = level.querySelector<SVGRectElement>('[data-fp-kind="space"]');
  if (!space) return 0;
  const width = Number(space.getAttribute("width"));
  const modelSpace = level.querySelector<SVGRectElement>(`[data-fp-kind="space"][data-fp-id]`);
  if (!modelSpace || !width) return 0;
  // Architectural renderer currently uses a stable 16 drawing units per foot.
  // Verify against the system bounds when a matching zone is available.
  const candidate = level.querySelector<SVGRectElement>('[data-fp-kind="space"]');
  return candidate ? 16 : 0;
}
function element<K extends keyof SVGElementTagNameMap>(name: K, attrs: Record<string, string | number>) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}
function utilizationClass(value: number) { return value > 1 ? "st-result st-fail" : value > 0.85 ? "st-result st-near" : "st-result st-pass"; }
function cssEscape(value: string) { return CSS.escape(value); }
function canvasIntervals(system: StructuralSystem, coordinate: number): Array<[number, number]> {
  const intervals = system.zoneRects
    .filter((rect) => system.direction === "x" ? coordinate >= rect.left && coordinate <= rect.right : coordinate >= rect.top && coordinate <= rect.bottom)
    .map((rect): [number, number] => system.direction === "x" ? [rect.top, rect.bottom] : [rect.left, rect.right])
    .sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const interval of intervals) {
    const last = merged[merged.length - 1];
    if (!last || interval[0] > last[1]) merged.push([...interval]);
    else last[1] = Math.max(last[1], interval[1]);
  }
  const cuts = system.voidRects
    .filter((rect) => system.direction === "x" ? coordinate > rect.left && coordinate < rect.right : coordinate > rect.top && coordinate < rect.bottom)
    .map((rect): [number, number] => system.direction === "x" ? [rect.top, rect.bottom] : [rect.left, rect.right]);
  let result = merged;
  for (const cut of cuts) {
    const next: Array<[number, number]> = [];
    for (const segment of result) {
      if (cut[1] <= segment[0] || cut[0] >= segment[1]) next.push(segment);
      else {
        if (cut[0] > segment[0]) next.push([segment[0], Math.min(cut[0], segment[1])]);
        if (cut[1] < segment[1]) next.push([Math.max(cut[1], segment[0]), segment[1]]);
      }
    }
    result = next;
  }
  return result;
}
