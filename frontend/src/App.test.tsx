// The four steps as a user goes through them, against the stand-in back end.
import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import App from "./App";
import type { RunRequest } from "./api/client";
import * as fx from "./test/fixtures";
import { renderApp } from "./test/render";
import { server } from "./test/server";

const API = "*/api/v1";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

async function choose(user: UserEvent, label: string | RegExp, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

async function upload(user: UserEvent) {
  const file = new File(["PK"], "catalog.xlsx", { type: XLSX });
  await user.upload(screen.getByLabelText("Excel file"), file);
  await screen.findByRole("combobox", { name: "Tools sheet" });
}

async function toSettings(user: UserEvent) {
  await upload(user);
  await choose(user, "Tools sheet", "Catalog");
  await screen.findByText("SYN-00001");
  const next = screen.getByRole("button", { name: "Next" });
  await waitFor(() => expect(next).toBeEnabled());
  await user.click(next);
  await screen.findByRole("button", { name: "Run planning" });
}

describe("the planner", () => {
  it("shows the engine build and the four steps", async () => {
    renderApp(<App />);
    expect(await screen.findByText("Engine v34.62")).toBeInTheDocument();
    for (const step of ["Upload", "Sheet and columns", "Settings", "Run and results"]) {
      expect(screen.getByText(step)).toBeInTheDocument();
    }
  });

  it("reports a file the server refuses", async () => {
    server.use(http.post(`${API}/workbooks`, () => HttpResponse.json(
      { detail: { code: "unreadable_workbook", message: "The file is not an Excel workbook (.xlsx) that can be read." } },
      { status: 422 })));
    const { user } = renderApp(<App />);
    await user.upload(screen.getByLabelText("Excel file"), new File(["x"], "notes.xlsx", { type: XLSX }));
    expect(await screen.findByText("The file is not an Excel workbook (.xlsx) that can be read.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Tools sheet" })).not.toBeInTheDocument();
  });

  it("preselects no sheet and fills the mapping from the suggestion", async () => {
    const { user } = renderApp(<App />);
    await upload(user);
    expect(screen.getByRole("combobox", { name: "Tools sheet" })).toHaveValue("");
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await choose(user, "Tools sheet", "Catalog");
    expect(await screen.findByText("SYN-00001")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Code" })).toHaveValue("Article No");
    expect(screen.getByRole("combobox", { name: "Current stock pcs" })).toHaveValue("Stock");
    expect(screen.getByRole("combobox", { name: "Year" })).toHaveValue("");
    expect(screen.getByText("First 1 of 360 rows")).toBeInTheDocument();
  });

  it("offers the header row the server suggests", async () => {
    server.use(http.get(`${API}/workbooks/:id/sheets/:sheet`, ({ request }) => {
      const row = Number(new URL(request.url).searchParams.get("header_row"));
      return HttpResponse.json({ ...fx.sheet, header_row: row, headers_look_misplaced: row === 1,
                                 suggested_header_row: 4 });
    }));
    const { user } = renderApp(<App />);
    await upload(user);
    await choose(user, "Tools sheet", "Catalog");
    expect(await screen.findByText(/Row 4 looks like the header row/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use row 4" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Header row in the sheet" })).toHaveValue("4"));
    await waitFor(() => expect(screen.queryByText(/Row 4 looks like the header row/)).not.toBeInTheDocument());
  });

  it("blocks a mapping the server finds conflicting", async () => {
    server.use(http.post(`${API}/workbooks/:id/mapping/check`, () => HttpResponse.json(
      { ok: false, conflicts: { Description: ["Description", "ProductCategory"] }, missing_columns: [] })));
    const { user } = renderApp(<App />);
    await upload(user);
    await choose(user, "Tools sheet", "Catalog");
    expect(await screen.findByText("'Description' is mapped to: Description, ProductCategory")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("asks for every required column", async () => {
    server.use(http.get(`${API}/workbooks/:id/sheets/:sheet`, () => HttpResponse.json(
      { ...fx.sheet, suggested_mapping: { ...fx.sheet.suggested_mapping, consumption: null } })));
    const { user } = renderApp(<App />);
    await upload(user);
    await choose(user, "Tools sheet", "Catalog");
    expect(await screen.findByText("Choose a column for: Consumption pcs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await choose(user, "Consumption pcs", "Consumption 12 months");
    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeEnabled());
  });

  it("refuses settings outside the engine's limits", async () => {
    const { user } = renderApp(<App />);
    await toSettings(user);
    const coverage = screen.getByRole("textbox", { name: "On-machine stock coverage (days)" });
    await user.clear(coverage);
    await user.type(coverage, "120");
    expect(await screen.findByText("On-machine stock coverage (days): at most 90.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run planning" })).toBeDisabled();
  });

  it("warns about a KTC-ID that is not three digits", async () => {
    const { user } = renderApp(<App />);
    await toSettings(user);
    const ktc = screen.getByRole("textbox", { name: "KTC-ID" });
    await user.clear(ktc);
    await user.type(ktc, "19");
    expect(screen.getByText(/The KTC-ID must be exactly 3 digits/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run planning" })).toBeEnabled();
  });

  it("runs with the chosen mapping and settings and shows the result", async () => {
    let sent: { workbook_id: number; settings: RunRequest } | null = null;
    server.use(http.post(`${API}/runs`, async ({ request }) => {
      sent = (await request.json()) as typeof sent;
      return HttpResponse.json(fx.run({ status: "queued", summary: null }), { status: 202 });
    }));
    const { user } = renderApp(<App />);
    await upload(user);
    await choose(user, "Tools sheet", "Catalog");
    await screen.findByText("SYN-00001");
    await user.click(screen.getByRole("button", { name: "Clear System type available" }));
    await user.click(screen.getByRole("button", { name: "Clear Current stock pcs" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Next" }));

    const helix = await screen.findByRole("textbox", { name: "Helix threshold (packs per month)" });
    await user.clear(helix);
    await user.type(helix, "1");
    const empty = screen.getByRole("textbox", { name: "Empty-cabinet threshold (%)" });
    await user.clear(empty);
    await user.type(empty, "50");
    await user.type(screen.getByRole("textbox", { name: "Customer" }), "Synthetic");
    await user.type(screen.getByRole("textbox", { name: "Site" }), "Golden");
    await user.click(screen.getByRole("button", { name: "Run planning" }));

    expect(await screen.findByText("Total cabinets")).toBeInTheDocument();
    expect(sent).not.toBeNull();
    const settings = sent!.settings;
    expect(sent!.workbook_id).toBe(fx.workbook.id);
    expect(settings.sheet).toBe("Catalog");
    expect(settings.header_row).toBe(1);
    expect(settings.mapping).toMatchObject({ code: "Article No", system_type: null, stock: null,
                                             description_2: "Description 2" });
    expect(settings.planning).toEqual({ ...fx.defaults.planning, helix_threshold: 1,
                                        underuse_threshold_pct: 50 });
    expect(settings.scope).toEqual({ ...fx.defaults.scope, customer: "Synthetic", site: "Golden" });

    const totals = screen.getByRole("region", { name: "Totals" });
    expect(within(totals).getByText("Total cabinets").nextSibling).toHaveTextContent("4");
    expect(within(totals).getByText("KTC articles").nextSibling).toHaveTextContent("214");
    expect(screen.getByRole("link", { name: "Download result workbook" })).toHaveAttribute(
      "href", "/api/v1/runs/11/workbook");
    expect(await screen.findByText("SYN-00002")).toBeInTheDocument();
  });

  it("follows a run until it finishes", async () => {
    let polls = 0;
    server.use(http.get(`${API}/runs/:id`, () => {
      polls += 1;
      return HttpResponse.json(polls < 2 ? fx.run({ status: "running", summary: null }) : fx.run());
    }));
    const { user } = renderApp(<App />);
    await toSettings(user);
    await user.click(screen.getByRole("button", { name: "Run planning" }));
    expect(await screen.findByText("Planning the cabinets...")).toBeInTheDocument();
    expect(await screen.findByText("Total cabinets", {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("shows why a run failed", async () => {
    server.use(http.get(`${API}/runs/:id`, () => HttpResponse.json(fx.run({
      status: "failed", summary: null,
      error: { code: "unassigned_programs", message: "Every programme needs a supply point before planning.",
               details: { programs: ["Line A"] } } }))));
    const { user } = renderApp(<App />);
    await toSettings(user);
    await user.click(screen.getByRole("button", { name: "Run planning" }));
    expect(await screen.findByText("Every programme needs a supply point before planning.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Download result workbook" })).not.toBeInTheDocument();
  });

  it("says when a stored result is reused", async () => {
    server.use(http.post(`${API}/runs`, () => HttpResponse.json(fx.run({ reused: true }))),
               http.get(`${API}/runs/:id`, () => HttpResponse.json(fx.run())));
    const { user } = renderApp(<App />);
    await toSettings(user);
    await user.click(screen.getByRole("button", { name: "Run planning" }));
    expect(await screen.findByText(/planned before \(run 11\)/)).toBeInTheDocument();
  });

  it("shows the server's refusal of a run request", async () => {
    server.use(http.post(`${API}/runs`, () => HttpResponse.json(
      { detail: [{ loc: ["body", "settings", "planning", "op_mode"], msg: "Value error, only the standard operation mode is available in this version" }] },
      { status: 422 })));
    const { user } = renderApp(<App />);
    await toSettings(user);
    await user.click(screen.getByRole("button", { name: "Run planning" }));
    expect(await screen.findByText(/only the standard operation mode/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run planning" })).toBeInTheDocument();
  });

  it("goes back to the settings from the result and keeps them", async () => {
    const { user } = renderApp(<App />);
    await toSettings(user);
    const helix = screen.getByRole("textbox", { name: "Helix threshold (packs per month)" });
    await user.clear(helix);
    await user.type(helix, "2");
    await user.click(screen.getByRole("button", { name: "Run planning" }));
    await screen.findByText("Total cabinets");
    await user.click(screen.getByRole("button", { name: "Change settings" }));
    expect(await screen.findByRole("textbox", { name: "Helix threshold (packs per month)" })).toHaveValue("2");
  });
});
