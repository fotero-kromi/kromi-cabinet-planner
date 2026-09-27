// The first rows of the chosen sheet, as the server read them.
import { Text, Title } from "@mantine/core";
import type { ColDef } from "ag-grid-community";

import { DataGrid } from "../DataGrid";

type Row = Record<string, unknown>;

export function DataPreview({ columns, rows, rowCount }: {
  columns: string[];
  rows: Row[];
  rowCount: number;
}) {
  // valueGetter, not field: a column name with a dot must not be read as a path.
  const defs: ColDef<Row>[] = columns.map((column) => ({
    colId: column,
    headerName: column,
    valueGetter: (p) => p.data?.[column],
  }));
  return (
    <div>
      <Title order={4}>Data preview</Title>
      <Text size="sm" c="dimmed" mb="xs">First {rows.length} of {rowCount} rows</Text>
      <DataGrid<Row> label="Data preview" rows={rows} columns={defs} height={260} />
    </div>
  );
}
