import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { AddForm } from "../../components/AddForm";
import {
  ApiError,
  hr,
  type Officer,
  type OfficerStatus,
} from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

const STATUS_LABEL: Record<OfficerStatus, string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  retired: "Retired",
};

export function OfficerProfilePage() {
  const { officerId = "" } = useParams();
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["hr-officer", officerId],
    queryFn: () => hr.officers.get(officerId),
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
        <Link to="/hr/officers" className="mb-4 inline-block text-sm text-slate-500 underline">
          ← Back to directory
        </Link>

        {query.isLoading && (
          <Card>
            <Spinner label="Loading officer…" />
          </Card>
        )}
        {query.error instanceof ApiError && query.error.status === 403 && (
          <Alert variant="error">
            Your role can't view officers (needs <code>hr.officer.read</code>).
          </Alert>
        )}
        {query.error instanceof ApiError && query.error.status === 404 && (
          <Alert variant="error">No officer with that id.</Alert>
        )}

        {query.data && (
          <>
            <OfficerHeader officer={query.data} />
            <AssignmentsCard officerId={officerId} />
            <TransfersCard officerId={officerId} />
            <LeaveCard officerId={officerId} />
            <PromotionsCard officerId={officerId} currentRank={query.data.rank} />
            <PerformanceCard officerId={officerId} />
            {hasPerm("hr.discipline.read") && <DisciplineCard officerId={officerId} />}
          </>
        )}
      </div>
    </div>
  );
}

function OfficerHeader({ officer }: { officer: Officer }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canWrite = hasPerm("hr.officer.write");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    badge_number: officer.badge_number,
    hire_date: officer.hire_date,
    status: officer.status,
    supervisor_id: officer.supervisor_id ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [saved, setSaved] = useState(false);
  const fe = fieldErrors(problem);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setSaved(false);
    setBusy(true);
    try {
      const patch: Record<string, unknown> = {};
      if (form.badge_number.trim() !== officer.badge_number) patch.badge_number = form.badge_number.trim();
      if (form.hire_date !== officer.hire_date) patch.hire_date = form.hire_date;
      if (form.status !== officer.status) patch.status = form.status;
      const sup = form.supervisor_id.trim();
      if (sup !== (officer.supervisor_id ?? "")) patch.supervisor_id = sup === "" ? null : sup;
      await hr.officers.update(officer.id, patch);
      setSaved(true);
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["hr-officer", officer.id] });
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
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{officer.badge_number}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {officer.rank} · unit <span className="font-mono text-xs">{officer.unit_id.slice(0, 8)}…</span>
          </p>
          <p className="text-sm text-slate-500">
            Hired {officer.hire_date}
            {officer.supervisor_id && (
              <> · supervisor <span className="font-mono text-xs">{officer.supervisor_id.slice(0, 8)}…</span></>
            )}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
          {STATUS_LABEL[officer.status]}
        </span>
      </div>

      {canWrite && (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-slate-700">Correct profile</h2>
            <Button variant="secondary" onClick={() => setEditing((v) => !v)}>
              {editing ? "Cancel" : "Edit"}
            </Button>
          </div>
          {saved && (
            <div className="mt-3">
              <Alert variant="info">Profile updated.</Alert>
            </div>
          )}
          {editing && (
            <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
              <p className="text-xs text-slate-500">
                Rank and unit aren't editable here — they're owned by the
                promotion (FR-HR-04) and transfer-approval (FR-HR-03) workflows.
              </p>
              <ProblemAlert
                problem={problem}
                service="hr-service"
                forbiddenHint="Your role can't edit officers (needs hr.officer.write)."
              />
              <TextInput
                label="Badge number"
                value={form.badge_number}
                onChange={(e) => setForm((f) => ({ ...f, badge_number: e.target.value }))}
                error={fe.badge_number}
              />
              <div className="flex flex-col gap-1">
                <label htmlFor="edit-hire" className="text-sm font-medium text-slate-700">
                  Hire date
                </label>
                <input
                  id="edit-hire"
                  type="date"
                  value={form.hire_date}
                  onChange={(e) => setForm((f) => ({ ...f, hire_date: e.target.value }))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="edit-status" className="text-sm font-medium text-slate-700">
                  Status
                </label>
                <select
                  id="edit-status"
                  value={form.status}
                  onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as OfficerStatus }))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                >
                  {(Object.keys(STATUS_LABEL) as OfficerStatus[]).map((s) => (
                    <option key={s} value={s}>
                      {STATUS_LABEL[s]}
                    </option>
                  ))}
                </select>
              </div>
              <TextInput
                label="Supervisor id"
                value={form.supervisor_id}
                onChange={(e) => setForm((f) => ({ ...f, supervisor_id: e.target.value }))}
                error={fe.supervisor_id}
                placeholder="another officer's id — blank to clear"
              />
              <div>
                <Button type="submit" loading={busy}>
                  Save changes
                </Button>
              </div>
            </form>
          )}
        </div>
      )}
    </Card>
  );
}

