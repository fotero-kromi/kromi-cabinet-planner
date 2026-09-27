// AG Grid Community with the app's look; read-only in this version.
import { AllCommunityModule, ModuleRegistry, type ColDef, themeQuartz } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeQuartz.withParams({
  accentColor: "#006c52",
  headerBackgroundColor: "#eaf4ec",
  fontFamily: "Arial, Helvetica, sans-serif",
  fontSize: 13,
});

interface Props<T> {
  rows: T[];
  columns: ColDef<T>[];
  /** pixels; the grid scrolls inside */
  height: number;
  label: string;
}

export function DataGrid<T>({ rows, columns, height, label }: Props<T>) {
  return (
    <div style={{ height }} role="region" aria-label={label}>
      <AgGridReact<T>
        theme={gridTheme}
        rowData={rows}
        columnDefs={columns}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        // Keep the rows in the page in tests (jsdom has no layout) and in
        // small tables; large ones are virtualised by AG Grid.
        suppressColumnVirtualisation
      />
    </div>
  );
}
