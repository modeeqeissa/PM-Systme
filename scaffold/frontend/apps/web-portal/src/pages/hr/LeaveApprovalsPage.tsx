import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, hr, type LeaveRequest } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

export function LeaveApprovalsPage() {
  const navigate = useNavigate();
  const canApprove = hasPerm("hr.leave.approve");
  const [tab, setTab] = useState<"pending" | "approved" | "rejected">("pending");

  const query = useQuery({
    queryKey: ["hr-leave-queue", tab],
    queryFn: () => hr.leave.queue(tab),
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
        <h1 className="text-xl font-semibold text-slate-900">Leave approvals</h1>
        <p className="mb-6 text-sm text-slate-500">
          FR-HR-05 — leave requests routed to supervisors/commanders.
        </p>

        <div className="mb-4 flex gap-2 text-sm">
          {(["pending", "approved", "rejected"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setTab(s)}
              className={
                "rounded-full px-3 py-1 capitalize " +
                (tab === s ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600")
              }
            >
              {s}
            </button>
          ))}
        </div>

        {query.isLoading && (
          <Card>
            <Spinner label="Loading leave requests…" />
          </Card>
        )}
        {query.error instanceof ApiError && query.error.status === 403 && (
          <Alert variant="error">
            Your role can't view the leave queue (needs <code>hr.leave.read</code>).
          </Alert>
        )}
        {query.data && query.data.length === 0 && (
          <Card>
            <p className="text-sm text-slate-500">No {tab} leave requests.</p>
          </Card>
        )}
        {query.data && query.data.length > 0 && (
          <div className="flex flex-col gap-4">
            {query.data.map((l) => (
              <LeaveRow key={l.id} leave={l} canApprove={canApprove && tab === "pending"} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LeaveRow({ leave, canApprove }: { leave: LeaveRequest; canApprove: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [approvedBy, setApprovedBy] = useState("");
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const fe = fieldErrors(problem);

  async function decide(status: "approved" | "rejected") {
    setProblem(null);
    setBusy(status);
    try {
      await hr.leave.decide(leave.id, {
        status,
        approved_by: status === "approved" ? approvedBy.trim() : undefined,
      });
      await qc.invalidateQueries({ queryKey: ["hr-leave-queue"] });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate("/login", { replace: true });
        return;
      }
      setProblem(classify(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between text-sm">
        <div>
          <div className="text-slate-900">
            Officer <span className="font-mono text-xs">{leave.officer_id.slice(0, 8)}…</span> ·{" "}
            <span className="capitalize">{leave.leave_type}</span>
          </div>
          <div className="text-slate-500">
            {leave.start_date} → {leave.end_date}
          </div>
        </div>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
          {leave.status}
        </span>
      </div>

      {canApprove && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          {!open ? (
            <Button variant="secondary" onClick={() => setOpen(true)}>
              Review
            </Button>
          ) : (
            <div className="flex flex-col gap-3">
              <ProblemAlert
                problem={problem}
                service="hr-service"
                forbiddenHint="Your role can't approve leave (needs hr.leave.approve)."
              />
              <TextInput
                label="Approved by (officer id)"
                value={approvedBy}
                onChange={(e) => setApprovedBy(e.target.value)}
                error={fe.approved_by}
                placeholder="required to approve"
              />
              <div className="flex gap-2">
                <Button onClick={() => decide("approved")} loading={busy === "approved"}>
                  Approve
                </Button>
                <Button variant="secondary" onClick={() => decide("rejected")} loading={busy === "rejected"}>
                  Reject
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
