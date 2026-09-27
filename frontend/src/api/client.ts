// The typed API client. Its types are generated from the back end's OpenAPI
// schema (openapi.json -> schema.d.ts, `npm run gen:api`); nothing here is
// written by hand except the error handling.
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Workbook = Schemas["WorkbookOut"];
export type Sheet = Schemas["SheetOut"];
export type Defaults = Schemas["DefaultsOut"];
export type MappingIn = Schemas["ColumnMappingIn"];
export type MappingCheck = Schemas["MappingCheckOut"];
export type PlanningIn = Schemas["PlanningIn"];
export type ScopeIn = Schemas["ScopeIn"];
export type ExportIn = Schemas["ExportIn"];
export type RunRequest = Schemas["RunRequest"];
export type Run = Schemas["RunOut"];
export type Bucket = Schemas["BucketOut"];
export type Tool = Schemas["ToolOut"];

export const api = createClient<paths>({
  // Same origin as the page: the Vite dev server forwards /api, and in
  // production the back end serves the page itself.
  baseUrl: globalThis.location?.origin ?? "",
  // Looked up on every call, so test doubles installed later are used.
  fetch: (request: Request) => globalThis.fetch(request),
});

export const workbookDownloadUrl = (runId: number): string =>
  `/api/v1/runs/${runId}/workbook`;

/** An API call that did not succeed, with the text to show the user. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: unknown;

  constructor(status: number, message: string, code: string | null = null, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type ValidationItem = { loc?: unknown[]; msg?: string };

/** The message of a FastAPI error body: a text, a {code, message} object from the
 *  services, or Pydantic's list of validation errors. */
export function apiError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const lines = (detail as ValidationItem[]).map((item) => {
      const where = (item.loc ?? []).filter((p) => p !== "body").join(" > ");
      return where ? `${where}: ${item.msg ?? "invalid"}` : (item.msg ?? "invalid");
    });
    return new ApiError(status, lines.join("\n") || "The request was refused.", "invalid_request", detail);
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const d = detail as { code?: string; message: string; details?: unknown };
    return new ApiError(status, d.message, d.code ?? null, d.details ?? null);
  }
  return new ApiError(status, `The server answered with status ${status}.`);
}

/** The data of an openapi-fetch call, or an ApiError. */
export async function unwrap<R extends { data?: unknown; error?: unknown; response: Response }>(
  call: Promise<R>,
): Promise<NonNullable<R["data"]>> {
  let result: R;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, "The planner server cannot be reached. Is it running?");
  }
  if (!result.response.ok || result.data === undefined) {
    throw apiError(result.response.status, result.error);
  }
  return result.data as NonNullable<R["data"]>;
}

/** The settings defaults. openapi-fetch widens fixed-length lists (the
 *  per-class thresholds and machine rows) in responses to plain lists; the
 *  schema's own type is restored here. */
export async function fetchDefaults(): Promise<Defaults> {
  return (await unwrap(api.GET("/api/v1/settings/defaults"))) as Defaults;
}

/** Uploads a workbook as a multipart form (the file field is binary). */
export function uploadWorkbook(file: File): Promise<Workbook> {
  return unwrap(
    api.POST("/api/v1/workbooks", {
      body: { file: file as unknown as string },
      bodySerializer: () => {
        const form = new FormData();
        form.append("file", file);
        return form;
      },
    }),
  );
}
