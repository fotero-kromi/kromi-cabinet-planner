// The planner as four steps: upload, sheet and columns, settings, run and
// results. The steps keep their inputs while the user moves back and forth;
// a new file starts over.
import { AppShell, Badge, Container, Group, Loader, Stepper, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, fetchDefaults, unwrap, type Run, type Workbook } from "./api/client";
import { ErrorAlert } from "./components/ErrorAlert";
import { initialSettings, type SettingsDraft } from "./lib/settings";
import { MappingStep, type Source, type StoredMapping } from "./steps/MappingStep";
import { ResultsStep } from "./steps/ResultsStep";
import { SettingsStep } from "./steps/SettingsStep";
import { UploadStep } from "./steps/UploadStep";

type Step = 0 | 1 | 2 | 3;

export default function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => unwrap(api.GET("/api/v1/health")) });
  const defaults = useQuery({
    queryKey: ["defaults"],
    queryFn: fetchDefaults,
    staleTime: Infinity,
  });

  const [step, setStep] = useState<Step>(0);
  const [workbook, setWorkbook] = useState<Workbook | null>(null);
  const [source, setSource] = useState<Source>({ sheet: null, headerRow: 1 });
  const [mapping, setMapping] = useState<StoredMapping | null>(null);
  const [headerRow, setHeaderRow] = useState(1);
  const [edited, setEdited] = useState<SettingsDraft | null>(null);
  const [run, setRun] = useState<Run | null>(null);

  const settings = edited ?? (defaults.data ? initialSettings(defaults.data) : null);

  const startOver = (next: Workbook | null) => {
    setWorkbook(next);
    setSource({ sheet: null, headerRow: defaults.data?.header_row ?? 1 });
    setMapping(null);
    setRun(null);
    setStep(next ? 1 : 0);
  };

  // A step can be revisited; later steps open only once their inputs exist.
  const reachable = (s: Step) =>
    s === 0 || (s === 1 && workbook !== null) || (s === 2 && mapping !== null && step >= 2) || (s === 3 && run !== null);

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header px="md">
        <Group h="100%" justify="space-between">
          <Title order={3} c="kromi.6">Kromi Cabinet Planner</Title>
          {health.data && <Badge variant="light">Engine {health.data.build}</Badge>}
          {health.isError && <Badge color="red">Server not reachable</Badge>}
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="xl">
          {defaults.isError && <ErrorAlert title="The planner server cannot be reached" error={defaults.error} />}
          <Stepper active={step} onStepClick={(s) => reachable(s as Step) && setStep(s as Step)} mt="md">
            <Stepper.Step label="Upload" description="Tool list">
              <UploadStep workbook={workbook} onUploaded={(wb) => startOver(wb)} />
            </Stepper.Step>
            <Stepper.Step label="Sheet and columns" description="What is where">
              {workbook && (
                <MappingStep
                  workbook={workbook}
                  source={source}
                  onSourceChange={setSource}
                  mapping={mapping}
                  onMappingChange={setMapping}
                  onBack={() => setStep(0)}
                  onNext={(m, row) => {
                    setMapping(m);
                    setHeaderRow(row);
                    setStep(2);
                  }}
                />
              )}
            </Stepper.Step>
            <Stepper.Step label="Settings" description="Planning rules">
              {!settings && <Loader />}
              {workbook && mapping && source.sheet && settings && defaults.data && (
                <SettingsStep
                  workbookId={workbook.id}
                  sheet={source.sheet}
                  headerRow={headerRow}
                  mapping={mapping.draft}
                  defaults={defaults.data}
                  settings={settings}
                  onChange={setEdited}
                  onBack={() => setStep(1)}
                  onStarted={(r) => {
                    setRun(r);
                    setStep(3);
                  }}
                />
              )}
            </Stepper.Step>
            <Stepper.Step label="Run and results" description="Plan and workbook">
              {run && (
                <ResultsStep
                  key={run.id}
                  runId={run.id}
                  reused={run.reused ?? false}
                  onChangeSettings={() => setStep(2)}
                  onStartOver={() => startOver(null)}
                />
              )}
            </Stepper.Step>
          </Stepper>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
