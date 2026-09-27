import type { Run } from "../api/client";

/** A run is finished once it succeeded or failed; until then it is polled. */
export const runFinished = (run: Run | undefined): boolean =>
  run?.status === "succeeded" || run?.status === "failed";
