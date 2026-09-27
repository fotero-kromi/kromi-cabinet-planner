// Any list of setting descriptions as a form: grouped, in the given order,
// showing only the fields that apply. Inputs sit in a grid, checkboxes below
// them, then any warnings of the group.
import { Alert, Fieldset, SimpleGrid, Stack } from "@mantine/core";

import type { Defaults } from "../../api/client";
import {
  type FieldContext, SETTING_GROUPS, type SettingField, getValue, setValue, visibleFields,
} from "../../lib/settingFields";
import type { SettingsDraft } from "../../lib/settings";
import { SettingInput } from "./SettingInput";

export function SettingsForm({ fields, defaults, settings, stdSpecialMapped, opMode, onChange }: {
  fields: readonly SettingField[];
  defaults: Defaults;
  settings: SettingsDraft;
  stdSpecialMapped: boolean;
  opMode: string;
  onChange: (settings: SettingsDraft) => void;
}) {
  const ctx: FieldContext = { settings, stdSpecialMapped, opMode };
  const shown = visibleFields(fields, ctx);
  const input = (f: SettingField) => (
    <SettingInput key={`${f.section}.${f.key}`} field={f} value={getValue(settings, f)} defaults={defaults}
                  ctx={ctx} onChange={(v) => onChange(setValue(settings, f, v))} />
  );

  return (
    <Stack>
      {SETTING_GROUPS.map((group) => {
        const inGroup = shown.filter((f) => f.group === group.id);
        if (inGroup.length === 0) return null;
        const boxes = inGroup.filter((f) => f.kind === "checkbox");
        const others = inGroup.filter((f) => f.kind !== "checkbox");
        const warnings = inGroup.flatMap((f) =>
          f.kind === "text" && f.warning ? [f.warning(String(getValue(settings, f) ?? ""))] : [])
          .filter((w): w is string => w !== null);
        return (
          <Fieldset key={group.id} legend={group.title}>
            {others.length > 0 && <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>{others.map(input)}</SimpleGrid>}
            {boxes.length > 0 && <Stack gap="xs" mt={others.length > 0 ? "md" : 0}>{boxes.map(input)}</Stack>}
            {warnings.map((w) => <Alert key={w} color="yellow" mt="sm">{w}</Alert>)}
          </Fieldset>
        );
      })}
    </Stack>
  );
}
