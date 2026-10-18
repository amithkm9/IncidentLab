import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, requestRecoveryProof } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("HTTP boundary failures", () => {
  it("preserves a stale-record conflict without reporting success", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: "The lab revision changed." }),
            { status: 409 },
          ),
        ),
    );
    await expect(
      api("/api/promote", { rehearsal_id: "old", plan_id: "plan-1" }),
    ).rejects.toMatchObject({
      status: 409,
      message: "The lab revision changed.",
    });
  });
  it("exposes a useful connection failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Network error")),
    );
    await expect(api("/api/workspace")).rejects.toMatchObject({
      connectionLost: true,
    });
  });
  it("rejects an unreadable response", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>proxy error</html>", { status: 502 }),
        ),
    );
    await expect(api("/api/workspace")).rejects.toBeInstanceOf(ApiError);
  });
  it("requests an explicit proof without a request body or automatic retry", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "The proof could not complete." }),
          { status: 500 },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    await expect(requestRecoveryProof("record-1")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetch).toHaveBeenCalledExactlyOnceWith(
      "/api/rehearsals/record-1/proof",
      { method: "POST" },
    );
  });
});
