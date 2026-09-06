import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, training, type CertStatus } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, ProblemAlert, type Problem } from "../../lib/problem";

const TABS: { key: CertStatus | "all"; label: string }[] = [
  { key: "expiring_soon", label: "Expiring soon" },
  { key: "expired", label: "Expired" },
  { key: "active", label: "Active" },
  { key: "all", label: "All" },
];
const TONE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  expiring_soon: "bg-amber-100 text-amber-800",
  expired: "bg-rose-100 text-rose-700",
};

export function CompliancePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canWrite = hasPerm("training.cert.write");
  const [tab, setTab] = useState<CertStatus | "all">("expiring_soon");
  const [recompute, setRecompute] = useState<{ checked: number; updated: number } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState(false);

  const query = useQuery({
    queryKey: ["tr-compliance", tab],
    queryFn: () => training.officerCerts.list(tab === "all" ? {} : { status: tab }),
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
      const res = await training.officerCerts.recompute();
      setRecompute(res);
      await qc.invalidateQueries({ queryKey: ["tr-compliance"] });
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
            <h1 className="text-xl font-semibold text-slate-900">Certification compliance</h1>
            <p className="mb-4 text-sm text-slate-500">
              FR-TRAIN-03/04 — issued certifications by expiry status. Statuses are
              recomputed on a background sweep; run it on demand below.
            </p>
          </div>
          {canWrite && (
            <Button onClick={runRecompute} loading={busy}>
              Recompute status
            </Button>
          )}
        </div>

        <div className="mb-3">
          <ProblemAlert
            problem={problem}
            service="training-service"
            forbiddenHint="Your role can't recompute (needs training.cert.write)."
          />
        </div>
        {recompute && (
          <div className="mb-3">
            <Alert variant="info">
              Recompute done — checked {recompute.checked}, updated {recompute.updated}.
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
                (tab === t.key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600")
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
                Your role can't view compliance (needs <code>training.cert.read</code>).
              </Alert>
            </div>
          )}
          {query.data && query.data.length === 0 && (
            <p className="p-6 text-sm text-slate-500">Nothing in this bucket.</p>
          )}
          {query.data && query.data.length > 0 && (
            <ul className="divide-y divide-slate-100 text-sm">
              {query.data.map((oc) => (
                <li key={oc.id} className="flex items-center justify-between px-6 py-3">
                  <span className="font-mono text-xs">{oc.officer_id}</span>
                  <span>
                    <span className="text-slate-500">issued {oc.issued_date} · exp {oc.expires_date} </span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[oc.status]}`}>
                      {oc.status}
                    </span>
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
