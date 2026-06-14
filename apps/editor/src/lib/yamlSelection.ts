import type { Selection } from "./types";

export function findYamlRangeForSelection(
  yamlText: string,
  selected: Selection
): { start: number; end: number } | null {
  const levelOffset = yamlText.indexOf(`  ${selected.level}:\n`);
  if (levelOffset < 0) {
    return null;
  }
  const nextLevelOffset = findNextLevelOffset(yamlText, levelOffset + 1);
  const levelEnd = nextLevelOffset >= 0 ? nextLevelOffset : yamlText.length;
  if (selected.kind === "space") {
    return findMappingEntryRange(yamlText, levelOffset, levelEnd, "spaces", selected.id);
  }
  if (selected.kind === "feature") {
    return findMappingEntryRange(yamlText, levelOffset, levelEnd, "features", selected.id);
  }
  if (selected.kind === "opening") {
    return findListItemRange(yamlText, levelOffset, levelEnd, "openings", `id: ${selected.id}`);
  }
  if (selected.kind === "connection") {
    const index = Number(selected.index ?? selected.id);
    return findIndexedListItemRange(yamlText, levelOffset, levelEnd, "connections", index);
  }
  return null;
}

function findNextLevelOffset(yamlText: string, after: number): number {
  const levelsHeader = yamlText.indexOf("levels:\n");
  if (levelsHeader < 0) {
    return -1;
  }
  const levelPattern = /\n  [A-Za-z0-9_-]+:\n/g;
  levelPattern.lastIndex = after;
  const match = levelPattern.exec(yamlText);
  return match ? match.index + 1 : -1;
}

function findMappingEntryRange(yamlText: string, levelStart: number, levelEnd: number, section: string, id: string) {
  const sectionStart = yamlText.indexOf(`    ${section}:\n`, levelStart);
  if (sectionStart < 0 || sectionStart > levelEnd) {
    return null;
  }
  const sectionEnd = findNextSectionOffset(yamlText, sectionStart + 1, levelEnd);
  const entryStart = yamlText.indexOf(`      ${id}:`, sectionStart);
  if (entryStart < 0 || entryStart >= sectionEnd) {
    return null;
  }
  return { start: entryStart, end: findNextEntryOffset(yamlText, entryStart + 1, sectionEnd, "      ") };
}

function findListItemRange(yamlText: string, levelStart: number, levelEnd: number, section: string, token: string) {
  const sectionStart = yamlText.indexOf(`    ${section}:\n`, levelStart);
  if (sectionStart < 0 || sectionStart > levelEnd) {
    return null;
  }
  const sectionEnd = findNextSectionOffset(yamlText, sectionStart + 1, levelEnd);
  const tokenOffset = yamlText.indexOf(token, sectionStart);
  if (tokenOffset < 0 || tokenOffset >= sectionEnd) {
    return null;
  }
  const itemStart = yamlText.lastIndexOf("\n      -", tokenOffset);
  if (itemStart < sectionStart) {
    return { start: tokenOffset, end: tokenOffset + token.length };
  }
  return { start: itemStart + 1, end: findNextEntryOffset(yamlText, itemStart + 2, sectionEnd, "      -") };
}

function findIndexedListItemRange(
  yamlText: string,
  levelStart: number,
  levelEnd: number,
  section: string,
  index: number
) {
  const sectionStart = yamlText.indexOf(`    ${section}:\n`, levelStart);
  if (sectionStart < 0 || sectionStart > levelEnd || index < 0) {
    return null;
  }
  const sectionEnd = findNextSectionOffset(yamlText, sectionStart + 1, levelEnd);
  const pattern = /\n      -/g;
  pattern.lastIndex = sectionStart;
  for (let current = 0; ; current += 1) {
    const match = pattern.exec(yamlText);
    if (!match || match.index >= sectionEnd) {
      return null;
    }
    if (current === index) {
      return {
        start: match.index + 1,
        end: findNextEntryOffset(yamlText, match.index + 2, sectionEnd, "      -")
      };
    }
  }
}

function findNextSectionOffset(yamlText: string, after: number, limit: number) {
  const pattern = /\n    [A-Za-z0-9_-]+:/g;
  pattern.lastIndex = after;
  const match = pattern.exec(yamlText);
  return match && match.index < limit ? match.index + 1 : limit;
}

function findNextEntryOffset(yamlText: string, after: number, limit: number, prefix: string) {
  const offset = yamlText.indexOf(`\n${prefix}`, after);
  return offset >= 0 && offset < limit ? offset + 1 : limit;
}
