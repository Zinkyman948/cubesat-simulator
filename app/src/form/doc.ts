// Editing the scenario YAML by path while keeping its comments and layout.
//
// The YAML text is the single source of truth: the form reads values from
// it and writes changes back into it, so the YAML tab and the form are
// always two views of the same scenario.

import { Document, parseDocument } from "yaml";

export type Path = (string | number)[];

export interface Parsed {
  doc: Document | null;
  data: Record<string, unknown> | null;
  error: string | null;
}

export function parseScenario(text: string): Parsed {
  const doc = parseDocument(text);
  if (doc.errors.length > 0) return { doc: null, data: null, error: doc.errors[0].message };
  const data = doc.toJS();
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    return { doc: null, data: null, error: "The scenario must be a YAML mapping." };
  }
  return { doc, data, error: null };
}

/** Apply `edit` to a fresh parse of `text` and return the new text. */
export function editScenario(text: string, edit: (doc: Document) => void): string {
  const doc = parseDocument(text);
  edit(doc);
  // Keep compact flow maps like {gain_dbi: 0.0} as written in the examples.
  return doc.toString({ flowCollectionPadding: false });
}

export function pathKey(path: Path): string {
  return path.join(".");
}

export function getIn(data: unknown, path: Path): unknown {
  let node: unknown = data;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[key];
  }
  return node;
}
