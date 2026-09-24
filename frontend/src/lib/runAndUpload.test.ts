import type { FileRejection } from "@mantine/dropzone";
import { describe, expect, it } from "vitest";

import { run } from "../test/fixtures";
import { runFinished } from "./run";
import { MAX_UPLOAD_BYTES, rejectionMessage } from "./upload";

const rejected = (code: string) =>
  [{ file: new File(["x"], "a.txt"), errors: [{ code, message: code }] }] as unknown as FileRejection[];

describe("a run", () => {
  it("is finished once it succeeded or failed", () => {
    expect(runFinished(run())).toBe(true);
    expect(runFinished(run({ status: "failed" }))).toBe(true);
    expect(runFinished(run({ status: "queued" }))).toBe(false);
    expect(runFinished(run({ status: "running" }))).toBe(false);
    expect(runFinished(undefined)).toBe(false);
  });
});

describe("a refused file", () => {
  it("is explained in the user's words", () => {
    expect(rejectionMessage(rejected("file-too-large"))).toBe("The file is larger than 20 MB.");
    expect(rejectionMessage(rejected("file-invalid-type"))).toBe(
      "Only Excel workbooks (.xlsx) can be planned.");
    expect(MAX_UPLOAD_BYTES).toBe(20 * 1024 * 1024);
  });
});
