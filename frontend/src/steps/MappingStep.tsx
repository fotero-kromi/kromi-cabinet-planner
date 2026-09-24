import { Button, Group, Stack } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap, type Workbook } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";
import { DataPreview } from "../components/mapping/DataPreview";
import { MappingGrid } from "../components/mapping/MappingGrid";
import { MappingProblems } from "../components/mapping/MappingProblems";
import { SheetPicker, type Source } from "../components/mapping/SheetPicker";
import {
  type MappingDraft, initialMapping, mappingKey, missingRequired, toMappingIn, validHeaderRow,
} from "../lib/mapping";

export type { Source };

/** A mapping remembers which sheet and header row it was made for. */
export interface StoredMapping {
  key: string;
  draft: MappingDraft;
}

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

  const missing = draft ? missingRequired(draft) : [];
  const canContinue = key !== null && draft !== null && mappingIn !== null && checkIsCurrent && check.data!.ok;

  return (
    <Stack>
      <SheetPicker
        sheets={workbook.sheets}
        source={source}
        onChange={onSourceChange}
        misplaced={sheet.data?.headers_look_misplaced
          ? { headerRow: sheet.data.header_row, suggested: sheet.data.suggested_header_row }
          : null}
      />
      {sheet.isError && <ErrorAlert title="The sheet cannot be read" error={sheet.error} />}

      {sheet.data && draft && (
        <>
          <DataPreview columns={columns} rows={sheet.data.preview} rowCount={sheet.data.row_count} />
          <MappingGrid columns={columns} draft={draft} onChange={setField} />
          {check.isError && <ErrorAlert title="The mapping cannot be checked" error={check.error} />}
          <MappingProblems missingRequired={missing} check={checkIsCurrent ? check.data! : null} />
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
