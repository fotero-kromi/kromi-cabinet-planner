import { Alert, Button, Group, List, NumberInput, Select, SimpleGrid, Stack, Text, Title, Tooltip } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";

import { api, unwrap, type Workbook } from "../api/client";
import { DataGrid } from "../components/DataGrid";
import { ErrorAlert } from "../components/ErrorAlert";
import {
  MAPPING_FIELDS, type MappingDraft, initialMapping, mappingKey, missingRequired, toMappingIn,
  validHeaderRow,
} from "../lib/mapping";

export interface Source {
  sheet: string | null;
  /** as typed; a whole number from 1 to 50 is valid */
  headerRow: number | string;
}

/** A mapping remembers which sheet and header row it was made for. */
export interface StoredMapping {
  key: string;
  draft: MappingDraft;
}

type Row = Record<string, unknown>;

export function MappingStep({ workbook, source, onSourceChange, mapping, onMappingChange, onBack, onNext }: {
  workbook: Workbook;
  source: Source;
  onSourceChange: (source: Source) => void;
  mapping: StoredMapping | null;
  onMappingChange: (mapping: StoredMapping) => void;
  onBack: () => void;
  onNext: (mapping: StoredMapping, headerRow: number) => void;
}) {
  const headerRow = validHeaderRow(source.headerRow);
  const sheetName = source.sheet;
  const sheet = useQuery({
    queryKey: ["sheet", workbook.id, sheetName, headerRow],
    queryFn: () => unwrap(api.GET("/api/v1/workbooks/{workbook_id}/sheets/{sheet}", {
      params: { path: { workbook_id: workbook.id, sheet: sheetName! }, query: { header_row: headerRow! } },
    })),
    enabled: sheetName !== null && headerRow !== null,
  });

  const key = sheetName !== null && headerRow !== null ? mappingKey(workbook.id, sheetName, headerRow) : null;
  const columns = sheet.data?.columns ?? [];
  // The user's edits for this sheet and header row, else the suggestion.
  const draft: MappingDraft | null = key === null || !sheet.data
    ? null
    : mapping?.key === key
      ? mapping.draft
      : initialMapping(sheet.data.suggested_mapping, sheet.data.columns);
  const mappingIn = draft ? toMappingIn(draft) : null;

  const check = useQuery({
    queryKey: ["mapping-check", workbook.id, sheetName, headerRow, mappingIn],
    queryFn: () => unwrap(api.POST("/api/v1/workbooks/{workbook_id}/mapping/check", {
      params: { path: { workbook_id: workbook.id } },
      body: { sheet: sheetName!, header_row: headerRow!, mapping: mappingIn! },
    })),
    enabled: mappingIn !== null,
    placeholderData: keepPreviousData,
  });
  const checkIsCurrent = check.data !== undefined && !check.isPlaceholderData;

  const setField = (field: keyof MappingDraft, column: string | null) => {
    if (key !== null && draft) onMappingChange({ key, draft: { ...draft, [field]: column } });
  };

  const previewColumns: ColDef<Row>[] = columns.map((column) => ({
    colId: column,
    headerName: column,
    valueGetter: (p) => p.data?.[column],
  }));
  const missing = draft ? missingRequired(draft) : [];
  const canContinue = key !== null && draft !== null && mappingIn !== null && checkIsCurrent && check.data!.ok;

  return (
    <Stack>
      <Group align="flex-end">
        <Select
          label="Tools sheet"
          placeholder="Choose the sheet with the tool list"
          data={workbook.sheets}
          value={sheetName}
          onChange={(value) => onSourceChange({ ...source, sheet: value })}
          allowDeselect={false}
          w={320}
        />
        <NumberInput
          label="Header row in the sheet"
          description="Row that carries the column names"
          value={source.headerRow}
          onChange={(value) => onSourceChange({ ...source, headerRow: value })}
          min={1}
          max={50}
          allowDecimal={false}
          allowNegative={false}
          w={220}
          error={headerRow === null ? "A whole number from 1 to 50." : undefined}
        />
      </Group>

      {sheet.isError && <ErrorAlert title="The sheet cannot be read" error={sheet.error} />}
      {sheet.data?.headers_look_misplaced && (
        <Alert color="yellow" title="Check the header row">
          <Group justify="space-between">
            <Text size="sm">
              The column names do not look like they are on row {sheet.data.header_row}. Row{" "}
              {sheet.data.suggested_header_row} looks like the header row.
            </Text>
            <Button size="xs" variant="light"
                    onClick={() => onSourceChange({ ...source, headerRow: sheet.data.suggested_header_row })}>
              Use row {sheet.data.suggested_header_row}
            </Button>
          </Group>
        </Alert>
      )}

      {sheet.data && draft && (
        <>
          <div>
            <Title order={4}>Data preview</Title>
            <Text size="sm" c="dimmed" mb="xs">
              First {sheet.data.preview.length} of {sheet.data.row_count} rows
            </Text>
            <DataGrid<Row> label="Data preview" rows={sheet.data.preview} columns={previewColumns} height={260} />
          </div>

          <div>
            <Title order={4}>Column mapping</Title>
            <Text size="sm" c="dimmed" mb="xs">
              Code, Description and Consumption are required; the other fields are optional.
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
              {MAPPING_FIELDS.map((f) => (
                <Tooltip key={f.field} label={f.help} multiline w={340} openDelay={600} position="top-start">
                  <div>
                    <Select
                      label={f.label}
                      data={columns}
                      value={draft[f.field]}
                      onChange={(value) => setField(f.field, value)}
                      required={f.required}
                      clearable={!f.required}
                      clearButtonProps={{ "aria-label": `Clear ${f.label}`, "aria-hidden": false }}
                      placeholder={f.required ? "Choose a column" : "Not used"}
                      searchable
                      allowDeselect={!f.required}
                    />
                  </div>
                </Tooltip>
              ))}
            </SimpleGrid>
          </div>

          {missing.length > 0 && (
            <Alert color="yellow">Choose a column for: {missing.join(", ")}</Alert>
          )}
          {check.isError && <ErrorAlert title="The mapping cannot be checked" error={check.error} />}
          {checkIsCurrent && !check.data!.ok && (
            <Alert color="red" title="Column mapping conflict">
              <List size="sm">
                {Object.entries(check.data!.conflicts).map(([column, fields]) => (
                  <List.Item key={column}>
                    '{column}' is mapped to: {fields.join(", ")}
                  </List.Item>
                ))}
                {check.data!.missing_columns.map((column) => (
                  <List.Item key={column}>The sheet has no column '{column}'.</List.Item>
                ))}
              </List>
              <Text size="sm" mt="xs">Pick one field per column and clear the others.</Text>
            </Alert>
          )}
        </>
      )}

      <Group justify="space-between">
        <Button variant="default" onClick={onBack}>Back</Button>
        <Button disabled={!canContinue} onClick={() => onNext({ key: key!, draft: draft! }, headerRow!)}>
          Next
        </Button>
      </Group>
    </Stack>
  );
}
