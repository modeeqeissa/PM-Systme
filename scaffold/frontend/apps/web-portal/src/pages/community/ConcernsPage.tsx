import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, community, type Concern, type ConcernStatus } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

const STATUSES: ConcernStatus[] = ["open", "in_progress", "resolved"];
const STATUS_TONE: Record<ConcernStatus, string> = {
  open: "bg-amber-100 text-amber-800",
  in_progress: "bg-blue-100 text-blue-800",
  resolved: "bg-emerald-100 text-emerald-700",
};

export function ConcernsPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("community.write");
  const [statusFilter, setStatusFilter] = useState<ConcernStatus | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");

  const query = useQuery({
    queryKey: ["cm-concerns", statusFilter, categoryFilter],
    queryFn: () =>
      community.concerns.list({
        status: statusFilter || undefined,
        category: categoryFilter.trim() || undefined,
      }),
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
        <h1 className="text-xl font-semibold text-slate-900">Community concerns</h1>
        <p className="mb-6 text-sm text-slate-500">
          FR-COMM-02 — issues raised by the community, optionally tied to a meeting.
        </p>

        <Card className="mb-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label htmlFor="cn-status" className="text-sm font-medium text-slate-700">
                Status
              </label>
              <select
                id="cn-status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as ConcernStatus | "")}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
              >
                <option value="">Any status</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
            <TextInput
              label="Filter by category"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              placeholder="exact match, e.g. traffic"
            />
          </div>
        </Card>

        {canWrite && <NewConcernForm />}

        {query.isLoading && (
          <Card>
            <Spinner label="Loading concerns…" />
          </Card>
        )}
        {query.error instanceof ApiError && query.error.status === 403 && (
          <Alert variant="error">
            Your role can't view concerns (needs <code>community.read</code>).
          </Alert>
        )}
        {query.data && query.data.length === 0 && (
          <Card>
            <p className="text-sm text-slate-500">No concerns match.</p>
          </Card>
        )}
        <div className="flex flex-col gap-4">
          {(query.data ?? []).map((c) => (
            <ConcernRow key={c.id} concern={c} canWrite={canWrite} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ConcernRow({ concern, canWrite }: { concern: Concern; canWrite: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function setStatus(status: ConcernStatus) {
    setProblem(null);
    setBusy(true);
    try {
      await community.concerns.setStatus(concern.id, status);
      await qc.invalidateQueries({ queryKey: ["cm-concerns"] });
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
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <Link
            to={`/community/concerns/${concern.id}`}
            className="font-medium text-slate-900 underline decoration-slate-300 hover:decoration-slate-900"
          >
            {concern.category}
          </Link>
          <p className="mt-1 text-sm text-slate-600">{concern.description}</p>
          {concern.raised_by && (
            <p className="text-xs text-slate-500">raised by {concern.raised_by}</p>
          )}
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[concern.status]}`}>
          {concern.status.replace("_", " ")}
        </span>
      </div>
      {canWrite && (
        <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3 text-sm">
          <span className="text-slate-500">Set status:</span>
          {STATUSES.filter((s) => s !== concern.status).map((s) => (
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

function NewConcernForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ meeting_id: "", category: "", description: "", raised_by: "" });
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
      await community.concerns.create({
        meeting_id: form.meeting_id.trim() || null,
        category: form.category.trim(),
        description: form.description.trim(),
        raised_by: form.raised_by.trim() || null,
      });
      setDone(true);
      setForm({ meeting_id: "", category: "", description: "", raised_by: "" });
      await qc.invalidateQueries({ queryKey: ["cm-concerns"] });
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
        <h2 className="text-lg font-semibold text-slate-900">Log concern</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Log concern"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <ProblemAlert
            problem={problem}
            service="community-service"
            forbiddenHint="Your role can't log concerns (needs community.write)."
          />
          {done && <Alert variant="info">Concern logged.</Alert>}
          <TextInput label="Category" value={form.category} onChange={set("category")} error={fe.category} placeholder="e.g. traffic, noise" required />
          <div className="flex flex-col gap-1">
            <label htmlFor="cn-desc" className="text-sm font-medium text-slate-700">
              Description
            </label>
            <textarea
              id="cn-desc"
              value={form.description}
              onChange={set("description")}
              rows={3}
              required
              className={
                "rounded-md border px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 " +
                (fe.description ? "border-red-400" : "border-slate-300")
              }
            />
            {fe.description && <p className="text-xs text-red-600">{fe.description}</p>}
          </div>
          <TextInput label="Raised by" value={form.raised_by} onChange={set("raised_by")} error={fe.raised_by} placeholder="optional — community member's name" />
          <TextInput label="Meeting id" value={form.meeting_id} onChange={set("meeting_id")} error={fe.meeting_id} placeholder="optional — link to a meeting (uuid)" />
          <div>
            <Button type="submit" loading={busy}>
              Log concern
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
