// One column choice per planning field (lib/mapping.ts MAPPING_FIELDS).
import { SimpleGrid, Select, Text, Title, Tooltip } from "@mantine/core";

import { type FieldInfo, MAPPING_FIELDS, type MappingDraft, type MappingField } from "../../lib/mapping";

export function MappingGrid({ columns, draft, onChange, fields = MAPPING_FIELDS }: {
  columns: string[];
  draft: MappingDraft;
  onChange: (field: MappingField, column: string | null) => void;
  fields?: readonly FieldInfo[];
}) {
  return (
    <div>
      <Title order={4}>Column mapping</Title>
      <Text size="sm" c="dimmed" mb="xs">
        Code, Description and Consumption are required; the other fields are optional.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
        {fields.map((f) => (
          <Tooltip key={f.field} label={f.help} multiline w={340} openDelay={600} position="top-start">
            <div>
              <Select
                label={f.label}
                data={columns}
                value={draft[f.field]}
                onChange={(value) => onChange(f.field, value)}
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
  );
}
