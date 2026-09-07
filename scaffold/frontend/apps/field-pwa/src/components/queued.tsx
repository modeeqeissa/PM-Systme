import { Alert } from "@pmp/ui";
import type { WriteOutcome } from "../lib/sync";

export function nowLocalInput(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

/** The standard result banner for a queued field write. */
export function OutcomeAlert({
  outcome,
  noun,
  onReauth,
}: {
  outcome: WriteOutcome | null;
  noun: string;
  onReauth: () => void;
}) {
  if (!outcome) return null;
  return (
    <div className="mb-3">
      {outcome.kind === "synced" && (
        <Alert variant="info">Filed and synced to the server.</Alert>
      )}
      {outcome.kind === "queued" && (
        <Alert variant="info">
          Saved on this device. It will sync automatically when you have signal
          (or use “Sync now” on the cases screen).
        </Alert>
      )}
      {outcome.kind === "rejected" && (
        <Alert variant="error">
          The server rejected this {noun} ({outcome.detail}). Nothing was filed —
          fix the details and try again.
        </Alert>
      )}
      {outcome.kind === "quota" && (
        <Alert variant="error">
          This device is out of storage — the {noun} was <strong>not</strong>{" "}
          saved. Sync or clear queued items first, then try again.
        </Alert>
      )}
      {outcome.kind === "reauth" && (
        <Alert variant="error">
          Your session expired and the server can't be reached (or your login
          fully expired). The {noun} is saved on this device.{" "}
          <button className="underline" onClick={onReauth}>
            Sign in again
          </button>{" "}
          to sync it.
        </Alert>
      )}
    </div>
  );
}
