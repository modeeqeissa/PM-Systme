import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import {
  ApiError,
  community,
  type Concern,
  type FollowUpAction,
} from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

const FU_TONE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  overdue: "bg-rose-100 text-rose-700",
  completed: "bg-emerald-100 text-emerald-700",
};

export function ConcernDetailPage() {
  const { concernId = "" } = useParams();
  const navigate = useNavigate();
  const canWrite = hasPerm("community.write");

  const concernQuery = useQuery({
    queryKey: ["cm-concern", concernId],
    queryFn: () => community.concerns.get(concernId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const fuQuery = useQuery({
    queryKey: ["cm-followups", concernId],
    queryFn: () => community.followUps.forConcern(concernId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (concernQuery.error instanceof ApiError && concernQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <Link to="/community/concerns" className="mb-4 inline-block text-sm text-slate-500 underline">
          ← Back to concerns
        </Link>

        {concernQuery.isLoading && (
          <Card>
            <Spinner label="Loading concern…" />
          </Card>
        )}
        {concernQuery.error instanceof ApiError && concernQuery.error.status === 404 && (
          <Alert variant="error">No concern with that id.</Alert>
        )}
        {concernQuery.error instanceof ApiError && concernQuery.error.status === 403 && (
          <Alert variant="error">
            Your role can't view concerns (needs <code>community.read</code>).
          </Alert>
        )}

        {concernQuery.data && (
          <>
            <ConcernCard concern={concernQuery.data} canWrite={canWrite} />
            <Card>
              <h2 className="text-lg font-semibold text-slate-900">Follow-up actions</h2>
              <p className="mb-4 text-sm text-slate-500">
                FR-COMM-03 — assigned tasks against this concern. "Overdue" is set
                only by the recompute sweep (see the Follow-ups queue).
              </p>

              {canWrite && <NewFollowUpForm concernId={concernId} />}

              {fuQuery.isLoading && <Spinner label="Loading actions…" />}
              {fuQuery.error instanceof ApiError && fuQuery.error.status === 403 && (
                <Alert variant="error">Needs <code>community.read</code>.</Alert>
              )}
              {fuQuery.data && fuQuery.data.length === 0 && (
                <p className="text-sm text-slate-500">No follow-up actions yet.</p>
              )}
              <ul className="flex flex-col gap-3">
                {(fuQuery.data ?? []).map((fu) => (
                  <FollowUpRow key={fu.id} action={fu} concernId={concernId} canWrite={canWrite} />
                ))}
              </ul>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function ConcernCard({ concern, canWrite }: { concern: Concern; canWrite: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function setStatus(status: Concern["status"]) {
    setProblem(null);
    setBusy(true);
    try {
      await community.concerns.setStatus(concern.id, status);
      await qc.invalidateQueries({ queryKey: ["cm-concern", concern.id] });
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
          <h1 className="text-xl font-semibold text-slate-900">{concern.category}</h1>
          <p className="mt-1 text-sm text-slate-600">{concern.description}</p>
          {concern.raised_by && <p className="text-xs text-slate-500">raised by {concern.raised_by}</p>}
          {concern.meeting_id && (
            <p className="text-xs text-slate-500">
              from meeting <span className="font-mono">{concern.meeting_id.slice(0, 8)}…</span>
            </p>
          )}
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
          {concern.status.replace("_", " ")}
        </span>
      </div>
      {canWrite && (
        <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3 text-sm">
          <span className="text-slate-500">Set status:</span>
          {(["open", "in_progress", "resolved"] as const)
            .filter((s) => s !== concern.status)
            .map((s) => (
              <button
                key={s}
                disabled={busy}
                onClick={() => setStatus(s)}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200 disabled:opacity-50"
              >
                {s.replace("_", " ")}
              </button>
            ))}
        </div>
      )}
      <div className="mt-2">
        <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
      </div>
    </Card>
  );
}

function FollowUpRow({
  action,
  concernId,
  canWrite,
}: {
  action: FollowUpAction;
  concernId: string;
  canWrite: boolean;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function setStatus(status: "pending" | "completed") {
    setProblem(null);
    setBusy(true);
    try {
      await community.followUps.setStatus(action.id, status);
      await qc.invalidateQueries({ queryKey: ["cm-followups", concernId] });
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
    <li className="border-b border-slate-100 pb-3 text-sm last:border-0">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-900">{action.description}</p>
          <p className="text-slate-500">
            assigned <span className="font-mono text-xs">{action.assigned_to.slice(0, 8)}…</span> · due {action.due_date}
          </p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${FU_TONE[action.status]}`}>
          {action.status}
        </span>
      </div>
      {canWrite && action.status !== "completed" && (
        <div className="mt-2 flex gap-2">
          <button
            disabled={busy}
            onClick={() => setStatus("completed")}
            className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200 disabled:opacity-50"
          >
            mark completed
          </button>
          {action.status === "overdue" && (
            <button
              disabled={busy}
              onClick={() => setStatus("pending")}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200 disabled:opacity-50"
            >
              back to pending
            </button>
          )}
        </div>
      )}
      <div className="mt-2">
        <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
      </div>
    </li>
  );
}

function NewFollowUpForm({ concernId }: { concernId: string }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ description: "", assigned_to: "", due_date: "" });
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
      await community.followUps.create(concernId, {
        description: form.description.trim(),
        assigned_to: form.assigned_to.trim(),
        due_date: form.due_date,
      });
      setDone(true);
      setForm({ description: "", assigned_to: "", due_date: "" });
      await qc.invalidateQueries({ queryKey: ["cm-followups", concernId] });
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
    <div className="mb-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">Assign follow-up action</h3>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Assign action"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
          <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
          {done && <Alert variant="info">Follow-up action assigned.</Alert>}
          <TextInput label="Description" value={form.description} onChange={set("description")} error={fe.description} required />
          <TextInput label="Assigned to (officer id)" value={form.assigned_to} onChange={set("assigned_to")} error={fe.assigned_to} placeholder="uuid" required />
          <div className="flex flex-col gap-1">
            <label htmlFor="fu-due" className="text-sm font-medium text-slate-700">
              Due date
            </label>
            <input
              id="fu-due"
              type="date"
              value={form.due_date}
              onChange={set("due_date")}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            {fe.due_date && <p className="text-xs text-red-600">{fe.due_date}</p>}
          </div>
          <div>
            <Button type="submit" loading={busy}>
              Assign action
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
