// The planning settings as the settings screen edits them, and the run request
// built from them. Defaults, limits and choice labels come from the back end
// (engine/planning_defaults.py); labels and help texts are the Streamlit
// page's.
import type { Defaults, ExportIn, PlanningIn, RunRequest, ScopeIn } from "../api/client";
import { type MappingDraft, toMappingIn } from "./mapping";

export interface SettingsDraft {
  planning: PlanningIn;
  scope: ScopeIn;
  export: ExportIn;
}

type NumberKey = {
  [K in keyof PlanningIn]-?: NonNullable<PlanningIn[K]> extends number ? K : never;
}[keyof PlanningIn];

export interface NumberSetting {
  key: NumberKey;
  label: string;
  help: string;
  step: number;
  /** digits after the decimal point; 0 = whole numbers */
  decimals: number;
}

export const NUMBER_SETTINGS: Record<string, NumberSetting> = {
  ktc_threshold: { key: "ktc_threshold", label: "KTC / Kanban threshold (pieces per month)", step: 0.1, decimals: 4,
    help: "Items below this monthly piece rate are routed to Kanban (warehouse), not the vending machine. The KTC/Kanban decision is based on monthly pieces; physical sizing (spirals, slots) still uses packs." },
  insert_pack_units: { key: "insert_pack_units", label: "Insert default packing unit", step: 1, decimals: 0,
    help: "Inserts are standardised to this many pieces per pack for sizing (KROMI inserts ship in fixed boxes). This value replaces the pack size on every row classified as an insert." },
  helix_threshold: { key: "helix_threshold", label: "Helix threshold (packs per month)", step: 0.5, decimals: 4,
    help: "Items above this monthly pack rate go to Helix (spiral dispensing); below go to Carousel (slot stockpiles)." },
  consumption_months: { key: "consumption_months", label: "Consumption period in months", step: 1, decimals: 4,
    help: "How many months the consumption figures cover. 12 for annual, 3 for quarter, 1 for monthly." },
  helix_overfill_factor: { key: "helix_overfill_factor", label: "Helix single-spiral overfill factor", step: 0.01, decimals: 4,
    help: "Allow one spiral to hold up to capacity x this factor before adding a second spiral." },
  min_carousel_allocation: { key: "min_carousel_allocation", label: "Minimum Carousel compartments per KTC item", step: 1, decimals: 0,
    help: "Every KTC item routed to Carousel gets at least this many compartments. Protects against stockouts on refill day." },
  coverage_days: { key: "coverage_days", label: "On-machine stock coverage (days)", step: 1, decimals: 0,
    help: "Days of stock to keep in the cabinet between refills. Affects sizing only, not the KTC/Kanban split. Map a Standard/Special column to split this into two values." },
  coverage_days_special: { key: "coverage_days_special", label: "On-machine stock coverage (special, in days)", step: 1, decimals: 0,
    help: "Days of stock between refills for tools marked Special (from the mapped Standard/Special column)." },
  carousel_reserve_factor: { key: "carousel_reserve_factor", label: "Carousel reserve factor", step: 0.05, decimals: 4,
    help: "Multiplier on the target packs when sizing Carousel stockpiles. Lower for fast replenishment, higher for a deep buffer." },
  carousel_fill_ceiling: { key: "carousel_fill_ceiling", label: "Carousel fill ceiling", step: 0.05, decimals: 4,
    help: "Fraction of a Carousel's physical slots the plan may fill before opening the next cabinet. 1.00 packs cabinets fully; lower values leave headroom per cabinet at the cost of more cabinets." },
  underuse_threshold_pct: { key: "underuse_threshold_pct", label: "Empty-cabinet threshold (%)", step: 5, decimals: 4,
    help: "If the last cabinet of a type is below this occupation, the consolidation tries to absorb its items elsewhere." },
  capacity_buffer_pct: { key: "capacity_buffer_pct", label: "Capacity buffer (%)", step: 5, decimals: 4,
    help: "Extra capacity on top of the calculated need. Applied to spirals, stockpiles and locker items before the final cabinet count." },
  n_supply_points: { key: "n_supply_points", label: "Number of supply points", step: 1, decimals: 0,
    help: "Physical supply locations in the plant. When greater than 1, items are split per supply point per the mode below." },
};

/** The draft to start from: the server's defaults. */
export function initialSettings(defaults: Defaults): SettingsDraft {
  return { planning: { ...defaults.planning }, scope: { ...defaults.scope }, export: { ...defaults.export } };
}

export const KTC_ID_PATTERN = /^\d{3}$/;

/** Number settings that are empty or outside their limits, as messages. */
export function settingsProblems(
  draft: SettingsDraft,
  limits: Defaults["limits"],
  shown: readonly NumberKey[],
): string[] {
  const problems: string[] = [];
  for (const key of shown) {
    const setting = NUMBER_SETTINGS[key];
    const value = draft.planning[key];
    const label = setting?.label ?? key;
    if (typeof value !== "number" || Number.isNaN(value)) {
      problems.push(`${label}: enter a number.`);
      continue;
    }
    const [low, high] = limits[key] ?? [null, null];
    if (low !== null && value < low) problems.push(`${label}: at least ${low}.`);
    if (high !== null && value > high) problems.push(`${label}: at most ${high}.`);
    if (setting && setting.decimals === 0 && !Number.isInteger(value)) {
      problems.push(`${label}: a whole number.`);
    }
  }
  return problems;
}

/** The number settings the screen shows for this mapping. */
export function shownNumberSettings(draft: SettingsDraft, stdSpecialMapped: boolean): NumberKey[] {
  const keys: NumberKey[] = [
    "ktc_threshold", "insert_pack_units", "helix_threshold", "consumption_months",
    "helix_overfill_factor", "min_carousel_allocation", "coverage_days",
  ];
  if (stdSpecialMapped) keys.push("coverage_days_special");
  keys.push("carousel_reserve_factor", "carousel_fill_ceiling");
  if (draft.planning.enable_rebalancer ?? true) keys.push("underuse_threshold_pct");
  keys.push("capacity_buffer_pct", "n_supply_points");
  return keys;
}

/** Everything one run needs besides the workbook, or null while the mapping
 *  lacks a required field. */
export function buildRunRequest(
  sheet: string,
  headerRow: number,
  mapping: MappingDraft,
  settings: SettingsDraft,
): RunRequest | null {
  const mappingIn = toMappingIn(mapping);
  if (mappingIn === null) return null;
  return {
    sheet,
    header_row: headerRow,
    mapping: mappingIn,
    planning: settings.planning,
    scope: { ...settings.scope, ktc_id: (settings.scope.ktc_id ?? "").trim() },
    export: settings.export,
    program_to_sp: {},
  };
}
