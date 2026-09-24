// Which sheet holds the tool list and on which row its column names are.
import { Alert, Button, Group, NumberInput, Select, Stack, Text } from "@mantine/core";

import { validHeaderRow } from "../../lib/mapping";

export interface Source {
  sheet: string | null;
  /** as typed; a whole number from 1 to 50 is valid */
  headerRow: number | string;
}

export function SheetPicker({ sheets, source, onChange, misplaced }: {
  sheets: string[];
  source: Source;
  onChange: (source: Source) => void;
  /** the server's hint when the column names look like they are on another row */
  misplaced: { headerRow: number; suggested: number } | null;
}) {
  return (
    <Stack>
      <Group align="flex-end">
        <Select
          label="Tools sheet"
          placeholder="Choose the sheet with the tool list"
          data={sheets}
          value={source.sheet}
          onChange={(value) => onChange({ ...source, sheet: value })}
          allowDeselect={false}
          w={320}
        />
        <NumberInput
          label="Header row in the sheet"
          description="Row that carries the column names"
          value={source.headerRow}
          onChange={(value) => onChange({ ...source, headerRow: value })}
          min={1}
          max={50}
          allowDecimal={false}
          allowNegative={false}
          w={220}
          error={validHeaderRow(source.headerRow) === null ? "A whole number from 1 to 50." : undefined}
        />
      </Group>
      {misplaced && (
        <Alert color="yellow" title="Check the header row">
          <Group justify="space-between">
            <Text size="sm">
              The column names do not look like they are on row {misplaced.headerRow}. Row{" "}
              {misplaced.suggested} looks like the header row.
            </Text>
            <Button size="xs" variant="light" onClick={() => onChange({ ...source, headerRow: misplaced.suggested })}>
              Use row {misplaced.suggested}
            </Button>
          </Group>
        </Alert>
      )}
    </Stack>
  );
}
