export type ArtifactKind = "investigations" | "rehearsals" | "postmortems";

/** Keep saved identifiers inside one path segment, including dot-only segments. */
export function artifactPath<K extends ArtifactKind>(
  kind: K,
  id: string,
): `/api/${K}/${string}` {
  if (!id || id === "." || id === "..")
    throw new Error("Invalid saved record identifier.");
  return `/api/${kind}/${encodeURIComponent(id)}`;
}
export function proofPath(id: string): `/api/rehearsals/${string}/proof` {
  return `${artifactPath("rehearsals", id)}/proof`;
}
