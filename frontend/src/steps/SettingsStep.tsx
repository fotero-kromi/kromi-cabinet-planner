import { Alert, Button, Group, List, Stack, Text } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";

import { api, unwrap, type Defaults, type Run } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";
import { SettingsForm } from "../components/settings/SettingsForm";
import type { MappingDraft } from "../lib/mapping";
import { SETTING_FIELDS } from "../lib/settingFields";
import { type SettingsDraft, buildRunRequest, settingsProblems, shownNumberSettings } from "../lib/settings";

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
  const stdSpecialMapped = mapping.std_special !== null;
  const opMode = settings.planning.op_mode;
  const problems = settingsProblems(settings, defaults.limits, shownNumberSettings(settings, stdSpecialMapped));
  const request = buildRunRequest(sheet, headerRow, mapping, settings);

  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/runs", { body: { workbook_id: workbookId, settings: request! } })),
    onSuccess: onStarted,
  });

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Operation mode: {defaults.labels.op_mode?.[opMode] ?? "Standard"}. The other modes follow in a later
        version.
      </Text>
      <SettingsForm fields={SETTING_FIELDS} defaults={defaults} settings={settings}
                    stdSpecialMapped={stdSpecialMapped} opMode={opMode} onChange={onChange} />

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
