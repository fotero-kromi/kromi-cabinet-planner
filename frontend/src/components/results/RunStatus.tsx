// A run that is not (successfully) finished: planning in progress, or why it failed.
import { Alert, Code, Group, Loader, Text } from "@mantine/core";

import type { Run } from "../../api/client";
import { runFinished } from "../../lib/run";

export function RunStatus({ run }: { run: Run }) {
  if (!runFinished(run)) {
    return (
      <Group>
        <Loader size="sm" />
        <Text>Planning the cabinets...</Text>
      </Group>
    );
  }
  if (run.status === "failed") {
    return (
      <Alert color="red" title="The run failed">
        <Text size="sm">{run.error?.message || "The run failed without a message."}</Text>
        {run.error?.details != null && (
          <Code block mt="xs">{JSON.stringify(run.error.details, null, 2)}</Code>
        )}
      </Alert>
    );
  }
  return null;
}
