// One description per setting: what kind of input it is, its label and help
// (the Streamlit page's texts), its group, whether it is an advanced setting,
// and when it is shown. The settings form renders any list of these; defaults,
// limits and choice labels come from the server (engine/planning_defaults.py).
import type { Defaults } from "../api/client";
import type { SettingsDraft } from "./settings";

export type Section = keyof SettingsDraft;

export type GroupId = "run" | "routing" | "vend" | "supply" | "workbook";

export const SETTING_GROUPS: readonly { id: GroupId; title: string }[] = [
  { id: "run", title: "Run setup" },
  { id: "routing", title: "Routing and sizing" },
  { id: "vend", title: "Vend-mode controls" },
  { id: "supply", title: "Supply points and planning base" },
  { id: "workbook", title: "Result workbook" },
];

/** What decides whether a field is shown and how it is labelled. */
export interface FieldContext {
  settings: SettingsDraft;
  /** a Standard/Special column is mapped */
  stdSpecialMapped: boolean;
  /** operation-mode token ("" = Standard, "Helix", "Carousel", "Capped", "Fixed", "NumberingOnly") */
  opMode: string;
}

interface Base {
  section: Section;
  key: string;
  label: string | ((ctx: FieldContext) => string);
  help?: string;
  group: GroupId;
  /** a candidate for the advanced side panel (the redesign settles the list) */
  advanced: boolean;
  /** operation modes in which the Streamlit page hides the field */
  hiddenInModes?: readonly string[];
  /** further condition for showing the field */
  showWhen?: (ctx: FieldContext) => boolean;
}

export type SettingField =
  | (Base & { kind: "number"; step: number; decimals: number })
  | (Base & { kind: "checkbox" })
  | (Base & { kind: "select" | "radio"; labels: string })
  | (Base & { kind: "multiselect"; choices: string })
  | (Base & { kind: "text"; maxLength?: number; warning?: (value: string) => string | null });

export type NumberField = Extract<SettingField, { kind: "number" }>;

const FIXED = "Fixed";
/** The fixed configuration replaces these with the headroom set with the machines. */
const NOT_IN_FIXED = [FIXED];

export const KTC_ID_PATTERN = /^\d{3}$/;

