import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, community, type FollowUpStatus } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, ProblemAlert, type Problem } from "../../lib/problem";

const TABS: { key: FollowUpStatus | "all"; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "overdue", label: "Overdue" },
  { key: "completed", label: "Completed" },
  { key: "all", label: "All" },
];
const TONE: Record<string, string> = {
  pending: "bg-warn/10 text-warn",
  overdue: "bg-bad/10 text-bad",
  completed: "bg-ok/10 text-ok",
};

export function FollowUpsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canWrite = hasPerm("community.write");
  const [tab, setTab] = useState<FollowUpStatus | "all">("pending");
  const [recompute, setRecompute] = useState<{ checked: number; updated: number } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState(false);

  const query = useQuery({
    queryKey: ["cm-followups-queue", tab],
    queryFn: () => community.followUps.list(tab === "all" ? {} : { status: tab }),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (query.error instanceof ApiError && query.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  async function runRecompute() {
    setProblem(null);
    setRecompute(null);
    setBusy(true);
    try {
      const res = await community.followUps.recompute();
      setRecompute(res);
      await qc.invalidateQueries({ queryKey: ["cm-followups-queue"] });
      setTab("overdue");
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
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-ink">Follow-up actions</h1>
            <p className="mb-4 text-sm text-ink-faint">
              FR-COMM-03/04 — the global queue. "Recompute overdue" flags every
              pending action past its due date; each flagged row notifies its
              assigned officer.
            </p>
          </div>
          {canWrite && (
            <Button onClick={runRecompute} loading={busy}>
              Recompute overdue
            </Button>
          )}
        </div>

        <div className="mb-3">
          <ProblemAlert
            problem={problem}
            service="community-service"
            forbiddenHint="Your role can't recompute (needs community.write)."
          />
        </div>
        {recompute && (
          <div className="mb-3">
            <Alert variant="info">
              Recompute done — checked {recompute.checked}, newly overdue {recompute.updated}.
            </Alert>
          </div>
        )}

        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                "rounded-full px-3 py-1 " +
                (tab === t.key ? "bg-surface-3 text-white" : "bg-surface-2 text-ink-muted")
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        <Card className="p-0">
          {query.isLoading && (
            <div className="p-6">
              <Spinner label="Loading…" />
            </div>
          )}
          {query.error instanceof ApiError && query.error.status === 403 && (
            <div className="p-6">
              <Alert variant="error">
                Your role can't view follow-up actions (needs <code>community.read</code>).
              </Alert>
            </div>
          )}
          {query.data && query.data.length === 0 && (
            <p className="p-6 text-sm text-ink-faint">Nothing in this bucket.</p>
          )}
          {query.data && query.data.length > 0 && (
            <ul className="divide-y divide-hair text-sm">
              {query.data.map((fu) => (
                <li key={fu.id} className="flex items-start justify-between px-6 py-3">
                  <div>
                    <Link
                      to={`/community/concerns/${fu.concern_id}`}
                      className="text-ink underline decoration-hair hover:decoration-accent-command"
                    >
                      {fu.description}
                    </Link>
                    <p className="text-ink-faint">
                      assigned <span className="font-mono text-xs">{fu.assigned_to.slice(0, 8)}…</span> · due {fu.due_date}
                    </p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[fu.status]}`}>
                    {fu.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
