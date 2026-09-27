// The headline figures of a plan: cabinets per type and the KTC / Kanban split.
import { Paper, SimpleGrid, Text } from "@mantine/core";

import type { Bucket } from "../../api/client";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Paper withBorder p="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
      <Text size="xl" fw={700}>{value}</Text>
    </Paper>
  );
}

export function Totals({ all }: { all: Bucket }) {
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
