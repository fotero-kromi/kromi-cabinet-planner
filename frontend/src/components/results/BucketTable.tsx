// Cabinets and articles per supply point (the planner's buckets).
import type { ColDef } from "ag-grid-community";

import type { Bucket } from "../../api/client";
import { DataGrid } from "../DataGrid";

const COLUMNS: ColDef<Bucket>[] = [
  { field: "label", headerName: "Scope", flex: 1 },
  { field: "ktc_count", headerName: "KTC articles" },
  { field: "kanban_count", headerName: "Kanban articles" },
  { field: "helix_cabinets", headerName: "Helix" },
  { field: "carousel_cabinets", headerName: "Carousel" },
  { field: "locker_a_cabinets", headerName: "Locker A" },
  { field: "locker_b_cabinets", headerName: "Locker B" },
  { field: "locker_c_cabinets", headerName: "Locker C" },
  { field: "total_cabinets", headerName: "Total cabinets" },
];

export function BucketTable({ buckets }: { buckets: Bucket[] }) {
  return <DataGrid<Bucket> label="Per supply point" rows={buckets} columns={COLUMNS}
                           height={60 + 42 * buckets.length} />;
}
