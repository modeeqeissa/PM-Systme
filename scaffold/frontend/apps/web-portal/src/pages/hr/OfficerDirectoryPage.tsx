import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import {
  ApiError,
  hr,
  type Officer,
  type OfficerStatus,
} from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

const STATUSES: OfficerStatus[] = ["active", "on_leave", "suspended", "retired"];
const STATUS_LABEL: Record<OfficerStatus, string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  retired: "Retired",
};

export function OfficerDirectoryPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("hr.officer.write");

  const [statusFilter, setStatusFilter] = useState<OfficerStatus | "">("");
  const [unitFilter, setUnitFilter] = useState("");
  const [search, setSearch] = useState("");

  const unitsQuery = useQuery({
    queryKey: ["hr-units"],
    queryFn: () => hr.units.list(),
    retry: false,
  });

  const officersQuery = useQuery({
    queryKey: ["hr-officers", statusFilter, unitFilter],
    queryFn: () =>
      hr.officers.list({
        status: statusFilter || undefined,
        unit_id: unitFilter || undefined,
      }),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (officersQuery.error instanceof ApiError && officersQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  const unitName = (id: string) =>
    unitsQuery.data?.find((u) => u.id === id)?.name ?? `${id.slice(0, 8)}…`;

  const rows = useMemo(() => {
    const list = officersQuery.data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (o) =>
        o.badge_number.toLowerCase().includes(q) ||
        (o.rank ?? "").toLowerCase().includes(q),
    );
  }, [officersQuery.data, search]);

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-5xl px-4 pb-10">
        <h1 className="text-xl font-semibold text-ink">Officer directory</h1>
        <p className="mb-6 text-sm text-ink-faint">
          FR-HR-01 — the officer master roster. Filter by unit or status; search
          the current page by badge or rank.
        </p>

        <Card className="mb-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="dir-status" className="text-sm font-medium text-ink-muted">
                Status
              </label>
              <select
                id="dir-status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as OfficerStatus | "")}
                className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
              >
                <option value="">Any status</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="dir-unit" className="text-sm font-medium text-ink-muted">
                Unit
              </label>
              {unitsQuery.data && unitsQuery.data.length > 0 ? (
                <select
                  id="dir-unit"
                  value={unitFilter}
                  onChange={(e) => setUnitFilter(e.target.value)}
                  className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
                >
                  <option value="">Any unit</option>
                  {unitsQuery.data.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="dir-unit"
                  value={unitFilter}
                  onChange={(e) => setUnitFilter(e.target.value)}
                  placeholder="unit id (uuid)"
                  className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
                />
              )}
            </div>
            <TextInput
              label="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="badge or rank"
            />
          </div>
        </Card>

        {canWrite && <NewOfficerForm unitId={unitFilter} />}

        <Card className="p-0">
          {officersQuery.isLoading && (
            <div className="p-6">
              <Spinner label="Loading officers…" />
            </div>
          )}
          {officersQuery.error instanceof ApiError && officersQuery.error.status === 403 && (
            <div className="p-6">
              <Alert variant="error">
                Your role can't view officers (needs <code>hr.officer.read</code>).
              </Alert>
            </div>
          )}
          {officersQuery.data && rows.length === 0 && (
            <p className="p-6 text-sm text-ink-faint">No officers match.</p>
          )}
          {rows.length > 0 && (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-hair text-xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="px-6 py-3 font-medium">Badge</th>
                  <th className="px-6 py-3 font-medium">Rank</th>
                  <th className="px-6 py-3 font-medium">Unit</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id} className="border-b border-hair last:border-0">
                    <td className="px-6 py-3 font-medium">
                      <Link
                        to={`/hr/officers/${o.id}`}
                        className="text-ink underline decoration-hair hover:decoration-accent-command"
                      >
                        {o.badge_number}
                      </Link>
                    </td>
                    <td className="px-6 py-3">{o.rank}</td>
                    <td className="px-6 py-3">{unitName(o.unit_id)}</td>
                    <td className="px-6 py-3">
                      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-muted">
                        {STATUS_LABEL[o.status]}
                      </span>
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

function NewOfficerForm({ unitId }: { unitId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    user_id: "",
    badge_number: "",
    rank: "",
    unit_id: unitId,
    hire_date: "",
  });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [created, setCreated] = useState<Officer | null>(null);
  const fe = fieldErrors(problem);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setCreated(null);
    setBusy(true);
    try {
      const officer = await hr.officers.create({
        user_id: form.user_id.trim(),
        badge_number: form.badge_number.trim(),
        rank: form.rank.trim(),
        unit_id: form.unit_id.trim(),
        hire_date: form.hire_date,
      });
      setCreated(officer);
      setForm({ user_id: "", badge_number: "", rank: "", unit_id: unitId, hire_date: "" });
      await queryClient.invalidateQueries({ queryKey: ["hr-officers"] });
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
        <h2 className="text-lg font-semibold text-ink">New officer</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Add officer"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-4">
          <p className="text-sm text-ink-faint">
            FR-HR-01/02 — creates the profile and opens the first assignment at
            the unit below.
          </p>
          <div className="mb-2">
            <ProblemAlert
              problem={problem}
              service="hr-service"
              forbiddenHint="Your role can't create officers (needs hr.officer.write)."
            />
          </div>
          {created && (
            <Alert variant="info">
              Created officer <code>{created.badge_number}</code> ({created.id}).
            </Alert>
          )}
          <TextInput label="User id" value={form.user_id} onChange={set("user_id")} error={fe.user_id} placeholder="identity_db users.id (uuid)" required />
          <TextInput label="Badge number" value={form.badge_number} onChange={set("badge_number")} error={fe.badge_number} required />
          <TextInput label="Rank" value={form.rank} onChange={set("rank")} error={fe.rank} placeholder="e.g. Sergeant" required />
          <TextInput label="Unit id" value={form.unit_id} onChange={set("unit_id")} error={fe.unit_id} placeholder="uuid" required />
          <div className="flex flex-col gap-1">
            <label htmlFor="new-off-hire" className="text-sm font-medium text-ink-muted">
              Hire date
            </label>
            <input
              id="new-off-hire"
              type="date"
              value={form.hire_date}
              onChange={set("hire_date")}
              required
              className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
            />
            {fe.hire_date && <p className="text-xs text-bad">{fe.hire_date}</p>}
          </div>
          <div>
            <Button type="submit" loading={busy}>
              Create officer
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
