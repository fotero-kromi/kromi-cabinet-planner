// The planning settings as the settings screen edits them, and the run request
// built from them. Defaults, limits and choice labels come from the back end
// (engine/planning_defaults.py); labels and help texts are the Streamlit
// page's.
import type { Defaults, ExportIn, PlanningIn, RunRequest, ScopeIn } from "../api/client";
import { type MappingDraft, toMappingIn } from "./mapping";
import {
  type FieldContext, type NumberField, SETTING_FIELDS, fieldLabel, visibleFields,
} from "./settingFields";

export interface SettingsDraft {
  planning: PlanningIn;
  scope: ScopeIn;
  export: ExportIn;
}

/** The draft to start from: the server's defaults. */
export function initialSettings(defaults: Defaults): SettingsDraft {
  return { planning: { ...defaults.planning }, scope: { ...defaults.scope }, export: { ...defaults.export } };
}

/** Number settings that are empty or outside their limits, as messages. */
export function settingsProblems(
  draft: SettingsDraft,
  limits: Defaults["limits"],
  shown: readonly string[],
): string[] {
  const problems: string[] = [];
  for (const key of shown) {
    const field = numberField(key);
    const value = (draft.planning as Record<string, unknown>)[key];
    const label = field ? fieldLabel(field, contextFor(draft)) : key;
    if (typeof value !== "number" || Number.isNaN(value)) {
      problems.push(`${label}: enter a number.`);
      continue;
    }
    const [low, high] = limits[key] ?? [null, null];
    if (low !== null && value < low) problems.push(`${label}: at least ${low}.`);
    if (high !== null && value > high) problems.push(`${label}: at most ${high}.`);
    if (field && field.decimals === 0 && !Number.isInteger(value)) {
      problems.push(`${label}: a whole number.`);
    }
  }
  return problems;
}

/** The number settings the Standard form shows for this mapping, in form order. */
export function shownNumberSettings(draft: SettingsDraft, stdSpecialMapped: boolean): string[] {
  return visibleFields(SETTING_FIELDS, contextFor(draft, stdSpecialMapped))
    .filter((f) => f.kind === "number")
    .map((f) => f.key);
}

function numberField(key: string): NumberField | undefined {
  return SETTING_FIELDS.find((f): f is NumberField => f.kind === "number" && f.key === key);
}

function contextFor(settings: SettingsDraft, stdSpecialMapped = false): FieldContext {
  return { settings, stdSpecialMapped, opMode: settings.planning.op_mode };
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