// --- history cards -----------------------------------------------------
function CardShell({
  title,
  fr,
  children,
}: {
  title: string;
  fr: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      <p className="mb-4 text-sm text-slate-500">{fr}</p>
      {children}
    </Card>
  );
}

function useList<T>(key: unknown[], fn: () => Promise<T[]>) {
  return useQuery({ queryKey: key, queryFn: fn, retry: (n: number, e: unknown) => !(e instanceof ApiError) && n < 2 });
}

function ListState({ q, noun }: { q: ReturnType<typeof useList>; noun: string }) {
  if (q.isLoading) return <Spinner label={`Loading ${noun}…`} />;
  if (q.error instanceof ApiError && q.error.status === 403)
    return <Alert variant="error">Your role can't view {noun}.</Alert>;
  if (q.data && (q.data as unknown[]).length === 0)
    return <p className="text-sm text-slate-500">No {noun} yet.</p>;
  return null;
}

function AssignmentsCard({ officerId }: { officerId: string }) {
  const qc = useQueryClient();
  const key = ["hr-assignments", officerId];
  const q = useList(key, () => hr.assignments.list(officerId));
  const [unitId, setUnitId] = useState("");
  const [startDate, setStartDate] = useState("");
  const canWrite = hasPerm("hr.assignment.write");

  return (
    <CardShell title="Assignments" fr="FR-HR-02 — unit assignment history; recording a new one closes the open one.">
      {canWrite && (
        <AddForm
          title="Record assignment"
          openLabel="New assignment"
          submitLabel="Record"
          service="hr-service"
          forbiddenHint="Needs hr.assignment.write."
          successText={() => "Assignment recorded."}
          onSubmit={async () => {
            await hr.assignments.create(officerId, { unit_id: unitId.trim(), start_date: startDate });
            setUnitId("");
            setStartDate("");
            await qc.invalidateQueries({ queryKey: key });
          }}
        >
          {(fe) => (
            <>
              <TextInput label="Unit id" value={unitId} onChange={(e) => setUnitId(e.target.value)} error={fe.unit_id} placeholder="uuid" required />
              <DateField id="asg-start" label="Start date" value={startDate} onChange={setStartDate} error={fe.start_date} />
            </>
          )}
        </AddForm>
      )}
      <ListState q={q} noun="assignments" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((a) => (
            <li key={a.id} className="border-b border-slate-100 pb-2 last:border-0">
              <span className="font-mono text-xs">{a.unit_id.slice(0, 8)}…</span>{" "}
              <span className="text-slate-500">
                {a.start_date} → {a.end_date ?? "current"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function TransfersCard({ officerId }: { officerId: string }) {
  const qc = useQueryClient();
  const key = ["hr-transfers", officerId];
  const q = useList(key, () => hr.transfers.forOfficer(officerId));
  const [toUnitId, setToUnitId] = useState("");
  const canWrite = hasPerm("hr.transfer.write");

  return (
    <CardShell title="Transfers" fr="FR-HR-03 — request a transfer; a commander approves it in the queue.">
      {canWrite && (
        <AddForm
          title="Request transfer"
          openLabel="Request transfer"
          submitLabel="Submit request"
          service="hr-service"
          forbiddenHint="Needs hr.transfer.write."
          successText={() => "Transfer requested (pending approval)."}
          onSubmit={async () => {
            await hr.transfers.request(officerId, { to_unit_id: toUnitId.trim() });
            setToUnitId("");
            await qc.invalidateQueries({ queryKey: key });
          }}
        >
          {(fe) => (
            <TextInput label="To unit id" value={toUnitId} onChange={(e) => setToUnitId(e.target.value)} error={fe.to_unit_id} placeholder="uuid" required />
          )}
        </AddForm>
      )}
      <ListState q={q} noun="transfers" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((t) => (
            <li key={t.id} className="border-b border-slate-100 pb-2 last:border-0">
              → <span className="font-mono text-xs">{t.to_unit_id.slice(0, 8)}…</span>{" "}
              <StatusPill status={t.status} />
              {t.effective_date && <span className="text-slate-500"> · effective {t.effective_date}</span>}
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function LeaveCard({ officerId }: { officerId: string }) {
  const qc = useQueryClient();
  const key = ["hr-leave", officerId];
  const q = useList(key, () => hr.leave.forOfficer(officerId));
  const [form, setForm] = useState({ leave_type: "", start_date: "", end_date: "" });
  const canWrite = hasPerm("hr.leave.write");

  return (
    <CardShell title="Leave" fr="FR-HR-05 — request leave; a supervisor approves it in the queue.">
      {canWrite && (
        <AddForm
          title="Request leave"
          openLabel="Request leave"
          submitLabel="Submit request"
          service="hr-service"
          forbiddenHint="Needs hr.leave.write."
          successText={() => "Leave requested (pending approval)."}
          onSubmit={async () => {
            await hr.leave.request(officerId, {
              leave_type: form.leave_type.trim(),
              start_date: form.start_date,
              end_date: form.end_date,
            });
            setForm({ leave_type: "", start_date: "", end_date: "" });
            await qc.invalidateQueries({ queryKey: key });
          }}
        >
          {(fe) => (
            <>
              <TextInput label="Leave type" value={form.leave_type} onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value }))} error={fe.leave_type} placeholder="e.g. annual, sick" required />
              <DateField id="lv-start" label="Start date" value={form.start_date} onChange={(v) => setForm((f) => ({ ...f, start_date: v }))} error={fe.start_date} />
              <DateField id="lv-end" label="End date" value={form.end_date} onChange={(v) => setForm((f) => ({ ...f, end_date: v }))} error={fe.end_date} />
            </>
          )}
        </AddForm>
      )}
      <ListState q={q} noun="leave requests" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((l) => (
            <li key={l.id} className="border-b border-slate-100 pb-2 last:border-0">
              <span className="capitalize">{l.leave_type}</span>{" "}
              <span className="text-slate-500">
                {l.start_date} → {l.end_date}
              </span>{" "}
              <StatusPill status={l.status} />
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function PromotionsCard({ officerId, currentRank }: { officerId: string; currentRank: string }) {
  const qc = useQueryClient();
  const key = ["hr-promotions", officerId];
  const q = useList(key, () => hr.promotions.list(officerId));
  const [form, setForm] = useState({ new_rank: "", effective_date: "", approved_by: "" });
  const canWrite = hasPerm("hr.promotion.write");

  return (
    <CardShell title="Promotions" fr="FR-HR-04 — recorded directly (no approval step); updates the officer's rank immediately.">
      {canWrite && (
        <AddForm
          title="Record promotion"
          openLabel="Record promotion"
          submitLabel="Record"
          service="hr-service"
          forbiddenHint="Needs hr.promotion.write."
          successText={() => "Promotion recorded."}
          onSubmit={async () => {
            await hr.promotions.record(officerId, {
              new_rank: form.new_rank.trim(),
              effective_date: form.effective_date,
              approved_by: form.approved_by.trim(),
            });
            setForm({ new_rank: "", effective_date: "", approved_by: "" });
            await qc.invalidateQueries({ queryKey: key });
            await qc.invalidateQueries({ queryKey: ["hr-officer", officerId] });
          }}
        >
          {(fe) => (
            <>
              <p className="text-xs text-slate-500">Current rank: {currentRank}</p>
              <TextInput label="New rank" value={form.new_rank} onChange={(e) => setForm((f) => ({ ...f, new_rank: e.target.value }))} error={fe.new_rank} required />
              <DateField id="promo-eff" label="Effective date" value={form.effective_date} onChange={(v) => setForm((f) => ({ ...f, effective_date: v }))} error={fe.effective_date} />
              <TextInput label="Approved by (officer id)" value={form.approved_by} onChange={(e) => setForm((f) => ({ ...f, approved_by: e.target.value }))} error={fe.approved_by} placeholder="uuid" required />
            </>
          )}
        </AddForm>
      )}
      <ListState q={q} noun="promotions" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((p) => (
            <li key={p.id} className="border-b border-slate-100 pb-2 last:border-0">
              {p.previous_rank} → <span className="font-medium">{p.new_rank}</span>{" "}
              <span className="text-slate-500">· effective {p.effective_date}</span>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function PerformanceCard({ officerId }: { officerId: string }) {
  const qc = useQueryClient();
  const key = ["hr-performance", officerId];
  const q = useList(key, () => hr.performance.list(officerId));
  const [form, setForm] = useState({ reviewer_id: "", period: "", score: "", comments: "" });
  const canWrite = hasPerm("hr.performance.write");

  return (
    <CardShell title="Performance reviews" fr="FR-HR-07 — periodic reviews with a 0–99.99 score.">
      {canWrite && (
        <AddForm
          title="Record review"
          openLabel="Record review"
          submitLabel="Record"
          service="hr-service"
          forbiddenHint="Needs hr.performance.write."
          successText={() => "Review recorded."}
          onSubmit={async () => {
            await hr.performance.create(officerId, {
              reviewer_id: form.reviewer_id.trim(),
              period: form.period.trim(),
              score: Number(form.score),
              comments: form.comments.trim() || null,
            });
            setForm({ reviewer_id: "", period: "", score: "", comments: "" });
            await qc.invalidateQueries({ queryKey: key });
          }}
        >
          {(fe) => (
            <>
              <TextInput label="Reviewer id" value={form.reviewer_id} onChange={(e) => setForm((f) => ({ ...f, reviewer_id: e.target.value }))} error={fe.reviewer_id} placeholder="officer id (uuid)" required />
              <TextInput label="Period" value={form.period} onChange={(e) => setForm((f) => ({ ...f, period: e.target.value }))} error={fe.period} placeholder="e.g. 2026-H1" required />
              <TextInput label="Score" type="number" step="0.01" min="0" max="99.99" value={form.score} onChange={(e) => setForm((f) => ({ ...f, score: e.target.value }))} error={fe.score} required />
              <TextInput label="Comments" value={form.comments} onChange={(e) => setForm((f) => ({ ...f, comments: e.target.value }))} error={fe.comments} placeholder="optional" />
            </>
          )}
        </AddForm>
      )}
      <ListState q={q} noun="performance reviews" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((r) => (
            <li key={r.id} className="border-b border-slate-100 pb-2 last:border-0">
              <span className="font-medium">{r.period}</span> — score {r.score}
              {r.comments && <div className="text-slate-600">{r.comments}</div>}
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function DisciplineCard({ officerId }: { officerId: string }) {
  const qc = useQueryClient();
  const key = ["hr-discipline", officerId];
  const q = useList(key, () => hr.discipline.list(officerId));
  const [form, setForm] = useState({ incident_date: "", description: "", outcome: "" });
  const canWrite = hasPerm("hr.discipline.write");

  return (
    <CardShell title="Discipline records" fr="FR-HR-06 — HR/command only (hr.discipline.read / write).">
      {canWrite && (
        <AddForm
          title="Record discipline case"
          openLabel="New record"
          submitLabel="Record"
          service="hr-service"
          forbiddenHint="Needs hr.discipline.write."
          successText={() => "Discipline record created."}
          onSubmit={async () => {
            await hr.discipline.create(officerId, {
              incident_date: form.incident_date,
              description: form.description.trim(),
              outcome: form.outcome.trim() || null,
            });
            setForm({ incident_date: "", description: "", outcome: "" });
            await qc.invalidateQueries({ queryKey: key });
          }}
        >
          {(fe) => (
            <>
              <DateField id="disc-date" label="Incident date" value={form.incident_date} onChange={(v) => setForm((f) => ({ ...f, incident_date: v }))} error={fe.incident_date} />
              <TextInput label="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} error={fe.description} required />
              <TextInput label="Outcome" value={form.outcome} onChange={(e) => setForm((f) => ({ ...f, outcome: e.target.value }))} error={fe.outcome} placeholder="optional" />
            </>
          )}
        </AddForm>
      )}
      <ListState q={q} noun="discipline records" />
      {q.data && q.data.length > 0 && (
        <ul className="flex flex-col gap-2 text-sm">
          {q.data.map((d) => (
            <li key={d.id} className="border-b border-slate-100 pb-2 last:border-0">
              <span className="text-slate-500">{d.incident_date}</span> — {d.description}
              {d.outcome && <div className="text-slate-600">Outcome: {d.outcome}</div>}
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "approved"
      ? "bg-emerald-100 text-emerald-700"
      : status === "rejected"
        ? "bg-rose-100 text-rose-700"
        : "bg-amber-100 text-amber-800";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{status}</span>;
}

function DateField({
  id,
  label,
  value,
  onChange,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
