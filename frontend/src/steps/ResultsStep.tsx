import { Alert, Button, Code, Group, List, Loader, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import type { ColDef } from "ag-grid-community";

import { api, unwrap, workbookDownloadUrl, type Bucket, type Run, type Tool } from "../api/client";
import { DataGrid } from "../components/DataGrid";
import { ErrorAlert } from "../components/ErrorAlert";

/** How often an unfinished run is asked for its status. */
export const POLL_MS = 1000;

const finished = (run: Run | undefined) => run?.status === "succeeded" || run?.status === "failed";

const number = (digits: number) => (p: { value: unknown }) =>
  typeof p.value === "number" ? p.value.toLocaleString("en", { maximumFractionDigits: digits }) : "";

const TOOL_COLUMNS: ColDef<Tool>[] = [
  { field: "line_no", headerName: "Line", width: 80 },
  { field: "code", headerName: "Code" },
  { field: "description", headerName: "Description", flex: 1, minWidth: 220 },
  { field: "category", headerName: "Category" },
  { field: "size", headerName: "Size", width: 90 },
  { field: "system_category", headerName: "KTC / Kanban", width: 130 },
  { field: "cabinet_type", headerName: "Cabinet type", width: 130 },
  { field: "supply_point", headerName: "SP", width: 80 },
  { field: "pack_units", headerName: "Pack units", width: 110, valueFormatter: number(2) },
  { field: "monthly_pcs", headerName: "Pieces / month", width: 140, valueFormatter: number(2) },
  { field: "monthly_packs", headerName: "Packs / month", width: 140, valueFormatter: number(2) },
  { field: "spirals", headerName: "Spirals", width: 100 },
  { field: "compartments", headerName: "Compartments", width: 140 },
];

const BUCKET_COLUMNS: ColDef<Bucket>[] = [
  { field: "label", headerName: "Scope", flex: 1 },
  { field: "ktc_count", headerName: "KTC articles" },
  { field: "kanban_count", headerName: "Kanban articles" },
  { field: "helix_cabinets", headerName: "Helix" },
  { field: "carousel_cabinets", headerName: "Carousel" },
  { field: "locker_a_cabinets", headerName: "Locker A" },
  { field: "locker_b_cabinets", headerName: "Locker B" },
  { field: "locker_c_cabinets", headerName: "Locker C" },
  { field: "total_cabinets", headerName: "Total cabinets" },
];

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Paper withBorder p="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
      <Text size="xl" fw={700}>{value}</Text>
    </Paper>
  );
}

function Totals({ all }: { all: Bucket }) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, md: 6 }} role="region" aria-label="Totals">
      <Stat label="Total cabinets" value={all.total_cabinets} />
      <Stat label="Helix" value={all.helix_cabinets} />
      <Stat label="Carousel" value={all.carousel_cabinets} />
      <Stat label="Locker A / B / C"
            value={`${all.locker_a_cabinets} / ${all.locker_b_cabinets} / ${all.locker_c_cabinets}`} />
      <Stat label="KTC articles" value={all.ktc_count} />
      <Stat label="Kanban articles" value={all.kanban_count} />
    </SimpleGrid>
  );
}

function Issues({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Alert color="yellow" title={title}>
      <List size="sm">{items.map((item, i) => <List.Item key={i}>{item}</List.Item>)}</List>
    </Alert>
  );
}

export function ResultsStep({ runId, reused, onChangeSettings, onStartOver }: {
  runId: number;
  reused: boolean;
  onChangeSettings: () => void;
  onStartOver: () => void;
}) {
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => unwrap(api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
    refetchInterval: (query) => (finished(query.state.data) ? false : POLL_MS),
  });
  const succeeded = run.data?.status === "succeeded";
  const tools = useQuery({
    queryKey: ["run-tools", runId],
    queryFn: () => unwrap(api.GET("/api/v1/runs/{run_id}/tools", { params: { path: { run_id: runId } } })),
    enabled: succeeded,
  });

  const summary = run.data?.summary;
  const all = summary?.buckets.find((b) => b.position === 0) ?? summary?.buckets[0];

  return (
    <Stack>
      {run.isError && <ErrorAlert title="The run cannot be loaded" error={run.error} />}
      {run.data && !finished(run.data) && (
        <Group>
          <Loader size="sm" />
          <Text>Planning the cabinets...</Text>
        </Group>
      )}
      {run.data?.status === "failed" && (
        <Alert color="red" title="The run failed">
          <Text size="sm">{run.data.error?.message || "The run failed without a message."}</Text>
          {run.data.error?.details != null && (
            <Code block mt="xs">{JSON.stringify(run.data.error.details, null, 2)}</Code>
          )}
        </Alert>
      )}

      {succeeded && run.data && summary && all && (
        <>
          {reused && (
            <Alert color="blue">
              The same file with the same settings was planned before (run {runId}); its stored result is
              shown.
            </Alert>
          )}
          <Group justify="space-between" align="flex-end">
            <div>
              <Title order={3}>Result</Title>
              <Text size="sm" c="dimmed">
                Run {runId}{summary.customer ? `, ${summary.customer}` : ""}
                {summary.site ? ` / ${summary.site}` : ""}, engine {run.data.engine_build}
              </Text>
            </div>
            <Button component="a" href={workbookDownloadUrl(runId)} download>
              Download result workbook
            </Button>
          </Group>
          <Totals all={all} />
          <Issues title="Notes" items={run.data.notes} />
          <Issues title="Validation issues" items={summary.validation_issues} />
          <Issues title="Export problems" items={summary.export_problems} />
          {summary.buckets.length > 1 && (
            <div>
              <Title order={4} mb="xs">Per supply point</Title>
              <DataGrid<Bucket> label="Per supply point" rows={summary.buckets} columns={BUCKET_COLUMNS}
                                height={60 + 42 * summary.buckets.length} />
            </div>
          )}
          <div>
            <Title order={4} mb="xs">Articles</Title>
            {tools.isError && <ErrorAlert title="The articles cannot be loaded" error={tools.error} />}
            {tools.isPending && <Loader size="sm" />}
            {tools.data && (
              <DataGrid<Tool> label="Articles" rows={tools.data} columns={TOOL_COLUMNS} height={520} />
            )}
          </div>
        </>
      )}

      <Group justify="space-between">
        <Button variant="default" onClick={onChangeSettings}>Change settings</Button>
        <Button variant="default" onClick={onStartOver}>Start over</Button>
      </Group>
    </Stack>
  );
}
