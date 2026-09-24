// The column mapping: which source column feeds which planning field. Labels
// and help texts are the Streamlit page's, so both apps read the same.
import type { MappingIn } from "../api/client";

export type MappingField = keyof MappingIn;
/** A mapping being edited: `null` = not mapped (yet). */
export type MappingDraft = Record<MappingField, string | null>;

export interface FieldInfo {
  field: MappingField;
  label: string;
  help: string;
  required: boolean;
}

export const MAPPING_FIELDS: readonly FieldInfo[] = [
  { field: "code", label: "Code", required: true,
    help: "Unique identifier for each article (SAP number, internal ID, SKU). Used to deduplicate rows and to look up per-item overrides." },
  { field: "description", label: "Description", required: true,
    help: "The primary free-text description of each article. The classifier reads it to assign ProductCategory, ToolClass and SizeCategory." },
  { field: "consumption", label: "Consumption pcs", required: true,
    help: "Annual or per-period consumption in pieces. Combined with PackUnits and the consumption period to compute monthly packs, which drive the KTC/Kanban and Helix/Carousel splits." },
  { field: "category", label: "ProductCategory", required: false,
    help: "A pre-existing category column (drills, mills, taps...) if the file already carries one. When mapped, the classifier uses it as a hint instead of re-classifying from the description." },
  { field: "description_2", label: "Description_2", required: false,
    help: "A secondary description column, if the catalog splits long descriptions across two fields. When mapped, it is joined to the primary description before classification." },
  { field: "supplier_code", label: "SupplierCode", required: false,
    help: "Supplier-side article code. When mapped, deduplication can key on Code + SupplierCode instead of Code alone, so the same internal code from two suppliers stays as two rows." },
  { field: "pack_units", label: "PackUnits", required: false,
    help: "Pieces per pack / VPE. When unmapped, the planner assumes PackUnits = 1 and may overstate the cabinet count." },
  { field: "size", label: "SizeCategory", required: false,
    help: "A pre-existing size label (S/M/L/XL/XXL). When mapped, the planner uses it directly and skips the description-based size heuristic for that row." },
  { field: "year", label: "Year", required: false,
    help: "Year of the consumption row. Lets the planner keep only the latest year (see Planning base). Leave unmapped to use all rows." },
  { field: "program", label: "Program / Area", required: false,
    help: "The programme, project or workshop area of each row. Used for per-programme breakdowns; does not affect the cabinet count." },
  { field: "restocking", label: "Restocking yes/no", required: false,
    help: "A yes/no column marking items the customer restocks. A restockable vending item reserves one buffer compartment. Kanban items are unaffected." },
  { field: "site", label: "Site", required: false,
    help: "Physical site or plant code. Used to scope per-supply-point breakdowns in Partition mode." },
  { field: "std_special", label: "Standard / Special", required: false,
    help: "A column marking each tool as Standard or Special. When mapped, the stock coverage splits into a Standard and a Special value." },
  { field: "dimensions", label: "Package dimensions", required: false,
    help: "Package width x depth x height or diameter x length. When mapped, an advisory fit-check against the compartments runs; routing is not changed." },
  { field: "regrind", label: "Regrind YES/NO", required: false,
    help: "Tools that can be reground. A reground tool kept in a Helix gets at least two spirals (new and reground)." },
  { field: "system_type", label: "System type available", required: false,
    help: "A customer-specified storage system per tool: 'KTC', 'KTC or Kanban' or 'Locker'. When mapped, the customer's choice overrides the planner's KTC/Kanban/cabinet decision." },
  { field: "stock", label: "Current stock pcs", required: false,
    help: "The customer's current stock in pieces. When mapped, the workbook adds takeover sheets; the plan itself does not change." },
];

export const REQUIRED_FIELDS: readonly MappingField[] = MAPPING_FIELDS.filter((f) => f.required).map(
  (f) => f.field,
);

/** The mapping to start from: the server's suggestion, kept only where the
 *  suggested column exists in the sheet. */
export function initialMapping(
  suggested: Record<string, string | null | undefined>,
  columns: readonly string[],
): MappingDraft {
  const known = new Set(columns);
  const draft = {} as MappingDraft;
  for (const { field } of MAPPING_FIELDS) {
    const column = suggested[field];
    draft[field] = column && known.has(column) ? column : null;
  }
  return draft;
}

/** Required fields still without a column, as labels. */
export function missingRequired(draft: MappingDraft): string[] {
  return MAPPING_FIELDS.filter((f) => f.required && !draft[f.field]).map((f) => f.label);
}

/** The mapping the API accepts, or null while a required field is empty. */
export function toMappingIn(draft: MappingDraft): MappingIn | null {
  if (missingRequired(draft).length > 0) return null;
  return { ...draft } as MappingIn;
}

/** The header row as typed, if it is a whole number from 1 to 50. */
export function validHeaderRow(value: number | string): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return value !== "" && Number.isInteger(n) && n >= 1 && n <= 50 ? n : null;
}

export function mappingKey(workbookId: number, sheet: string, headerRow: number): string {
  return JSON.stringify([workbookId, sheet, headerRow]);
}
