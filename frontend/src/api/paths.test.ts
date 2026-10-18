import { describe, expect, it } from "vitest";
import { artifactPath, proofPath } from "./paths";

describe("local artifact URLs", () => {
  it("keeps punctuation and path delimiters inside the saved ID segment", () => {
    expect(artifactPath("investigations", "saved/id?query#fragment")).toBe(
      "/api/investigations/saved%2Fid%3Fquery%23fragment",
    );
    expect(proofPath("saved/id")).toBe("/api/rehearsals/saved%2Fid/proof");
    expect(artifactPath("postmortems", "javascript:alert(1)")).toMatch(
      /^\/api\/postmortems\/javascript%3A/,
    );
  });
  it.each(["", ".", ".."])('rejects the invalid segment "%s"', (id) => {
    expect(() => artifactPath("rehearsals", id)).toThrow(
      "Invalid saved record identifier",
    );
  });
});
