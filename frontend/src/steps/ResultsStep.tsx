import { Alert, Button, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";

import { api, unwrap, workbookDownloadUrl } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";
import { ArticleTable } from "../components/results/ArticleTable";
import { BucketTable } from "../components/results/BucketTable";
import { IssueList } from "../components/results/IssueList";
import { RunStatus } from "../components/results/RunStatus";
import { Totals } from "../components/results/Totals";
import { runFinished } from "../lib/run";

/** How often an unfinished run is asked for its status. */
export const POLL_MS = 1000;

export function ResultsStep({ runId, reused, onChangeSettings, onStartOver }: {
  runId: number;
  reused: boolean;
  onChangeSettings: () => void;
  onStartOver: () => void;
}) {
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => unwrap(api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
    refetchInterval: (query) => (runFinished(query.state.data) ? false : POLL_MS),
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
      {run.data && <RunStatus run={run.data} />}

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
          <IssueList title="Notes" items={run.data.notes} />
          <IssueList title="Validation issues" items={summary.validation_issues} />
          <IssueList title="Export problems" items={summary.export_problems} />
          {summary.buckets.length > 1 && (
            <div>
              <Title order={4} mb="xs">Per supply point</Title>
              <BucketTable buckets={summary.buckets} />
            </div>
          )}
          <div>
            <Title order={4} mb="xs">Articles</Title>
            {tools.isError && <ErrorAlert title="The articles cannot be loaded" error={tools.error} />}
            {tools.isPending && <Loader size="sm" />}
            {tools.data && <ArticleTable tools={tools.data} />}
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
