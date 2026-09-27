import { Alert, Code, Text } from "@mantine/core";

import { ApiError } from "../api/client";

/** An error from a call, with the server's details when it sent any. */
export function ErrorAlert({ title, error }: { title: string; error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const details = error instanceof ApiError && error.code !== "invalid_request" ? error.details : null;
  return (
    <Alert color="red" title={title}>
      <Text size="sm" style={{ whiteSpace: "pre-line" }}>{message}</Text>
      {details != null && (
        <Code block mt="xs">{JSON.stringify(details, null, 2)}</Code>
      )}
    </Alert>
  );
}
