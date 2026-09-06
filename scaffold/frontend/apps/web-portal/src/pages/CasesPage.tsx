import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Spinner } from "@pmp/ui";
import { NavBar } from "../components/NavBar";
import { ApiError, cases as casesApi, type Case } from "../lib/api";
import { currentClaims } from "../lib/auth";

const STATUS_LABEL: Record<Case["status"], string> = {
  open: "Open",
  investigating: "Investigating",
  referred_prosecution: "Referred — prosecution",
  closed: "Closed",
  suspended: "Suspended",
};

const STATUS_STYLE: Record<Case["status"], string> = {
  open: "bg-blue-100 text-blue-800",
  investigating: "bg-amber-100 text-amber-800",
  referred_prosecution: "bg-purple-100 text-purple-800",
  closed: "bg-slate-200 text-slate-700",
  suspended: "bg-rose-100 text-rose-800",
};

export function CasesPage() {
  const navigate = useNavigate();
  const claims = currentClaims();

  const query = useQuery({
    queryKey: ["cases"],
    queryFn: () => casesApi.list(),
    retry: (count, err) => !(err instanceof ApiError) && count < 2,
  });

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      navigate("/login", { replace: true });
    }
  }, [query.error, navigate]);

  const leadOfficer = (c: Case) =>
    claims && c.lead_officer_id === claims.sub
      ? `You (${claims.badge_number})`
      : `${c.lead_officer_id.slice(0, 8)}…`;

  return (
    <div className="pt-8">
      <NavBar />
      <div className="mx-auto max-w-4xl px-4 pb-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Cases</h1>
          {claims && (
            <p className="text-sm text-slate-500">
              Signed in as <span className="font-medium">{claims.badge_number}</span>
              {claims.roles.length > 0 && <> · {claims.roles.join(", ")}</>}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/incidents/new"
            className="inline-flex items-center justify-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700"
          >
            File incident
          </Link>
        </div>
      </div>

      <Card className="p-0">
        {query.isLoading && (
          <div className="p-6">
            <Spinner label="Loading cases…" />
          </div>
        )}

        {query.error && !(query.error instanceof ApiError && query.error.status === 401) && (
          <div className="p-6">
            <Alert variant="error">
              {query.error instanceof ApiError && query.error.status === 403
                ? "Your role can't view cases (needs the case.read permission)."
                : `Couldn't load cases: ${(query.error as Error).message}`}
            </Alert>
          </div>
        )}

        {query.data && query.data.length === 0 && (
          <div className="p-6 text-sm text-slate-500">
            No cases visible to you. Cases you lead (or all cases, with a supervisory
            role) will appear here.
          </div>
        )}

        {query.data && query.data.length > 0 && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-6 py-3 font-medium">Case number</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Lead officer</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-6 py-3 font-medium">
                    <Link
                      to={`/cases/${c.id}`}
                      className="text-slate-900 underline decoration-slate-300 hover:decoration-slate-900"
                    >
                      {c.case_number}
                    </Link>
                  </td>
                  <td className="px-6 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[c.status]}`}
                    >
                      {STATUS_LABEL[c.status]}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-slate-600">
                    {leadOfficer(c)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      </div>
    </div>
  );
}
