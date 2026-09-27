import { describe, expect, it } from "vitest";

import { COLUMNS, defaults, sheet } from "../test/fixtures";
import { initialMapping } from "./mapping";
import { buildRunRequest, initialSettings, settingsProblems, shownNumberSettings } from "./settings";

const draft = () => initialSettings(defaults);

describe("the settings", () => {
  it("start from the server's defaults", () => {
    const s = draft();
    expect(s.planning.helix_threshold).toBe(6);
    expect(s.scope.ktc_id).toBe("191");
    expect(s.export.include_planogram).toBe(true);
  });

  it("do not share objects with the defaults", () => {
    const s = draft();
    s.planning.helix_threshold = 1;
    expect(defaults.planning.helix_threshold).toBe(6);
  });

  it("show the special coverage only with a Standard/Special column", () => {
    expect(shownNumberSettings(draft(), false)).not.toContain("coverage_days_special");
    expect(shownNumberSettings(draft(), true)).toContain("coverage_days_special");
  });

  it("hide the empty-cabinet threshold while consolidation is off", () => {
    const s = draft();
    s.planning.enable_rebalancer = false;
    expect(shownNumberSettings(s, false)).not.toContain("underuse_threshold_pct");
    expect(shownNumberSettings(draft(), false)).toContain("underuse_threshold_pct");
  });

  it("report values outside the engine's limits, empty ones and fractions", () => {
    const s = draft();
    s.planning.coverage_days = 120;
    s.planning.carousel_reserve_factor = 0.01;
    s.planning.helix_threshold = Number.NaN;
    s.planning.n_supply_points = 1.5;
    expect(settingsProblems(s, defaults.limits, shownNumberSettings(s, false))).toEqual([
      "Helix threshold (packs per month): enter a number.",
      "On-machine stock coverage (days): at most 90.",
      "Carousel reserve factor: at least 0.05.",
      "Number of supply points: a whole number.",
    ]);
    expect(settingsProblems(draft(), defaults.limits, shownNumberSettings(draft(), false))).toEqual([]);
  });

  it("build the run request the API accepts", () => {
    const s = draft();
    s.scope.ktc_id = " 191 ";
    const req = buildRunRequest("Catalog", 2, initialMapping(sheet.suggested_mapping, COLUMNS), s);
    expect(req).toMatchObject({ sheet: "Catalog", header_row: 2, program_to_sp: {} });
    expect(req?.scope.ktc_id).toBe("191");
    expect(req?.planning).toEqual(defaults.planning);
    expect(req?.mapping.code).toBe("Article No");
  });

  it("build no request while the mapping is incomplete", () => {
    const mapping = initialMapping({ ...sheet.suggested_mapping, code: null }, COLUMNS);
    expect(buildRunRequest("Catalog", 1, mapping, draft())).toBeNull();
  });
});
