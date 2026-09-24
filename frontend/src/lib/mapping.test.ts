import { describe, expect, it } from "vitest";

import { COLUMNS, sheet } from "../test/fixtures";
import {
  MAPPING_FIELDS, initialMapping, mappingKey, missingRequired, toMappingIn, validHeaderRow,
} from "./mapping";

describe("the column mapping", () => {
  it("covers every field the API accepts, required ones first", () => {
    expect(MAPPING_FIELDS.map((f) => f.field).sort()).toEqual(
      Object.keys(sheet.suggested_mapping).sort(),
    );
    expect(MAPPING_FIELDS.slice(0, 3).every((f) => f.required)).toBe(true);
    expect(MAPPING_FIELDS.slice(3).some((f) => f.required)).toBe(false);
  });

  it("starts from the suggestion, only with columns the sheet has", () => {
    const draft = initialMapping({ ...sheet.suggested_mapping, size: "Gone" }, COLUMNS);
    expect(draft.code).toBe("Article No");
    expect(draft.stock).toBe("Stock");
    expect(draft.size).toBeNull();
    expect(draft.year).toBeNull();
  });

  it("is incomplete while a required field is empty", () => {
    const draft = initialMapping({ ...sheet.suggested_mapping, consumption: null }, COLUMNS);
    expect(missingRequired(draft)).toEqual(["Consumption pcs"]);
    expect(toMappingIn(draft)).toBeNull();
  });

  it("sends every field, unmapped ones as null", () => {
    const body = toMappingIn(initialMapping(sheet.suggested_mapping, COLUMNS));
    expect(body).not.toBeNull();
    expect(Object.keys(body ?? {}).sort()).toEqual(Object.keys(sheet.suggested_mapping).sort());
    expect(body?.year).toBeNull();
  });
});

describe("the header row", () => {
  it("is a whole number from 1 to 50", () => {
    expect(validHeaderRow(1)).toBe(1);
    expect(validHeaderRow("4")).toBe(4);
    expect(validHeaderRow(50)).toBe(50);
    for (const bad of ["", 0, 51, 2.5, "x", -1]) expect(validHeaderRow(bad)).toBeNull();
  });

  it("with the workbook and sheet identifies a mapping", () => {
    expect(mappingKey(7, "Catalog", 1)).toBe(mappingKey(7, "Catalog", 1));
    expect(mappingKey(7, "Catalog", 1)).not.toBe(mappingKey(7, "Catalog", 2));
    expect(mappingKey(7, "a,b", 1)).not.toBe(mappingKey(7, "a", 1));
  });
});
