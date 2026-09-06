import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, community } from "../../lib/api";
import { currentClaims } from "../../lib/auth";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

export function MeetingsPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("community.write");

  const query = useQuery({
    queryKey: ["cm-meetings"],
    queryFn: () => community.meetings.list(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (query.error instanceof ApiError && query.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <h1 className="text-xl font-semibold text-slate-900">Community meetings</h1>
        <p className="mb-6 text-sm text-slate-500">
          FR-COMM-01 — logged community engagement sessions, with an attendee summary.
        </p>

        {canWrite && <NewMeetingForm />}

        {query.isLoading && (
          <Card>
            <Spinner label="Loading meetings…" />
          </Card>
        )}
        {query.error instanceof ApiError && query.error.status === 403 && (
          <Alert variant="error">
            Your role can't view meetings (needs <code>community.read</code>).
          </Alert>
        )}
        {query.data && query.data.length === 0 && (
          <Card>
            <p className="text-sm text-slate-500">No meetings logged yet.</p>
          </Card>
        )}
        <div className="flex flex-col gap-4">
          {(query.data ?? []).map((m) => (
            <Card key={m.id}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-slate-900">{m.location}</h3>
                  <p className="text-sm text-slate-500">
                    {m.meeting_date} · facilitator{" "}
                    <span className="font-mono text-xs">{m.facilitator_id.slice(0, 8)}…</span>
                  </p>
                </div>
                <span className="font-mono text-xs text-slate-400">{m.station_id.slice(0, 8)}…</span>
              </div>
              {m.attendee_summary && (
                <p className="mt-2 text-sm text-slate-600">{m.attendee_summary}</p>
              )}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function NewMeetingForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const claims = currentClaims();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    station_id: claims?.station_id ?? "",
    facilitator_id: claims?.sub ?? "",
    meeting_date: "",
    location: "",
    attendee_summary: "",
  });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState(false);
  const fe = fieldErrors(problem);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setDone(false);
    setBusy(true);
    try {
      await community.meetings.create({
        station_id: form.station_id.trim(),
        facilitator_id: form.facilitator_id.trim(),
        meeting_date: form.meeting_date,
        location: form.location.trim(),
        attendee_summary: form.attendee_summary.trim() || null,
      });
      setDone(true);
      setForm({ ...form, meeting_date: "", location: "", attendee_summary: "" });
      await qc.invalidateQueries({ queryKey: ["cm-meetings"] });
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

  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Log meeting</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Log meeting"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <ProblemAlert
            problem={problem}
            service="community-service"
            forbiddenHint="Your role can't log meetings (needs community.write)."
          />
          {done && <Alert variant="info">Meeting logged.</Alert>}
          <TextInput label="Station id" value={form.station_id} onChange={set("station_id")} error={fe.station_id} placeholder="uuid" required />
          <TextInput label="Facilitator id" value={form.facilitator_id} onChange={set("facilitator_id")} error={fe.facilitator_id} placeholder="uuid" required />
          <div className="flex flex-col gap-1">
            <label htmlFor="mtg-date" className="text-sm font-medium text-slate-700">
              Meeting date
            </label>
            <input
              id="mtg-date"
              type="date"
              value={form.meeting_date}
              onChange={set("meeting_date")}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            {fe.meeting_date && <p className="text-xs text-red-600">{fe.meeting_date}</p>}
          </div>
          <TextInput label="Location" value={form.location} onChange={set("location")} error={fe.location} required />
          <div className="flex flex-col gap-1">
            <label htmlFor="mtg-att" className="text-sm font-medium text-slate-700">
              Attendee summary
            </label>
            <textarea
              id="mtg-att"
              value={form.attendee_summary}
              onChange={set("attendee_summary")}
              rows={3}
              placeholder="optional — who attended, roughly how many"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <div>
            <Button type="submit" loading={busy}>
              Log meeting
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
