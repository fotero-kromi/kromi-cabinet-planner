import type { FileRejection } from "@mantine/dropzone";

/** The back end's limit (kromi_api/config.py MAX_UPLOAD_BYTES). */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/** Why the drop zone refused a file, in the user's words. */
export function rejectionMessage(files: FileRejection[]): string {
  return files[0]?.errors[0]?.code === "file-too-large"
    ? "The file is larger than 20 MB."
    : "Only Excel workbooks (.xlsx) can be planned.";
}
