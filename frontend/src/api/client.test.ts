import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../test/server";
import { ApiError, api, apiError, unwrap } from "./client";

describe("API errors", () => {
  it("read a plain detail", () => {
    const e = apiError(404, { detail: "No such run." });
    expect(e.message).toBe("No such run.");
    expect(e.status).toBe(404);
  });

  it("read a service error with its code", () => {
    const e = apiError(422, { detail: { code: "unknown_sheet", message: "No sheet 'X'.", details: null } });
    expect(e.message).toBe("No sheet 'X'.");
    expect(e.code).toBe("unknown_sheet");
  });

  it("list validation errors by field", () => {
    const e = apiError(422, {
      detail: [
        { loc: ["body", "settings", "planning", "coverage_days"], msg: "Input should be less than or equal to 90" },
        { loc: ["body"], msg: "Field required" },
      ],
    });
    expect(e.message).toBe(
      "settings > planning > coverage_days: Input should be less than or equal to 90\nField required",
    );
    expect(e.code).toBe("invalid_request");
  });

  it("fall back to the status", () => {
    expect(apiError(500, "Internal Server Error").message).toBe("The server answered with status 500.");
  });

  it("turn an unreachable server into a readable error", async () => {
    server.use(http.get("*/api/v1/health", () => HttpResponse.error()));
    await expect(unwrap(api.GET("/api/v1/health"))).rejects.toThrow(
      new ApiError(0, "The planner server cannot be reached. Is it running?"),
    );
  });

  it("return the data of a successful call", async () => {
    await expect(unwrap(api.GET("/api/v1/health"))).resolves.toMatchObject({ database: "ok" });
  });
});
