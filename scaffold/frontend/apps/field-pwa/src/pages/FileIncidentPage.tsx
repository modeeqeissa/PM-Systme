import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { accessClaims, clearTokens } from "../lib/auth";
import { outboxAll } from "../lib/db";
import { useOnline } from "../lib/net";
import { fileIncident, syncNow } from "../lib/sync";

function nowLocalInput(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

type Outcome =
  | { kind: "synced" }
  | { kind: "queued" }
  | { kind: "rejected"; detail: string }
  | { kind: "reauth" };

export function FileIncidentPage() {
  const navigate = useNavigate();
  const online = useOnline();
  const claims = accessClaims();

  const [incidentType, setIncidentType] = useState("");
  const [description, setDescription] = useState("");
  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [reportedAt, setReportedAt] = useState(nowLocalInput);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setBusy(true);
    setOutcome(null);
    try {
      const localId = await fileIncident({
        reported_by: claims.sub,
        incident_type: incidentType.trim(),
        description: description.trim(),
        station_id: stationId.trim(),
        reported_at: new Date(reportedAt).toISOString(),
      });
      const r = await syncNow();
      if (r.needsReauth) {
        setOutcome({ kind: "reauth" });
        return;
      }
      const row = (await outboxAll()).find((o) => o.id === localId);
      if (row?.state === "synced") setOutcome({ kind: "synced" });
      else if (row?.state === "rejected")
        setOutcome({ kind: "rejected", detail: row.lastError ?? "rejected" });
      else setOutcome({ kind: "queued" });

      setIncidentType("");
      setDescription("");
      setReportedAt(nowLocalInput());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <Link to="/" className="mb-4 inline-block text-sm text-slate-500 underline">
        ← My cases
      </Link>
      <h1 className="text-lg font-semibold text-slate-900">File an incident</h1>
      <p className="mb-4 text-sm text-slate-500">
        FR-CASE-01 / FR-CASE-10 — saved on this device immediately, then synced
        to case-service. Filing the same report twice can't create a duplicate.
      </p>

      {!online && (
        <div className="mb-3">
          <Alert variant="error">
            Offline — this will be saved on your device and sent automatically
            when you reconnect.
          </Alert>
        </div>
      )}

      {outcome?.kind === "synced" && (
        <div className="mb-3">
          <Alert variant="info">Filed and synced to case-service.</Alert>
        </div>
      )}
      {outcome?.kind === "queued" && (
        <div className="mb-3">
          <Alert variant="info">
            Saved on this device. It will sync automatically when you have signal
            (or use “Sync now” on the cases screen).
          </Alert>
        </div>
      )}
      {outcome?.kind === "rejected" && (
        <div className="mb-3">
          <Alert variant="error">
            The server rejected this incident ({outcome.detail}). Nothing was
            filed — fix the details and try again.
          </Alert>
        </div>
      )}
      {outcome?.kind === "reauth" && (
        <div className="mb-3">
          <Alert variant="error">
            Your session needs a refresh and the server can't be reached, or your
            login has fully expired. The incident is saved on this device.{" "}
            <button
              className="underline"
              onClick={() => {
                clearTokens();
                navigate("/login", { replace: true });
              }}
            >
              Sign in again
            </button>{" "}
            to sync it.
          </Alert>
        </div>
      )}

      <Card>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <TextInput
            label="Incident type"
            value={incidentType}
            onChange={(e) => setIncidentType(e.target.value)}
            placeholder="e.g. theft, assault, traffic"
            required
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="desc" className="text-sm font-medium text-slate-700">
              What happened
            </label>
            <textarea
              id="desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <TextInput
            label="Station id"
            value={stationId}
            onChange={(e) => setStationId(e.target.value)}
            required
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="when" className="text-sm font-medium text-slate-700">
              When
            </label>
            <input
              id="when"
              type="datetime-local"
              value={reportedAt}
              onChange={(e) => setReportedAt(e.target.value)}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <Button type="submit" loading={busy}>
            File incident
          </Button>
        </form>
      </Card>
    </div>
  );
}