export const SETTING_FIELDS: readonly SettingField[] = [
  // ---- Run setup ----
  { section: "scope", key: "ktc_id", kind: "text", group: "run", advanced: false, maxLength: 3,
    label: "KTC-ID",
    help: "The 3-digit customer/installation ID that starts every generated KROMI article number.",
    warning: (v) => KTC_ID_PATTERN.test(v.trim()) ? null
      : "The KTC-ID must be exactly 3 digits. Until it is, no KROMI article numbers are generated "
        + "and the Article setup sheet is left out of the export." },
  { section: "scope", key: "customer", kind: "text", group: "run", advanced: false,
    label: "Customer", help: "Recorded with the run and in the Run_Metadata sheet." },
  { section: "scope", key: "site", kind: "text", group: "run", advanced: false,
    label: "Site", help: "Plant or site; recorded like the customer." },

  // ---- Routing and sizing ----
  { section: "planning", key: "ktc_threshold", kind: "number", group: "routing", advanced: false,
    step: 0.1, decimals: 4, label: "KTC / Kanban threshold (pieces per month)",
    help: "Items below this monthly piece rate are routed to Kanban (warehouse), not the vending machine. The KTC/Kanban decision is based on monthly pieces; physical sizing (spirals, slots) still uses packs." },
  { section: "planning", key: "helix_threshold", kind: "number", group: "routing", advanced: false,
    step: 0.5, decimals: 4, label: "Helix threshold (packs per month)",
    help: "Items above this monthly pack rate go to Helix (spiral dispensing); below go to Carousel (slot stockpiles)." },
  { section: "planning", key: "consumption_months", kind: "number", group: "routing", advanced: false,
    step: 1, decimals: 4, label: "Consumption period in months",
    help: "How many months the consumption figures cover. 12 for annual, 3 for quarter, 1 for monthly." },
  { section: "planning", key: "insert_pack_units", kind: "number", group: "routing", advanced: true,
    step: 1, decimals: 0, label: "Insert default packing unit",
    help: "Inserts are standardised to this many pieces per pack for sizing (KROMI inserts ship in fixed boxes). This value replaces the pack size on every row classified as an insert." },
  { section: "planning", key: "helix_overfill_factor", kind: "number", group: "routing", advanced: true,
    step: 0.01, decimals: 4, label: "Helix single-spiral overfill factor",
    help: "Allow one spiral to hold up to capacity x this factor before adding a second spiral." },
  { section: "planning", key: "min_carousel_allocation", kind: "number", group: "routing", advanced: true,
    step: 1, decimals: 0, label: "Minimum Carousel compartments per KTC item",
    help: "Every KTC item routed to Carousel gets at least this many compartments. Protects against stockouts on refill day." },
  { section: "planning", key: "coverage_days", kind: "number", group: "routing", advanced: false,
    step: 1, decimals: 0,
    label: (c) => c.stdSpecialMapped ? "On-machine stock coverage (standard, in days)"
      : "On-machine stock coverage (days)",
    help: "Days of stock to keep in the cabinet between refills. Affects sizing only, not the KTC/Kanban split. Map a Standard/Special column to split this into two values." },
  { section: "planning", key: "coverage_days_special", kind: "number", group: "routing", advanced: false,
    step: 1, decimals: 0, label: "On-machine stock coverage (special, in days)",
    help: "Days of stock between refills for tools marked Special (from the mapped Standard/Special column).",
    showWhen: (c) => c.stdSpecialMapped },
  { section: "planning", key: "carousel_reserve_factor", kind: "number", group: "routing", advanced: true,
    step: 0.05, decimals: 4, label: "Carousel reserve factor",
    help: "Multiplier on the target packs when sizing Carousel stockpiles. Lower for fast replenishment, higher for a deep buffer." },
  { section: "planning", key: "carousel_fill_ceiling", kind: "number", group: "routing", advanced: true,
    step: 0.05, decimals: 4, label: "Carousel fill ceiling", hiddenInModes: NOT_IN_FIXED,
    help: "Fraction of a Carousel's physical slots the plan may fill before opening the next cabinet. 1.00 packs cabinets fully; lower values leave headroom per cabinet at the cost of more cabinets." },
  { section: "planning", key: "capacity_buffer_pct", kind: "number", group: "routing", advanced: false,
    step: 5, decimals: 4, label: "Capacity buffer (%)", hiddenInModes: NOT_IN_FIXED,
    help: "Extra capacity on top of the calculated need. Applied to spirals, stockpiles and locker items before the final cabinet count." },
  { section: "planning", key: "underuse_threshold_pct", kind: "number", group: "routing", advanced: true,
    step: 5, decimals: 4, label: "Empty-cabinet threshold (%)", hiddenInModes: NOT_IN_FIXED,
    help: "If the last cabinet of a type is below this occupation, the consolidation tries to absorb its items elsewhere.",
    showWhen: (c) => c.settings.planning.enable_rebalancer },
  { section: "planning", key: "enable_rebalancer", kind: "checkbox", group: "routing", advanced: true,
    label: "Consolidate underused cabinets", hiddenInModes: NOT_IN_FIXED,
    help: "When a cabinet ends up below the empty-cabinet threshold, try to move its items into other cabinets with headroom." },
  { section: "planning", key: "special_ktc", kind: "checkbox", group: "routing", advanced: false,
    label: "Set special tools as KTC",
    help: "Force every tool marked Special onto a vending machine regardless of its consumption.",
    showWhen: (c) => c.stdSpecialMapped },

  // ---- Vend-mode controls ----
  { section: "planning", key: "pack_hint_extraction", kind: "checkbox", group: "vend", advanced: true,
    label: "Extract pack sizes from descriptions (qte 50, carton de 60, ...)",
    help: "Only fills pack units that would otherwise default to 1." },
  { section: "planning", key: "bulk_routing", kind: "checkbox", group: "vend", advanced: false,
    label: "Route bulk-consumable families out of vending (abrasives, paint cups, tapes, wipes)",
    help: "These belong on the shelf, not in the machine." },
  { section: "planning", key: "force_screws_kanban", kind: "checkbox", group: "vend", advanced: false,
    label: "Set screws and accessories as Kanban", help: "Regardless of their consumption rate." },

  // ---- Supply points and planning base ----
  { section: "planning", key: "n_supply_points", kind: "number", group: "supply", advanced: false,
    step: 1, decimals: 0, label: "Number of supply points",
    help: "Physical supply locations in the plant. When greater than 1, items are split per supply point per the mode below." },
  { section: "planning", key: "sp_mode", kind: "radio", group: "supply", advanced: false,
    labels: "sp_mode", label: "Supply-point mode" },
  { section: "planning", key: "year_mode", kind: "select", group: "supply", advanced: true,
    labels: "year_mode", label: "Year handling",
    help: "Only applied if a Year column is mapped and contains usable years." },
  { section: "planning", key: "dedup_mode", kind: "select", group: "supply", advanced: true,
    labels: "dedup_mode", label: "Deduplicate planning rows",
    help: "Recommended when the source repeats rows across years, suppliers or transactions." },
  { section: "planning", key: "restock_categories", kind: "multiselect", group: "supply", advanced: true,
    choices: "restock_categories", label: "Restockable categories (rule)",
    hiddenInModes: ["Helix", "NumberingOnly"],
    help: "Categories assumed restockable when the Restocking column gives no answer for a row." },
  { section: "planning", key: "use_description_2", kind: "checkbox", group: "supply", advanced: true,
    label: "Use Description_2 (if mapped)" },

  // ---- Result workbook ----
  { section: "export", key: "include_planogram", kind: "checkbox", group: "workbook", advanced: false,
    label: "Include cabinet planogram sheet",
    help: "Draws each proposed cabinet as a grid with every tool in a numbered compartment." },
  { section: "export", key: "include_technical", kind: "checkbox", group: "workbook", advanced: true,
    label: "Include technical / diagnostic sheets",
    help: "The full audit result, Run_Metadata, distribution sheets and more; useful for review." },
];

