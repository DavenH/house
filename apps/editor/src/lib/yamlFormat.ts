import type { AnyRecord } from "./types";

export function dumpPlanYaml(value: unknown) {
  return `${dumpBlock(value, 0, [])}\n`;
}

function dumpBlock(value: unknown, indent: number, path: string[]): string {
  if (Array.isArray(value)) {
    return dumpList(value, indent, path);
  }
  if (!isPlainObject(value)) {
    return `${" ".repeat(indent)}${inlineValue(value)}`;
  }
  return Object.entries(value)
    .map(([key, child]) => dumpMappingEntry(key, child, indent, path))
    .join("\n");
}

function dumpMappingEntry(key: string, value: unknown, indent: number, path: string[]) {
  const prefix = `${" ".repeat(indent)}${yamlKey(key)}:`;
  const childPath = [...path, key];
  if (shouldInline(childPath, value)) {
    return `${prefix} ${inlineValue(value)}`;
  }
  if (Array.isArray(value)) {
    return value.length ? `${prefix}\n${dumpList(value, indent + 2, childPath)}` : `${prefix} []`;
  }
  if (isPlainObject(value)) {
    const entries = Object.keys(value);
    return entries.length ? `${prefix}\n${dumpBlock(value, indent + 2, childPath)}` : `${prefix} {}`;
  }
  return `${prefix} ${inlineValue(value)}`;
}

function dumpList(values: unknown[], indent: number, path: string[]) {
  if (values.length === 0) {
    return `${" ".repeat(indent)}[]`;
  }
  return values
    .map((item) => {
      const prefix = `${" ".repeat(indent)}-`;
      if (shouldInlineListItem(path, item)) {
        return `${prefix} ${inlineValue(item)}`;
      }
      if (Array.isArray(item) || isPlainObject(item)) {
        return `${prefix}\n${dumpBlock(item, indent + 2, path)}`;
      }
      return `${prefix} ${inlineValue(item)}`;
    })
    .join("\n");
}

function shouldInline(path: string[], value: unknown) {
  if (!Array.isArray(value) && !isPlainObject(value)) {
    return false;
  }
  if (path[0] === "datums" && path.length === 2) {
    return true;
  }
  if (path[0] === "catalog" && path.length === 2) {
    return true;
  }
  if (path[0] === "masses" && path.length === 2 && path[1] !== "shared_body") {
    return true;
  }
  if (path[0] === "masses" && path.length === 3 && path[2] === "rect") {
    return true;
  }
  if (path[0] === "levels" && path.length === 4 && ["spaces", "features"].includes(path[2])) {
    return true;
  }
  return false;
}

function shouldInlineListItem(path: string[], value: unknown) {
  if (!Array.isArray(value) && !isPlainObject(value)) {
    return false;
  }
  const last = path[path.length - 1];
  if (["rects", "connections", "access", "openings", "stacks", "alignments"].includes(last)) {
    return true;
  }
  return path.length === 1 && path[0] === "notes" ? false : Array.isArray(value);
}

function inlineValue(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(inlineValue).join(", ")}]`;
  }
  if (isPlainObject(value)) {
    return `{${Object.entries(value)
      .map(([key, child]) => `${yamlKey(key)}: ${inlineValue(child)}`)
      .join(", ")}}`;
  }
  if (typeof value === "string") {
    return yamlString(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value === null || value === undefined) {
    return "null";
  }
  return yamlString(String(value));
}

function yamlKey(key: string) {
  return isPlainYamlToken(key) ? key : yamlString(key);
}

function yamlString(value: string) {
  if (value === "") {
    return "''";
  }
  if (isPlainYamlToken(value)) {
    return value;
  }
  return `'${value.replace(/'/g, "''")}'`;
}

function isPlainYamlToken(value: string) {
  return /^[A-Za-z0-9_.\/-]+$/.test(value) && !["true", "false", "null", "~"].includes(value.toLowerCase());
}

export function isPlainObject(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
