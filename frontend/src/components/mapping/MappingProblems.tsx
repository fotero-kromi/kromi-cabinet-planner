// What stops the mapping: empty required fields, and the server's check.
import { Alert, List, Text } from "@mantine/core";

import type { MappingCheck } from "../../api/client";

export function MappingProblems({ missingRequired, check }: {
  missingRequired: string[];
  /** the server's check of the current mapping, when there is one */
  check: MappingCheck | null;
}) {
  return (
    <>
      {missingRequired.length > 0 && (
        <Alert color="yellow">Choose a column for: {missingRequired.join(", ")}</Alert>
      )}
      {check && !check.ok && (
        <Alert color="red" title="Column mapping conflict">
          <List size="sm">
            {Object.entries(check.conflicts).map(([column, fields]) => (
              <List.Item key={column}>'{column}' is mapped to: {fields.join(", ")}</List.Item>
            ))}
            {check.missing_columns.map((column) => (
              <List.Item key={column}>The sheet has no column '{column}'.</List.Item>
            ))}
          </List>
          <Text size="sm" mt="xs">Pick one field per column and clear the others.</Text>
        </Alert>
      )}
    </>
  );
}
