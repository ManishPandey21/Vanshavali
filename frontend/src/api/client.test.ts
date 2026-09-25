import { describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, buildUrl, readCookie, setUnauthenticatedHandler } from "./client";
import { jsonResponse } from "../test/utils";

/** Resolves with the rejection so assertions can inspect the typed error. */
const failure = (p: Promise<unknown>): Promise<ApiError> =>
  p.then(
    () => {
      throw new Error("expected the request to fail");
    },
    (e: ApiError) => e,
  );

describe("api client", () => {
  it("sends X-CSRF-Token from the vsh_csrf cookie on unsafe methods, with credentials", async () => {
    document.cookie = "vsh_csrf=tok%3D123";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/trees", { method: "POST", body: { name: "x" } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/trees");
    expect(init.credentials).toBe("include");
    expect(init.headers["X-CSRF-Token"]).toBe("tok=123");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ name: "x" });
  });

  it("does not send the CSRF header on GET", async () => {
    document.cookie = "vsh_csrf=abc";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/trees");
    expect(fetchMock.mock.calls[0][1].headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("parses structured errors into a typed ApiError with field errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "validation_error",
              message: "Invalid request",
              details: [{ loc: ["body", "names", 0, "given_name"], msg: "Value error, too long", type: "value_error" }],
            },
          },
          422,
        ),
      ),
    );
    const err = await failure(apiRequest("/x", { method: "POST", body: {} }));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("validation_error");
    expect(err.message).toBe("Invalid request");
    expect(err.fieldErrors()).toEqual({ "names.0.given_name": "too long" });
  });

  it("maps 403 to a forbidden ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ error: { code: "forbidden", message: "nope", details: null } }, 403)));
    const err = await failure(apiRequest("/x"));
    expect(err.isForbidden).toBe(true);
  });

  it("invokes the unauthenticated handler on 401 unless skipped", async () => {
    const handler = vi.fn();
    setUnauthenticatedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => jsonResponse({ error: { code: "unauthenticated", message: "Authentication required" } }, 401)));
    await apiRequest("/trees").catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
    await apiRequest("/auth/me", { skipAuthRedirect: true }).catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(1);
    setUnauthenticatedHandler(null);
  });

  it("reports network failures as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    const err = await failure(apiRequest("/x"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });

  it("builds query strings with repeated array params and skips empty values", () => {
    expect(buildUrl("/a", { lineage: ["biological", "legal"], q: "", depth: 3, x: undefined })).toBe("/api/v1/a?lineage=biological&lineage=legal&depth=3");
    expect(readCookie("b", "a=1; b=two")).toBe("two");
  });
});
