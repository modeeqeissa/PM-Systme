import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import {
  ApiError,
  training,
  type Certification,
  type Course,
  type OfficerCertification,
} from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  expiring_soon: "bg-amber-100 text-amber-800",
  expired: "bg-rose-100 text-rose-700",
};

export function IssueCertificationPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("training.cert.write");

  const coursesQuery = useQuery({ queryKey: ["tr-courses"], queryFn: () => training.courses.list(), retry: false });
  const certsQuery = useQuery({ queryKey: ["tr-certifications"], queryFn: () => training.certifications.list(), retry: false });
  const recentQuery = useQuery({
    queryKey: ["tr-officer-certs-recent"],
    queryFn: () => training.officerCerts.list(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [form, setForm] = useState({ officer_id: "", certification_id: "", issued_date: "" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [issued, setIssued] = useState<OfficerCertification | null>(null);
  const fe = fieldErrors(problem);

  if (recentQuery.error instanceof ApiError && recentQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  const courseTitle = (certId: number) => {
    const cert = certsQuery.data?.find((c: Certification) => c.id === certId);
    const course = coursesQuery.data?.find((c: Course) => c.id === cert?.course_id);
    return course ? course.title : `certification #${certId}`;
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setIssued(null);
    setBusy(true);
    try {
      const rec = await training.officerCerts.issue({
        officer_id: form.officer_id.trim(),
        certification_id: Number(form.certification_id),
        issued_date: form.issued_date || undefined,
      });
      setIssued(rec);
      setForm({ officer_id: "", certification_id: "", issued_date: "" });
      await recentQuery.refetch();
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
        <h1 className="text-xl font-semibold text-slate-900">Issue certification</h1>
        <p className="mb-6 text-sm text-slate-500">
          FR-TRAIN-02 — issue a certification to an officer. The expiry date and
          status are computed by the server from the course's validity window.
        </p>

        {canWrite ? (
          <Card className="mb-6">
            <form onSubmit={submit} className="flex flex-col gap-3">
              <ProblemAlert
                problem={problem}
                service="training-service"
                forbiddenHint="Your role can't issue certifications (needs training.cert.write)."
              />
              {issued && (
                <Alert variant="info">
                  Issued to <span className="font-mono text-xs">{issued.officer_id}</span> —{" "}
                  {courseTitle(issued.certification_id)}. Expires{" "}
                  <span className="font-medium">{issued.expires_date}</span> ·{" "}
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[issued.status]}`}>
                    {issued.status}
                  </span>
                </Alert>
              )}
              <TextInput
                label="Officer id"
                value={form.officer_id}
                onChange={(e) => setForm((f) => ({ ...f, officer_id: e.target.value }))}
                error={fe.officer_id}
                placeholder="hr_db officers.id (uuid)"
                required
              />
              <div className="flex flex-col gap-1">
                <label htmlFor="issue-cert" className="text-sm font-medium text-slate-700">
                  Certification
                </label>
                {certsQuery.data && certsQuery.data.length > 0 ? (
                  <select
                    id="issue-cert"
                    value={form.certification_id}
                    onChange={(e) => setForm((f) => ({ ...f, certification_id: e.target.value }))}
                    required
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                  >
                    <option value="">Select…</option>
                    {certsQuery.data.map((c: Certification) => (
                      <option key={c.id} value={c.id}>
                        #{c.id} — {courseTitle(c.id)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="issue-cert"
                    type="number"
                    value={form.certification_id}
                    onChange={(e) => setForm((f) => ({ ...f, certification_id: e.target.value }))}
                    required
                    placeholder="certification id"
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                  />
                )}
                {fe.certification_id && <p className="text-xs text-red-600">{fe.certification_id}</p>}
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="issue-date" className="text-sm font-medium text-slate-700">
                  Issued date (optional — defaults to today)
                </label>
                <input
                  id="issue-date"
                  type="date"
                  value={form.issued_date}
                  onChange={(e) => setForm((f) => ({ ...f, issued_date: e.target.value }))}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
              <div>
                <Button type="submit" loading={busy}>
                  Issue certification
                </Button>
              </div>
            </form>
          </Card>
        ) : (
          <Alert variant="error">
            Your role can't issue certifications (needs <code>training.cert.write</code>).
          </Alert>
        )}

        <Card className="p-0">
          <h2 className="border-b border-slate-100 px-6 py-3 text-sm font-medium text-slate-700">
            Recently issued
          </h2>
          {recentQuery.isLoading && (
            <div className="p-6">
              <Spinner label="Loading…" />
            </div>
          )}
          {recentQuery.data && recentQuery.data.length === 0 && (
            <p className="p-6 text-sm text-slate-500">Nothing issued yet.</p>
          )}
          {recentQuery.data && recentQuery.data.length > 0 && (
            <ul className="divide-y divide-slate-100 text-sm">
              {recentQuery.data.slice(0, 25).map((oc) => (
                <li key={oc.id} className="flex items-center justify-between px-6 py-3">
                  <span>
                    <span className="font-mono text-xs">{oc.officer_id.slice(0, 8)}…</span> ·{" "}
                    {courseTitle(oc.certification_id)}
                  </span>
                  <span>
                    <span className="text-slate-500">exp {oc.expires_date} </span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[oc.status]}`}>
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
