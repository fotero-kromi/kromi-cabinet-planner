// Every planned article with its routing and sizing; sort and filter per column.
import type { ColDef } from "ag-grid-community";

import type { Tool } from "../../api/client";
import { DataGrid } from "../DataGrid";

const number = (digits: number) => (p: { value: unknown }) =>
  typeof p.value === "number" ? p.value.toLocaleString("en", { maximumFractionDigits: digits }) : "";

const COLUMNS: ColDef<Tool>[] = [
  { field: "line_no", headerName: "Line", width: 80 },
  { field: "code", headerName: "Code" },
  { field: "description", headerName: "Description", flex: 1, minWidth: 220 },
  { field: "category", headerName: "Category" },
  { field: "size", headerName: "Size", width: 90 },
  { field: "system_category", headerName: "KTC / Kanban", width: 130 },
  { field: "cabinet_type", headerName: "Cabinet type", width: 130 },
  { field: "supply_point", headerName: "SP", width: 80 },
  { field: "pack_units", headerName: "Pack units", width: 110, valueFormatter: number(2) },
  { field: "monthly_pcs", headerName: "Pieces / month", width: 140, valueFormatter: number(2) },
  { field: "monthly_packs", headerName: "Packs / month", width: 140, valueFormatter: number(2) },
  { field: "spirals", headerName: "Spirals", width: 100 },
  { field: "compartments", headerName: "Compartments", width: 140 },
];

export function ArticleTable({ tools, height = 520 }: { tools: Tool[]; height?: number }) {
  return <DataGrid<Tool> label="Articles" rows={tools} columns={COLUMNS} height={height} />;
}
