import { Alert, List } from "@mantine/core";

/** A titled list of messages; nothing when the list is empty. */
export function IssueList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Alert color="yellow" title={title}>
      <List size="sm">{items.map((item, i) => <List.Item key={i}>{item}</List.Item>)}</List>
    </Alert>
  );
}
