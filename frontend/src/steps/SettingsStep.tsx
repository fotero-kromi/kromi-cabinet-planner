import {
  Alert, Button, Checkbox, Fieldset, Group, List, MultiSelect, NumberInput, Radio, Select,
  SimpleGrid, Stack, Text, TextInput,
} from "@mantine/core";
import { useMutation } from "@tanstack/react-query";

import { api, unwrap, type Defaults, type ExportIn, type PlanningIn, type Run, type ScopeIn } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";
import type { MappingDraft } from "../lib/mapping";
import {
  KTC_ID_PATTERN, NUMBER_SETTINGS, type SettingsDraft, buildRunRequest, settingsProblems, shownNumberSettings,
} from "../lib/settings";

const options = (labels: Record<string, string> | undefined) =>
  Object.entries(labels ?? {}).map(([value, label]) => ({ value, label }));

export function SettingsStep({ workbookId, sheet, headerRow, mapping, defaults, settings, onChange, onBack, onStarted }: {
  workbookId: number;
  sheet: string;
  headerRow: number;
  mapping: MappingDraft;
  defaults: Defaults;
  settings: SettingsDraft;
  onChange: (settings: SettingsDraft) => void;
  onBack: () => void;
  onStarted: (run: Run) => void;
}) {
  const { planning, scope } = settings;
  const setPlanning = (patch: Partial<PlanningIn>) => onChange({ ...settings, planning: { ...planning, ...patch } });
  const setScope = (patch: Partial<ScopeIn>) => onChange({ ...settings, scope: { ...scope, ...patch } });
  const setExport = (patch: Partial<ExportIn>) => onChange({ ...settings, export: { ...settings.export, ...patch } });

  const stdSpecialMapped = mapping.std_special !== null;
  const shown = shownNumberSettings(settings, stdSpecialMapped);
  const problems = settingsProblems(settings, defaults.limits, shown);
  const request = buildRunRequest(sheet, headerRow, mapping, settings);

  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/runs", { body: { workbook_id: workbookId, settings: request! } })),
    onSuccess: onStarted,
  });

  const numberField = (name: keyof typeof NUMBER_SETTINGS, labelOverride?: string) => {
    const s = NUMBER_SETTINGS[name]!;
    if (!shown.includes(s.key)) return null;
    const [low, high] = defaults.limits[s.key] ?? [null, null];
    const value = planning[s.key];
    return (
      <NumberInput
        key={s.key}
        label={labelOverride ?? s.label}
        description={s.help}
        value={Number.isNaN(value) ? "" : value}
        onChange={(v) => setPlanning({ [s.key]: typeof v === "number" ? v : Number.NaN })}
        min={low ?? undefined}
        max={high ?? undefined}
        step={s.step}
        decimalScale={s.decimals}
        allowDecimal={s.decimals > 0}
        clampBehavior="none"
      />
    );
  };

  const ktcId = (scope.ktc_id ?? "").trim();

  return (
    <Stack>
      <Fieldset legend="Run setup">
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput
            label="KTC-ID"
            description="The 3-digit customer/installation ID that starts every generated KROMI article number."
            value={scope.ktc_id}
            onChange={(e) => setScope({ ktc_id: e.currentTarget.value })}
            maxLength={3}
          />
          <TextInput
            label="Customer"
            description="Recorded with the run and in the Run_Metadata sheet."
            value={scope.customer}
            onChange={(e) => setScope({ customer: e.currentTarget.value })}
          />
          <TextInput
            label="Site"
            description="Plant or site; recorded like the customer."
            value={scope.site}
            onChange={(e) => setScope({ site: e.currentTarget.value })}
          />
        </SimpleGrid>
        {!KTC_ID_PATTERN.test(ktcId) && (
          <Alert color="yellow" mt="sm">
            The KTC-ID must be exactly 3 digits. Until it is, no KROMI article numbers are generated and
            the Article setup sheet is left out of the export.
          </Alert>
        )}
        <Text size="sm" c="dimmed" mt="sm">
          Operation mode: {defaults.labels.op_mode?.[planning.op_mode] ?? "Standard"}. The other modes follow
          in a later version.
        </Text>
      </Fieldset>

      <Fieldset legend="Routing and sizing">
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {numberField("ktc_threshold")}
          {numberField("helix_threshold")}
          {numberField("consumption_months")}
          {numberField("insert_pack_units")}
          {numberField("helix_overfill_factor")}
          {numberField("min_carousel_allocation")}
          {numberField("coverage_days", stdSpecialMapped ? "On-machine stock coverage (standard, in days)" : undefined)}
          {numberField("coverage_days_special")}
          {numberField("carousel_reserve_factor")}
          {numberField("carousel_fill_ceiling")}
          {numberField("capacity_buffer_pct")}
          {numberField("underuse_threshold_pct")}
        </SimpleGrid>
        <Stack gap="xs" mt="md">
          <Checkbox
            label="Consolidate underused cabinets"
            description="When a cabinet ends up below the empty-cabinet threshold, try to move its items into other cabinets with headroom."
            checked={planning.enable_rebalancer}
            onChange={(e) => setPlanning({ enable_rebalancer: e.currentTarget.checked })}
          />
          {stdSpecialMapped && (
            <Checkbox
              label="Set special tools as KTC"
              description="Force every tool marked Special onto a vending machine regardless of its consumption."
              checked={planning.special_ktc}
              onChange={(e) => setPlanning({ special_ktc: e.currentTarget.checked })}
            />
          )}
        </Stack>
      </Fieldset>

      <Fieldset legend="Vend-mode controls">
        <Stack gap="xs">
          <Checkbox
            label="Extract pack sizes from descriptions (qte 50, carton de 60, ...)"
            description="Only fills pack units that would otherwise default to 1."
            checked={planning.pack_hint_extraction}
            onChange={(e) => setPlanning({ pack_hint_extraction: e.currentTarget.checked })}
          />
          <Checkbox
            label="Route bulk-consumable families out of vending (abrasives, paint cups, tapes, wipes)"
            description="These belong on the shelf, not in the machine."
            checked={planning.bulk_routing}
            onChange={(e) => setPlanning({ bulk_routing: e.currentTarget.checked })}
          />
          <Checkbox
            label="Set screws and accessories as Kanban"
            description="Regardless of their consumption rate."
            checked={planning.force_screws_kanban}
            onChange={(e) => setPlanning({ force_screws_kanban: e.currentTarget.checked })}
          />
        </Stack>
      </Fieldset>

      <Fieldset legend="Supply points and planning base">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {numberField("n_supply_points")}
          <Radio.Group
            label="Supply-point mode"
            value={planning.sp_mode}
            onChange={(v) => setPlanning({ sp_mode: v })}
          >
            <Stack gap={4} mt={4}>
              {options(defaults.labels.sp_mode).map((o) => (
                <Radio key={o.value} value={o.value} label={o.label} />
              ))}
            </Stack>
          </Radio.Group>
          <Select
            label="Year handling"
            description="Only applied if a Year column is mapped and contains usable years."
            data={options(defaults.labels.year_mode)}
            value={planning.year_mode}
            onChange={(v) => v && setPlanning({ year_mode: v })}
            allowDeselect={false}
          />
          <Select
            label="Deduplicate planning rows"
            description="Recommended when the source repeats rows across years, suppliers or transactions."
            data={options(defaults.labels.dedup_mode)}
            value={planning.dedup_mode}
            onChange={(v) => v && setPlanning({ dedup_mode: v })}
            allowDeselect={false}
          />
          <MultiSelect
            label="Restockable categories (rule)"
            description="Categories assumed restockable when the Restocking column gives no answer for a row."
            data={defaults.choices.restock_categories ?? []}
            value={planning.restock_categories}
            onChange={(v) => setPlanning({ restock_categories: v })}
            searchable
            clearable
          />
          <Checkbox
            mt="lg"
            label="Use Description_2 (if mapped)"
            checked={planning.use_description_2}
            onChange={(e) => setPlanning({ use_description_2: e.currentTarget.checked })}
          />
        </SimpleGrid>
      </Fieldset>

      <Fieldset legend="Result workbook">
        <Stack gap="xs">
          <Checkbox
            label="Include cabinet planogram sheet"
            description="Draws each proposed cabinet as a grid with every tool in a numbered compartment."
            checked={settings.export.include_planogram}
            onChange={(e) => setExport({ include_planogram: e.currentTarget.checked })}
          />
          <Checkbox
            label="Include technical / diagnostic sheets"
            description="The full audit result, Run_Metadata, distribution sheets and more; useful for review."
            checked={settings.export.include_technical}
            onChange={(e) => setExport({ include_technical: e.currentTarget.checked })}
          />
        </Stack>
      </Fieldset>

      {problems.length > 0 && (
        <Alert color="red" title="Check these settings">
          <List size="sm">
            {problems.map((p) => <List.Item key={p}>{p}</List.Item>)}
          </List>
        </Alert>
      )}
      {start.isError && <ErrorAlert title="The run was not started" error={start.error} />}

      <Group justify="space-between">
        <Button variant="default" onClick={onBack}>Back</Button>
        <Button
          onClick={() => start.mutate()}
          disabled={problems.length > 0 || request === null}
          loading={start.isPending}
        >
          Run planning
        </Button>
      </Group>
    </Stack>
  );
}
