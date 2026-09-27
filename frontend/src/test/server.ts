// A stand-in for the back end: the happy path by default; a test replaces a
// handler with server.use(...) to try another answer.
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import * as fx from "./fixtures";

const API = "*/api/v1";

export const handlers = [
  http.get(`${API}/health`, () => HttpResponse.json({ status: "ok", build: "v34.62", database: "ok" })),
  http.get(`${API}/settings/defaults`, () => HttpResponse.json(fx.defaults)),
  http.post(`${API}/workbooks`, () => HttpResponse.json(fx.workbook, { status: 201 })),
  http.get(`${API}/workbooks/:id/sheets/:sheet`, ({ params, request }) => {
    const headerRow = Number(new URL(request.url).searchParams.get("header_row") ?? 1);
    return HttpResponse.json({ ...fx.sheet, sheet: String(params.sheet), header_row: headerRow });
  }),
  http.post(`${API}/workbooks/:id/mapping/check`, () =>
    HttpResponse.json({ ok: true, conflicts: {}, missing_columns: [] })),
  http.post(`${API}/runs`, () => HttpResponse.json(fx.run({ status: "queued", summary: null }), { status: 202 })),
  http.get(`${API}/runs/:id`, () => HttpResponse.json(fx.run())),
  http.get(`${API}/runs/:id/tools`, () => HttpResponse.json(fx.tools)),
];

export const server = setupServer(...handlers);
