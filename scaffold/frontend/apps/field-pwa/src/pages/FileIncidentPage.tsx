import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { accessClaims } from "../lib/auth";
import { useOnline } from "../lib/net";
import { fileIncident, runQueuedWrite, type WriteOutcome } from "../lib/sync";
import { OutcomeAlert, nowLocalInput } from "../components/queued";

export function FileIncidentPage() {
  const navigate = useNavigate();
  const online = useOnline();
  const claims = accessClaims();

  const [incidentType, setIncidentType] = useState("");
  const [description, setDescription] = useState("");
  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [reportedAt, setReportedAt] = useState(nowLocalInput);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<WriteOutcome | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setBusy(true);
    setOutcome(null);
    try {
      const result = await runQueuedWrite(() =>
        fileIncident({
          reported_by: claims.sub,
          incident_type: incidentType.trim(),
          description: description.trim(),
          station_id: stationId.trim(),
          reported_at: new Date(reportedAt).toISOString(),
        }),
      );
      setOutcome(result);
      if (result.kind === "synced" || result.kind === "queued") {
        setIncidentType("");
        setDescription("");
        setReportedAt(nowLocalInput());
      }
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

      <OutcomeAlert outcome={outcome} noun="incident" onReauth={() => navigate("/login", { replace: true })} />

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
