// Response bodies shaped exactly like the API's (the types are the generated
// ones, so a schema change breaks these fixtures at compile time).
import type { Defaults, Run, Sheet, Tool, Workbook } from "../api/client";

export const COLUMNS = [
  "Article No", "Description", "Description 2", "Category", "Consumption 12 months",
  "Pack unit", "Location", "Stock", "System", "Supplier article no",
];

export const workbook: Workbook = {
  id: 7, sha256: "a".repeat(64), filename: "catalog.xlsx", size_bytes: 12345,
  uploaded_at: "2026-09-24T06:00:00Z", sheets: ["Cover", "Catalog"],
};

export const sheet: Sheet = {
  sheet: "Catalog", header_row: 1, columns: COLUMNS, row_count: 360,
  preview: [
    { "Article No": "SYN-00001", Description: "End mill D5 R0.5", "Description 2": "Sonder",
      Category: "Mills", "Consumption 12 months": 0, "Pack unit": 1, Location: "Line A",
      Stock: 51, System: null, "Supplier article no": "S89827" },
  ],
  headers_look_misplaced: false, suggested_header_row: 1,
  suggested_mapping: {
    code: "Article No", description: "Description", consumption: "Consumption 12 months",
    category: "Category", year: null, description_2: "Description 2", program: null,
    restocking: null, supplier_code: "Supplier article no", size: null, site: null,
    std_special: null, pack_units: "Pack unit", dimensions: null, regrind: null,
    system_type: "System", stock: "Stock",
  },
};

export const defaults: Defaults = {
  header_row: 1,
  planning: {
    use_description_2: true, year_mode: "all_rows", dedup_mode: "code_supplier",
    ktc_threshold: 1, optional_thresholds_active: false, per_class_thresholds: [],
    insert_pack_units: 10, helix_threshold: 6, consumption_months: 12,
    helix_overfill_factor: 1.1, min_carousel_allocation: 3, coverage_days: 20,
    coverage_days_special: 20, special_ktc: false, carousel_reserve_factor: 0.85,
    carousel_fill_ceiling: 1, enable_rebalancer: true, underuse_threshold_pct: 30,
    capacity_buffer_pct: 15, restock_categories: [], pack_hint_extraction: true,
    bulk_routing: false, force_screws_kanban: false, n_supply_points: 1,
    sp_mode: "replicate", calc_mode: "combined", op_mode: "", max_carousels: 2,
    fixed_headroom_pct: 10, fixed_allow_spill: true, fixed_stock_promotion: false,
    fixed_stock_months: 3, fixed_machines: [],
  },
  scope: { customer: "", site: "", ktc_id: "191", apply_overrides: true },
  export: { include_planogram: true, include_technical: false },
  limits: {
    header_row: [1, 50], ktc_threshold: [0, null], insert_pack_units: [1, null],
    helix_threshold: [0, null], consumption_months: [1, null],
    helix_overfill_factor: [1, null], min_carousel_allocation: [1, null],
    coverage_days: [1, 90], coverage_days_special: [1, 90],
    carousel_reserve_factor: [0.05, 2], carousel_fill_ceiling: [0.5, 1],
    underuse_threshold_pct: [5, 80], capacity_buffer_pct: [0, 200],
    n_supply_points: [1, 10], max_carousels: [1, 50], fixed_headroom_pct: [0, 90],
    fixed_stock_months: [0.5, 24],
  },
  labels: {
    op_mode: { "": "Standard (best fit per tool)" },
    sp_mode: { replicate: "Replicate - each item at every SP", partition: "Partition - each item at ONE SP" },
    calc_mode: { combined: "Combined", separated: "Separated" },
    year_mode: { all_rows: "Use all rows", latest_year_only: "Keep latest year only" },
    dedup_mode: { code_supplier: "Code + supplier", code_only: "Code only", none: "No deduplication" },
  },
  choices: { restock_categories: ["drills", "inserts", "mills"] },
};

const bucket = {
  position: 0, label: "All", ktc_count: 214, kanban_count: 146, helix_cabinets: 3,
  carousel_cabinets: 1, locker_a_cabinets: 0, locker_b_cabinets: 0, locker_c_cabinets: 0,
  total_cabinets: 4,
};

export function run(overrides: Partial<Run> = {}): Run {
  return {
    id: 11, workbook_id: workbook.id, status: "succeeded", engine_build: "v34.62",
    created_at: "2026-09-24T06:01:00Z", started_at: "2026-09-24T06:01:00Z",
    finished_at: "2026-09-24T06:01:02Z", settings: {}, error: null, notes: [],
    summary: {
      customer: "Synthetic", site: "Golden", grand: {}, buckets: [bucket],
      validation_issues: [], export_problems: [], export_notes: "",
    },
    reused: false,
    ...overrides,
  };
}

export const tools: Tool[] = [
  { line_no: 1, listing: "Tools", code: "SYN-00001", description: "End mill D5 R0.5",
    category: "mills", size: "S", pack_units: 1, system_category: "Kanban",
    cabinet_type: "Kanban", supply_point: 1, monthly_pcs: 0, monthly_packs: 0, spirals: 0,
    compartments: 0 },
  { line_no: 2, listing: "Tools", code: "SYN-00002", description: "Drill D8.5",
    category: "drills", size: "M", pack_units: 1, system_category: "KTC",
    cabinet_type: "Helix", supply_point: 1, monthly_pcs: 12.5, monthly_packs: 12.5, spirals: 2,
    compartments: 0 },
];
