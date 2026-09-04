import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import {
  ApiError,
  cases as casesApi,
  incidents as incidentsApi,
  validationErrors,
  type Incident,
} from "../lib/api";
import { currentClaims } from "../lib/auth";
import { useIdempotencyKey } from "../lib/idempotency";
import { localInputToIso, toLocalInputValue } from "../lib/datetime";

type Problem =
  | { kind: "validation"; fields: Record<string, string> }
  | { kind: "forbidden" }
  | { kind: "network" }
  | { kind: "other"; message: string };

function classify(err: unknown): Problem {
  if (err instanceof ApiError) {
    if (err.status === 422) return { kind: "validation", fields: validationErrors(err) };
    if (err.status === 403) return { kind: "forbidden" };
    return { kind: "other", message: err.message };
  }
  // fetch rejected — no response at all
  return { kind: "network" };
}

export function IncidentPage() {
  const navigate = useNavigate();
  const claims = currentClaims();
  const idem = useIdempotencyKey();

  const [incidentType, setIncidentType] = useState("");
  const [description, setDescription] = useState("");
  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [reportedAt, setReportedAt] = useState(() => toLocalInputValue(new Date()));

  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [filed, setFiled] = useState<{ incident: Incident; replayed: boolean } | null>(null);
  const [escalateErr, setEscalateErr] = useState<Problem | null>(null);

  const fieldErr = useMemo(
    () => (problem?.kind === "validation" ? problem.fields : {}),
    [problem],
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setProblem(null);
    setBusy(true);
    try {
      const result = await incidentsApi.create(
        {
          reported_by: claims.sub,
          incident_type: incidentType.trim(),
          description: description.trim(),
          station_id: stationId.trim(),
          reported_at: localInputToIso(reportedAt),
        },
        // SAME key on every retry of this submission — only rotated by "File another"
        idem.current(),
      );
      setFiled(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate("/login", { replace: true });
        return;
      }
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  async function escalate() {
    if (!filed || !claims) return;
    setEscalateErr(null);
    setBusy(true);
    try {
      await casesApi.create({
        incident_id: filed.incident.id,
        lead_officer_id: claims.sub,
      });
      navigate("/cases");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate("/login", { replace: true });
        return;
      }
      setEscalateErr(classify(err));
    } finally {
      setBusy(false);
    }
  }

  function fileAnother() {
    idem.rotate(); // a genuinely new submission gets a fresh key
    setFiled(null);
    setProblem(null);
    setEscalateErr(null);
    setIncidentType("");
    setDescription("");
    setReportedAt(toLocalInputValue(new Date()));
  }

  // --- filed view -------------------------------------------------------
  if (filed) {
    const inc = filed.incident;
    return (
      <Shell>
        <Card>
          <div className="mb-4">
            <Alert variant="info">
              {filed.replayed
                ? "This incident was already filed with that idempotency key — showing the existing record (no duplicate created)."
                : "Incident filed."}
            </Alert>
          </div>
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-slate-500">Incident id</dt>
            <dd className="font-mono text-xs text-slate-700">{inc.id}</dd>
            <dt className="text-slate-500">Type</dt>
            <dd className="text-slate-900">{inc.incident_type}</dd>
            <dt className="text-slate-500">Description</dt>
            <dd className="text-slate-900">{inc.description}</dd>
            <dt className="text-slate-500">Station</dt>
            <dd className="font-mono text-xs text-slate-700">{inc.station_id}</dd>
            <dt className="text-slate-500">Reported at</dt>
            <dd className="text-slate-900">{new Date(inc.reported_at).toLocaleString()}</dd>
          </dl>

          {escalateErr && (
            <div className="mt-4">
              <Alert variant="error">
                {escalateErr.kind === "forbidden"
                  ? "Your role can't open cases (needs the case.write permission)."
                  : escalateErr.kind === "network"
                    ? "Couldn't reach case-service. Try again."
                    : escalateErr.kind === "other"
                      ? escalateErr.message
                      : "Couldn't escalate."}
              </Alert>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <Button onClick={escalate} loading={busy}>
              Escalate to a case
            </Button>
            <Button variant="secondary" onClick={fileAnother} disabled={busy}>
              File another incident
            </Button>
            <Link
              to="/cases"
              className="inline-flex items-center text-sm text-slate-500 underline"
            >
              Back to cases
            </Link>
          </div>
        </Card>
      </Shell>
    );
  }

  // --- form view -------------------------------------------------------
  return (
    <Shell>
      <Card>
        <h1 className="text-lg font-semibold text-slate-900">File an incident</h1>
        <p className="mb-6 text-sm text-slate-500">
          Filing as <span className="font-medium">{claims?.badge_number}</span> — FR-CASE-01.
        </p>

        {problem?.kind === "forbidden" && (
          <div className="mb-4">
            <Alert variant="error">
              Your role can't file incidents. This needs the <code>case.write</code>{" "}
              permission — ask an administrator to grant it.
            </Alert>
          </div>
        )}
        {problem?.kind === "network" && (
          <div className="mb-4">
            <Alert variant="error">
              Couldn't reach case-service. Your entry is not lost — press{" "}
              <strong>File incident</strong> again to retry with the same
              idempotency key.
            </Alert>
          </div>
        )}
        {problem?.kind === "other" && (
          <div className="mb-4">
            <Alert variant="error">{problem.message}</Alert>
          </div>
        )}
        {problem?.kind === "validation" && Object.keys(fieldErr).length === 0 && (
          <div className="mb-4">
            <Alert variant="error">The server rejected the form. Check the fields.</Alert>
          </div>
        )}

        <form onSubmit={submit} className="flex flex-col gap-4">
          <TextInput
            label="Incident type"
            value={incidentType}
            onChange={(e) => setIncidentType(e.target.value)}
            error={fieldErr.incident_type}
            maxLength={50}
            placeholder="e.g. burglary, theft, assault"
            autoFocus
            required
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="desc" className="text-sm font-medium text-slate-700">
              Description
            </label>
            <textarea
              id="desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              required
              className={
                "rounded-md border px-3 py-2 text-sm text-slate-900 shadow-sm " +
                "focus:outline-none focus:ring-2 focus:ring-slate-400 " +
                (fieldErr.description ? "border-red-400" : "border-slate-300")
              }
            />
            {fieldErr.description && (
              <p className="text-xs text-red-600">{fieldErr.description}</p>
            )}
          </div>
          <TextInput
            label="Station id"
            value={stationId}
            onChange={(e) => setStationId(e.target.value)}
            error={fieldErr.station_id}
            hint="Defaults to your station; change it if you're reporting for another."
            required
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="reported_at" className="text-sm font-medium text-slate-700">
              Reported at
            </label>
            <input
              id="reported_at"
              type="datetime-local"
              value={reportedAt}
              onChange={(e) => setReportedAt(e.target.value)}
              required
              className={
                "rounded-md border px-3 py-2 text-sm text-slate-900 shadow-sm " +
                "focus:outline-none focus:ring-2 focus:ring-slate-400 " +
                (fieldErr.reported_at ? "border-red-400" : "border-slate-300")
              }
            />
            {fieldErr.reported_at && (
              <p className="text-xs text-red-600">{fieldErr.reported_at}</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button type="submit" loading={busy}>
              File incident
            </Button>
            <Link to="/cases" className="text-sm text-slate-500 underline">
              Cancel
            </Link>
          </div>
        </form>
      </Card>
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-xl px-4 py-8">{children}</div>;
}
