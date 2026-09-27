import { Stack, Text } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { uploadWorkbook, type Workbook } from "../api/client";
import { ErrorAlert } from "../components/ErrorAlert";
import { FileDrop } from "../components/upload/FileDrop";

export function UploadStep({ workbook, onUploaded }: {
  workbook: Workbook | null;
  onUploaded: (workbook: Workbook) => void;
}) {
  const [rejected, setRejected] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: uploadWorkbook, onSuccess: onUploaded });

  return (
    <Stack>
      <FileDrop
        onFile={(file) => {
          setRejected(null);
          upload.mutate(file);
        }}
        onReject={setRejected}
        loading={upload.isPending}
      />
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
