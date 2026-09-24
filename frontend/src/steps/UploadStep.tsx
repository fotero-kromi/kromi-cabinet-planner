import { Group, Stack, Text } from "@mantine/core";
import { Dropzone, type FileRejection } from "@mantine/dropzone";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { uploadWorkbook, type Workbook } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
/** The back end's limit (kromi_api/config.py MAX_UPLOAD_BYTES). */
const MAX_BYTES = 20 * 1024 * 1024;

export function UploadStep({ workbook, onUploaded }: {
  workbook: Workbook | null;
  onUploaded: (workbook: Workbook) => void;
}) {
  const [rejected, setRejected] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: uploadWorkbook, onSuccess: onUploaded });

  const onReject = (files: FileRejection[]) => {
    const reason = files[0]?.errors[0];
    setRejected(reason?.code === "file-too-large"
      ? "The file is larger than 20 MB."
      : "Only Excel workbooks (.xlsx) can be planned.");
  };

  return (
    <Stack>
      <Dropzone
        onDrop={(files) => {
          setRejected(null);
          const file = files[0];
          if (file) upload.mutate(file);
        }}
        onReject={onReject}
        accept={{ [XLSX]: [".xlsx"] }}
        maxSize={MAX_BYTES}
        multiple={false}
        loading={upload.isPending}
        inputProps={{ "aria-label": "Excel file" }}
      >
        <Group justify="center" mih={140} style={{ pointerEvents: "none" }}>
          <Stack gap={4} align="center">
            <Text size="lg">Drop the customer's tool list here, or click to choose a file</Text>
            <Text size="sm" c="dimmed">Excel workbook (.xlsx), up to 20 MB</Text>
          </Stack>
        </Group>
      </Dropzone>
      {rejected && <ErrorAlert title="Upload failed" error={rejected} />}
      {upload.isError && <ErrorAlert title="Upload failed" error={upload.error} />}
      {workbook && !upload.isPending && (
        <Text size="sm">
          Current file: <b>{workbook.filename}</b> ({workbook.sheets.length} sheet
          {workbook.sheets.length === 1 ? "" : "s"}). Drop another file to replace it.
        </Text>
      )}
    </Stack>
  );
}
