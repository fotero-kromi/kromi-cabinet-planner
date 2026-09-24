// Drop zone for one Excel workbook, with the back end's type and size limits.
import { Group, Stack, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";

import { MAX_UPLOAD_BYTES, rejectionMessage } from "../../lib/upload";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function FileDrop({ onFile, onReject, loading }: {
  onFile: (file: File) => void;
  onReject: (message: string) => void;
  loading: boolean;
}) {
  return (
    <Dropzone
      onDrop={(files) => {
        const file = files[0];
        if (file) onFile(file);
      }}
      onReject={(files) => onReject(rejectionMessage(files))}
      accept={{ [XLSX]: [".xlsx"] }}
      maxSize={MAX_UPLOAD_BYTES}
      multiple={false}
      loading={loading}
      inputProps={{ "aria-label": "Excel file" }}
    >
      <Group justify="center" mih={140} style={{ pointerEvents: "none" }}>
        <Stack gap={4} align="center">
          <Text size="lg">Drop the customer's tool list here, or click to choose a file</Text>
          <Text size="sm" c="dimmed">Excel workbook (.xlsx), up to 20 MB</Text>
        </Stack>
      </Group>
    </Dropzone>
  );
}
