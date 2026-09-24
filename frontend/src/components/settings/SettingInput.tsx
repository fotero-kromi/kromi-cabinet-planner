// One setting as its input, chosen by the description's kind.
import { Checkbox, MultiSelect, NumberInput, Radio, Select, Stack, TextInput } from "@mantine/core";

import type { Defaults } from "../../api/client";
import { type FieldContext, type SettingField, fieldLabel, limitsOf } from "../../lib/settingFields";

const options = (labels: Record<string, string> | undefined) =>
  Object.entries(labels ?? {}).map(([value, label]) => ({ value, label }));

export function SettingInput({ field, value, onChange, defaults, ctx }: {
  field: SettingField;
  value: unknown;
  onChange: (value: unknown) => void;
  defaults: Defaults;
  ctx: FieldContext;
}) {
  const label = fieldLabel(field, ctx);
  switch (field.kind) {
    case "number": {
      const [low, high] = limitsOf(field, defaults);
      const n = value as number;
      return (
        <NumberInput
          label={label}
          description={field.help}
          value={Number.isNaN(n) ? "" : n}
          onChange={(v) => onChange(typeof v === "number" ? v : Number.NaN)}
          min={low ?? undefined}
          max={high ?? undefined}
          step={field.step}
          decimalScale={field.decimals}
          allowDecimal={field.decimals > 0}
          clampBehavior="none"
        />
      );
    }
    case "checkbox":
      return (
        <Checkbox
          label={label}
          description={field.help}
          checked={value as boolean}
          onChange={(e) => onChange(e.currentTarget.checked)}
        />
      );
    case "select":
      return (
        <Select
          label={label}
          description={field.help}
          data={options(defaults.labels[field.labels])}
          value={value as string}
          onChange={(v) => v !== null && onChange(v)}
          allowDeselect={false}
        />
      );
    case "radio":
      return (
        <Radio.Group label={label} description={field.help} value={value as string} onChange={onChange}>
          <Stack gap={4} mt={4}>
            {options(defaults.labels[field.labels]).map((o) => (
              <Radio key={o.value} value={o.value} label={o.label} />
            ))}
          </Stack>
        </Radio.Group>
      );
    case "multiselect":
      return (
        <MultiSelect
          label={label}
          description={field.help}
          data={defaults.choices[field.choices] ?? []}
          value={value as string[]}
          onChange={onChange}
          searchable
          clearable
        />
      );
    case "text":
      return (
        <TextInput
          label={label}
          description={field.help}
          value={value as string}
          onChange={(e) => onChange(e.currentTarget.value)}
          maxLength={field.maxLength}
        />
      );
  }
}
