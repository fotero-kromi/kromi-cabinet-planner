import { describe, expect, it } from "vitest";

import { defaults } from "../test/fixtures";
import {
  NOT_ON_FORM, SETTING_FIELDS, SETTING_GROUPS, type FieldContext, fieldLabel, getValue, setValue,
  visibleFields,
} from "./settingFields";
import { initialSettings } from "./settings";

const ctx = (patch: Partial<FieldContext> = {}): FieldContext => ({
  settings: initialSettings(defaults), stdSpecialMapped: false, opMode: "", ...patch,
});
const keys = (c: FieldContext) => visibleFields(SETTING_FIELDS, c).map((f) => f.key);

describe("the setting descriptions", () => {
  it("name settings the API has, with a kind that fits the value", () => {
    for (const f of SETTING_FIELDS) {
      const value = (defaults[f.section] as Record<string, unknown>)[f.key];
      const expected = { number: "number", checkbox: "boolean", select: "string", radio: "string",
                         text: "string", multiselect: "array" }[f.kind];
      expect(Array.isArray(value) ? "array" : typeof value, `${f.section}.${f.key}`).toBe(expected);
    }
  });

  it("cover every setting or say why it is not on the form", () => {
    for (const section of ["planning", "scope", "export"] as const) {
      for (const key of Object.keys(defaults[section])) {
        const described = SETTING_FIELDS.some((f) => f.section === section && f.key === key);
        const excluded = `${section}.${key}` in NOT_ON_FORM;
        expect(described !== excluded, `${section}.${key}`).toBe(true);
      }
    }
  });

  it("are unique and belong to a known group", () => {
    const ids = SETTING_FIELDS.map((f) => `${f.section}.${f.key}`);
    expect(new Set(ids).size).toBe(ids.length);
    const groups = new Set(SETTING_GROUPS.map((g) => g.id));
    for (const f of SETTING_FIELDS) expect(groups.has(f.group), f.key).toBe(true);
  });

  it("take their choices from the server", () => {
    for (const f of SETTING_FIELDS) {
      if (f.kind === "select" || f.kind === "radio") expect(defaults.labels[f.labels], f.key).toBeDefined();
      if (f.kind === "multiselect") expect(defaults.choices[f.choices], f.key).toBeDefined();
    }
  });

  it("show the special coverage only with a Standard/Special column", () => {
    expect(keys(ctx())).not.toContain("coverage_days_special");
    expect(keys(ctx())).not.toContain("special_ktc");
    expect(keys(ctx({ stdSpecialMapped: true }))).toEqual(
      expect.arrayContaining(["coverage_days_special", "special_ktc"]));
    const coverage = SETTING_FIELDS.find((f) => f.key === "coverage_days")!;
    expect(fieldLabel(coverage, ctx())).toBe("On-machine stock coverage (days)");
    expect(fieldLabel(coverage, ctx({ stdSpecialMapped: true }))).toBe(
      "On-machine stock coverage (standard, in days)");
  });

  it("show the empty-cabinet threshold only while consolidation is on", () => {
    const off = initialSettings(defaults);
    off.planning.enable_rebalancer = false;
    expect(keys(ctx())).toContain("underuse_threshold_pct");
    expect(keys(ctx({ settings: off }))).not.toContain("underuse_threshold_pct");
  });

  it("hide what the Streamlit page hides per operation mode", () => {
    const fixed = keys(ctx({ opMode: "Fixed" }));
    for (const key of ["carousel_fill_ceiling", "enable_rebalancer", "underuse_threshold_pct",
                       "capacity_buffer_pct"]) {
      expect(fixed, key).not.toContain(key);
    }
    expect(keys(ctx({ opMode: "Helix" }))).not.toContain("restock_categories");
    expect(keys(ctx({ opMode: "NumberingOnly" }))).not.toContain("restock_categories");
    expect(keys(ctx())).toContain("restock_categories");
  });

  it("mark the advanced settings", () => {
    const advanced = SETTING_FIELDS.filter((f) => f.advanced).map((f) => f.key);
    expect(advanced).toContain("helix_overfill_factor");
    expect(advanced).not.toContain("ktc_threshold");
  });

  it("read and write a value without changing the original", () => {
    const s = initialSettings(defaults);
    const field = SETTING_FIELDS.find((f) => f.key === "helix_threshold")!;
    const next = setValue(s, field, 2);
    expect(getValue(next, field)).toBe(2);
    expect(getValue(s, field)).toBe(6);
    const site = SETTING_FIELDS.find((f) => f.section === "scope" && f.key === "site")!;
    expect(setValue(s, site, "Golden").scope.site).toBe("Golden");
  });
});