/** Settings the form does not show, and why. */
export const NOT_ON_FORM: Record<string, string> = {
  "planning.op_mode": "chosen before the form; only Standard in this version",
  "planning.calc_mode": "applies only with a PPE sheet, which this version does not read",
  "planning.optional_thresholds_active": "per-class thresholds follow in a later version",
  "planning.per_class_thresholds": "per-class thresholds follow in a later version",
  "planning.max_carousels": "Helix + Carousel (capped) mode only",
  "planning.fixed_headroom_pct": "fixed configuration only",
  "planning.fixed_allow_spill": "fixed configuration only",
  "planning.fixed_stock_promotion": "fixed configuration only",
  "planning.fixed_stock_months": "fixed configuration only",
  "planning.fixed_machines": "fixed configuration only",
  "scope.apply_overrides": "no override library in the new app yet",
};

export function fieldLabel(field: SettingField, ctx: FieldContext): string {
  return typeof field.label === "function" ? field.label(ctx) : field.label;
}

export function visibleFields(fields: readonly SettingField[], ctx: FieldContext): SettingField[] {
  return fields.filter((f) => !(f.hiddenInModes ?? []).includes(ctx.opMode)
    && (f.showWhen ? f.showWhen(ctx) : true));
}

export function getValue(settings: SettingsDraft, field: SettingField): unknown {
  return (settings[field.section] as Record<string, unknown>)[field.key];
}

/** New settings with one value changed; the original is left as it was. */
export function setValue(settings: SettingsDraft, field: SettingField, value: unknown): SettingsDraft {
  return { ...settings, [field.section]: { ...settings[field.section], [field.key]: value } };
}

/** The server's limits of a number field: [lowest, highest], null = open. */
export function limitsOf(field: NumberField, defaults: Defaults): [number | null, number | null] {
  return defaults.limits[field.key] ?? [null, null];
}
