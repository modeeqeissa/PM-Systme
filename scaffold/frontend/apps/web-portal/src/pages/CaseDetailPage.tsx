import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import {
  ApiError,
  cases as casesApi,
  evidence as evidenceApi,
  validationErrors,
  type Arrest,
  type CaseOfficer,
  type CourtProceeding,
  type CustodyEvent,
  type EvidenceItem,
  type HashVerification,
  type PartyType,
  type Statement,
} from "../lib/api";
import { currentClaims } from "../lib/auth";
import { localInputToIso, toLocalInputValue } from "../lib/datetime";

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  investigating: "Investigating",
  referred_prosecution: "Referred — prosecution",
  closed: "Closed",
  suspended: "Suspended",
};

const PARTY_TYPE_LABEL: Record<PartyType, string> = {
  witness: "Witness",
  suspect: "Suspect",
  victim: "Victim",
};

type Problem =
  | { kind: "validation"; fields: Record<string, string> }
  | { kind: "forbidden" }
  | { kind: "network" }
  | { kind: "other"; message: string };

function classify(err: unknown): Problem {
  if (err instanceof ApiError) {
    if (err.status === 422) return { kind: "validation", fields: validationErrors(err) };
    if (err.status === 403) return { kind: "forbidden" };
    return { kind: "other", message: err.message };
  }
  return { kind: "network" };
}

export function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [items, setItems] = useState<EvidenceItem[]>([]);

  if (query.error instanceof ApiError && query.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Link to="/cases" className="mb-4 inline-block text-sm text-ink-faint underline">
        ← Back to cases
      </Link>

      {query.isLoading && (
        <Card>
          <Spinner label="Loading case…" />
        </Card>
      )}

      {query.error instanceof ApiError && query.error.status === 403 && (
        <Alert variant="error">
          Your role can't view this case (needs the <code>case.read</code> permission).
        </Alert>
      )}
      {query.error instanceof ApiError && query.error.status === 404 && (
        <Alert variant="error">No case with that id.</Alert>
      )}

      {query.data && (
        <>
          <Card className="mb-6">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-xl font-semibold text-ink">
                  {query.data.case_number}
                </h1>
                <p className="mt-1 text-sm text-ink-faint">
                  Lead officer:{" "}
                  <span className="font-mono text-xs">{query.data.lead_officer_id}</span>
                </p>
                <p className="text-sm text-ink-faint">
                  Opened {new Date(query.data.opened_at).toLocaleString()}
                  {query.data.closed_at &&
                    ` · Closed ${new Date(query.data.closed_at).toLocaleString()}`}
                </p>
              </div>
              <span className="rounded-full bg-surface-2 px-3 py-1 text-xs font-medium text-ink-muted">
                {STATUS_LABEL[query.data.status] ?? query.data.status}
              </span>
            </div>
          </Card>

          <AssignedOfficersSection caseId={query.data.id} />

          <ArrestsSection caseId={query.data.id} />

          <StatementsSection caseId={query.data.id} />

          <CourtProceedingsSection caseId={query.data.id} />

          <AddEvidenceForm
            caseId={query.data.id}
            onCreated={(item) => setItems((prev) => [item, ...prev])}
          />

          {items.length > 0 && (
            <div className="mt-6 flex flex-col gap-6">
              {items.map((item) => (
                <EvidenceCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// --- Assigned officers (FR-CASE-07) -------------------------------------
function AssignedOfficersSection({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const officersQuery = useQuery({
    queryKey: ["case-officers", caseId],
    queryFn: () => casesApi.officers(caseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [officerId, setOfficerId] = useState("");
  const [roleOnCase, setRoleOnCase] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const fieldErr = problem?.kind === "validation" ? problem.fields : {};

  if (officersQuery.error instanceof ApiError && officersQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setBusy(true);
    try {
      await casesApi.assignOfficer(caseId, {
        officer_id: officerId.trim(),
        role_on_case: roleOnCase.trim(),
      });
      await queryClient.invalidateQueries({ queryKey: ["case-officers", caseId] });
      setOfficerId("");
      setRoleOnCase("");
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

  async function unassign(id: string) {
    setProblem(null);
    setRemovingId(id);
    try {
      await casesApi.unassignOfficer(caseId, id);
      await queryClient.invalidateQueries({ queryKey: ["case-officers", caseId] });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate("/login", { replace: true });
        return;
      }
      setProblem(classify(err));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-ink">Assigned officers</h2>
      <p className="mb-4 text-sm text-ink-faint">
        FR-CASE-07 — assigns a supporting officer to this case; publishes a{" "}
        <code>CaseOfficerAssigned</code> event that notifies the officer.
        Requires the <code>case.approve</code> permission.
      </p>

      {problem?.kind === "forbidden" && (
        <div className="mb-4">
          <Alert variant="error">
            Your role can't change case staffing. This needs the{" "}
            <code>case.approve</code> permission.
          </Alert>
        </div>
      )}
      {problem?.kind === "network" && (
        <div className="mb-4">
          <Alert variant="error">Couldn't reach case-service. Try again.</Alert>
        </div>
      )}
      {problem?.kind === "other" && (
        <div className="mb-4">
          <Alert variant="error">{problem.message}</Alert>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextInput
          label="Officer id"
          value={officerId}
          onChange={(e) => setOfficerId(e.target.value)}
          error={fieldErr.officer_id}
          placeholder="uuid"
          required
        />
        <TextInput
          label="Role on case"
          value={roleOnCase}
          onChange={(e) => setRoleOnCase(e.target.value)}
          error={fieldErr.role_on_case}
          placeholder="e.g. lead, support, forensic liaison"
          maxLength={30}
          required
        />
        <div>
          <Button type="submit" loading={busy}>
            Assign officer
          </Button>
        </div>
      </form>

      <h3 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Currently assigned
      </h3>
      {officersQuery.isLoading && <Spinner label="Loading assigned officers…" />}
      {officersQuery.error instanceof ApiError && officersQuery.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>case.read</code> permission to view assigned officers.
        </Alert>
      )}
      {officersQuery.data && officersQuery.data.length === 0 && (
        <p className="text-sm text-ink-faint">No supporting officers assigned yet.</p>
      )}
      {officersQuery.data && officersQuery.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {officersQuery.data.map((o: CaseOfficer) => (
            <li
              key={o.officer_id}
              className="flex items-center justify-between border-b border-hair pb-2 text-sm last:border-0"
            >
              <span>
                <span className="font-mono text-xs">{o.officer_id}</span>
                <span className="ml-2 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-muted">
                  {o.role_on_case}
                </span>
              </span>
              <Button
                variant="secondary"
                onClick={() => unassign(o.officer_id)}
                loading={removingId === o.officer_id}
              >
                Unassign
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Record arrest -------------------------------------------------------
function ArrestsSection({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const claims = currentClaims();
  const queryClient = useQueryClient();

  const arrestsQuery = useQuery({
    queryKey: ["arrests", caseId],
    queryFn: () => casesApi.arrests(caseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [suspectId, setSuspectId] = useState("");
  const [arrestDate, setArrestDate] = useState(() => toLocalInputValue(new Date()));
  const [location, setLocation] = useState("");
  const [legalBasis, setLegalBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [justAdded, setJustAdded] = useState<Arrest | null>(null);

  const fieldErr = problem?.kind === "validation" ? problem.fields : {};

  if (arrestsQuery.error instanceof ApiError && arrestsQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setProblem(null);
    setJustAdded(null);
    setBusy(true);
    try {
      const arrest = await casesApi.recordArrest(caseId, {
        officer_id: claims.sub,
        suspect_id: suspectId.trim(),
        arrest_date: localInputToIso(arrestDate),
        location: location.trim() || null,
        legal_basis: legalBasis.trim() || null,
      });
      setJustAdded(arrest);
      queryClient.setQueryData<Arrest[]>(["arrests", caseId], (prev) => [
        arrest,
        ...(prev ?? []),
      ]);
      setSuspectId("");
      setArrestDate(toLocalInputValue(new Date()));
      setLocation("");
      setLegalBasis("");
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
      <h2 className="text-lg font-semibold text-ink">Record arrest</h2>
      <p className="mb-4 text-sm text-ink-faint">
        FR-CASE-04 — records an arrest against this case; publishes an{" "}
        <code>ArrestRecorded</code> event that feeds the dashboard's{" "}
        <code>arrests_recorded</code> KPI.
      </p>

      {problem?.kind === "forbidden" && (
        <div className="mb-4">
          <Alert variant="error">
            Your role can't record an arrest. This needs the{" "}
            <code>case.write</code> permission.
          </Alert>
        </div>
      )}
      {problem?.kind === "network" && (
        <div className="mb-4">
          <Alert variant="error">Couldn't reach case-service. Try again.</Alert>
        </div>
      )}
      {problem?.kind === "other" && (
        <div className="mb-4">
          <Alert variant="error">{problem.message}</Alert>
        </div>
      )}
      {justAdded && (
        <div className="mb-4">
          <Alert variant="info">
            Arrest recorded — id <code>{justAdded.id}</code>.
          </Alert>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextInput
          label="Suspect id"
          value={suspectId}
          onChange={(e) => setSuspectId(e.target.value)}
          error={fieldErr.suspect_id}
          placeholder="uuid"
          required
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="arrest-date" className="text-sm font-medium text-ink-muted">
            Arrest date
          </label>
          <input
            id="arrest-date"
            type="datetime-local"
            value={arrestDate}
            onChange={(e) => setArrestDate(e.target.value)}
            required
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
        </div>
        <TextInput
          label="Location"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          error={fieldErr.location}
          placeholder="optional"
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="legal-basis" className="text-sm font-medium text-ink-muted">
            Legal basis
          </label>
          <textarea
            id="legal-basis"
            value={legalBasis}
            onChange={(e) => setLegalBasis(e.target.value)}
            rows={2}
            placeholder="optional"
            className={
              "rounded-md border px-3 py-2 text-sm text-ink shadow-sm " +
              "focus:outline-none focus:ring-2 focus:ring-accent-command/50 " +
              (fieldErr.legal_basis ? "border-bad/30" : "border-hair")
            }
          />
          {fieldErr.legal_basis && (
            <p className="text-xs text-bad">{fieldErr.legal_basis}</p>
          )}
        </div>
        <div>
          <Button type="submit" loading={busy}>
            Record arrest
          </Button>
        </div>
      </form>

      <h3 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Arrests
      </h3>
      {arrestsQuery.isLoading && <Spinner label="Loading arrests…" />}
      {arrestsQuery.error instanceof ApiError && arrestsQuery.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>case.read</code> permission to view arrests.
        </Alert>
      )}
      {arrestsQuery.data && arrestsQuery.data.length === 0 && (
        <p className="text-sm text-ink-faint">No arrests recorded yet.</p>
      )}
      {arrestsQuery.data && arrestsQuery.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {arrestsQuery.data.map((a) => (
            <li key={a.id} className="border-b border-hair pb-2 text-sm last:border-0">
              <div className="text-ink">
                Suspect <span className="font-mono text-xs">{a.suspect_id}</span>
              </div>
              <div className="text-ink-faint">
                {new Date(a.arrest_date).toLocaleString()}
                {a.location && ` · ${a.location}`}
              </div>
              {a.legal_basis && <div className="text-ink-muted">{a.legal_basis}</div>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Record statement -----------------------------------------------------
function StatementsSection({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const claims = currentClaims();
  const queryClient = useQueryClient();

  const statementsQuery = useQuery({
    queryKey: ["statements", caseId],
    queryFn: () => casesApi.statements(caseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [partyType, setPartyType] = useState<PartyType>("witness");
  const [statementText, setStatementText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [justAdded, setJustAdded] = useState<Statement | null>(null);

  const fieldErr = problem?.kind === "validation" ? problem.fields : {};

  if (statementsQuery.error instanceof ApiError && statementsQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setProblem(null);
    setJustAdded(null);
    setBusy(true);
    try {
      const statement = await casesApi.recordStatement(caseId, {
        recorded_by: claims.sub,
        party_type: partyType,
        statement_text: statementText.trim(),
      });
      setJustAdded(statement);
      queryClient.setQueryData<Statement[]>(["statements", caseId], (prev) => [
        statement,
        ...(prev ?? []),
      ]);
      setPartyType("witness");
      setStatementText("");
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
      <h2 className="text-lg font-semibold text-ink">Record statement</h2>
      <p className="mb-4 text-sm text-ink-faint">
        FR-CASE-05 — records a witness, suspect, or victim statement against this case.
      </p>

      {problem?.kind === "forbidden" && (
        <div className="mb-4">
          <Alert variant="error">
            Your role can't record a statement. This needs the{" "}
            <code>case.write</code> permission.
          </Alert>
        </div>
      )}
      {problem?.kind === "network" && (
        <div className="mb-4">
          <Alert variant="error">Couldn't reach case-service. Try again.</Alert>
        </div>
      )}
      {problem?.kind === "other" && (
        <div className="mb-4">
          <Alert variant="error">{problem.message}</Alert>
        </div>
      )}
      {justAdded && (
        <div className="mb-4">
          <Alert variant="info">
            Statement recorded — id <code>{justAdded.id}</code>.
          </Alert>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="statement-party-type" className="text-sm font-medium text-ink-muted">
            Party type
          </label>
          <select
            id="statement-party-type"
            value={partyType}
            onChange={(e) => setPartyType(e.target.value as PartyType)}
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          >
            <option value="witness">Witness</option>
            <option value="suspect">Suspect</option>
            <option value="victim">Victim</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="statement-text" className="text-sm font-medium text-ink-muted">
            Statement
          </label>
          <textarea
            id="statement-text"
            value={statementText}
            onChange={(e) => setStatementText(e.target.value)}
            rows={4}
            required
            className={
              "rounded-md border px-3 py-2 text-sm text-ink shadow-sm " +
              "focus:outline-none focus:ring-2 focus:ring-accent-command/50 " +
              (fieldErr.statement_text ? "border-bad/30" : "border-hair")
            }
          />
          {fieldErr.statement_text && (
            <p className="text-xs text-bad">{fieldErr.statement_text}</p>
          )}
        </div>
        <div>
          <Button type="submit" loading={busy}>
            Record statement
          </Button>
        </div>
      </form>

      <h3 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Statements
      </h3>
      {statementsQuery.isLoading && <Spinner label="Loading statements…" />}
      {statementsQuery.error instanceof ApiError && statementsQuery.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>case.read</code> permission to view statements.
        </Alert>
      )}
      {statementsQuery.data && statementsQuery.data.length === 0 && (
        <p className="text-sm text-ink-faint">No statements recorded yet.</p>
      )}
      {statementsQuery.data && statementsQuery.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {statementsQuery.data.map((s) => (
            <li key={s.id} className="border-b border-hair pb-2 text-sm last:border-0">
              <div className="text-ink">
                {PARTY_TYPE_LABEL[s.party_type]}{" "}
                <span className="text-ink-faint">
                  — recorded by{" "}
                  <span className="font-mono text-xs">{s.recorded_by}</span>
                  {" · "}
                  {new Date(s.recorded_at).toLocaleString()}
                </span>
              </div>
              <div className="text-ink-muted">{s.statement_text}</div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Record court proceeding ----------------------------------------------
function CourtProceedingsSection({ caseId }: { caseId: string }) {
  const navigate = useNavigate();
  const claims = currentClaims();
  const queryClient = useQueryClient();

  const proceedingsQuery = useQuery({
    queryKey: ["court-proceedings", caseId],
    queryFn: () => casesApi.courtProceedings(caseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [hearingDate, setHearingDate] = useState(() => toLocalInputValue(new Date()));
  const [courtName, setCourtName] = useState("");
  const [verdict, setVerdict] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [justAdded, setJustAdded] = useState<CourtProceeding | null>(null);

  const fieldErr = problem?.kind === "validation" ? problem.fields : {};

  if (
    proceedingsQuery.error instanceof ApiError &&
    proceedingsQuery.error.status === 401
  ) {
    navigate("/login", { replace: true });
    return null;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setProblem(null);
    setJustAdded(null);
    setBusy(true);
    try {
      const proceeding = await casesApi.recordCourtProceeding(caseId, {
        hearing_date: localInputToIso(hearingDate),
        court_name: courtName.trim() || null,
        verdict: verdict.trim() || null,
        notes: notes.trim() || null,
      });
      setJustAdded(proceeding);
      queryClient.setQueryData<CourtProceeding[]>(
        ["court-proceedings", caseId],
        (prev) => [proceeding, ...(prev ?? [])],
      );
      setHearingDate(toLocalInputValue(new Date()));
      setCourtName("");
      setVerdict("");
      setNotes("");
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
      <h2 className="text-lg font-semibold text-ink">Record court proceeding</h2>
      <p className="mb-4 text-sm text-ink-faint">
        FR-CASE-06 — records a hearing against this case.
      </p>

      {problem?.kind === "forbidden" && (
        <div className="mb-4">
          <Alert variant="error">
            Your role can't record a court proceeding. This needs the{" "}
            <code>case.write</code> permission.
          </Alert>
        </div>
      )}
      {problem?.kind === "network" && (
        <div className="mb-4">
          <Alert variant="error">Couldn't reach case-service. Try again.</Alert>
        </div>
      )}
      {problem?.kind === "other" && (
        <div className="mb-4">
          <Alert variant="error">{problem.message}</Alert>
        </div>
      )}
      {justAdded && (
        <div className="mb-4">
          <Alert variant="info">
            Court proceeding recorded — id <code>{justAdded.id}</code>.
          </Alert>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="hearing-date" className="text-sm font-medium text-ink-muted">
            Hearing date
          </label>
          <input
            id="hearing-date"
            type="datetime-local"
            value={hearingDate}
            onChange={(e) => setHearingDate(e.target.value)}
            required
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
        </div>
        <TextInput
          label="Court name"
          value={courtName}
          onChange={(e) => setCourtName(e.target.value)}
          error={fieldErr.court_name}
          placeholder="optional"
        />
        <TextInput
          label="Verdict"
          value={verdict}
          onChange={(e) => setVerdict(e.target.value)}
          error={fieldErr.verdict}
          placeholder="optional — once decided"
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="proceeding-notes" className="text-sm font-medium text-ink-muted">
            Notes
          </label>
          <textarea
            id="proceeding-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="optional"
            className={
              "rounded-md border px-3 py-2 text-sm text-ink shadow-sm " +
              "focus:outline-none focus:ring-2 focus:ring-accent-command/50 " +
              (fieldErr.notes ? "border-bad/30" : "border-hair")
            }
          />
          {fieldErr.notes && <p className="text-xs text-bad">{fieldErr.notes}</p>}
        </div>
        <div>
          <Button type="submit" loading={busy}>
            Record court proceeding
          </Button>
        </div>
      </form>

      <h3 className="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Court proceedings
      </h3>
      {proceedingsQuery.isLoading && <Spinner label="Loading court proceedings…" />}
      {proceedingsQuery.error instanceof ApiError && proceedingsQuery.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>case.read</code> permission to view court proceedings.
        </Alert>
      )}
      {proceedingsQuery.data && proceedingsQuery.data.length === 0 && (
        <p className="text-sm text-ink-faint">No court proceedings recorded yet.</p>
      )}
      {proceedingsQuery.data && proceedingsQuery.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {proceedingsQuery.data.map((p) => (
            <li key={p.id} className="border-b border-hair pb-2 text-sm last:border-0">
              <div className="text-ink">
                {new Date(p.hearing_date).toLocaleString()}
                {p.court_name && (
                  <>
                    {" · "}
                    <span className="font-medium">{p.court_name}</span>
                  </>
                )}
              </div>
              {p.verdict && (
                <div className="text-ink-muted">
                  Verdict: <span className="font-medium">{p.verdict}</span>
                </div>
              )}
              {p.notes && <div className="text-ink-faint">{p.notes}</div>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// --- Add evidence -----------------------------------------------------
function AddEvidenceForm({
  caseId,
  onCreated,
}: {
  caseId: string;
  onCreated: (item: EvidenceItem) => void;
}) {
  const navigate = useNavigate();
  const claims = currentClaims();
  const fileRef = useRef<HTMLInputElement>(null);

  const [itemType, setItemType] = useState("");
  const [description, setDescription] = useState("");
  const [collectedAt, setCollectedAt] = useState(() => toLocalInputValue(new Date()));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [justAdded, setJustAdded] = useState<EvidenceItem | null>(null);

  const fieldErr = problem?.kind === "validation" ? problem.fields : {};

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    setProblem(null);
    setJustAdded(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.set("case_id", caseId);
      form.set("item_type", itemType.trim());
      form.set("description", description.trim());
      form.set("collected_by", claims.sub);
      form.set("collected_at", localInputToIso(collectedAt));
      const file = fileRef.current?.files?.[0];
      if (file) form.set("file", file);

      const item = await evidenceApi.create(form);
      setJustAdded(item);
      onCreated(item);
      setItemType("");
      setDescription("");
      setCollectedAt(toLocalInputValue(new Date()));
      if (fileRef.current) fileRef.current.value = "";
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
      <h2 className="text-lg font-semibold text-ink">Add evidence</h2>
      <p className="mb-4 text-sm text-ink-faint">
        FR-EVID-01/02 — a digital file is SHA-256 hashed and stored encrypted; a{" "}
        <code>collected</code> custody event is recorded automatically.
      </p>

      {problem?.kind === "forbidden" && (
        <div className="mb-4">
          <Alert variant="error">
            Your role can't log evidence. This needs the{" "}
            <code>evidence.vault.write</code> permission.
          </Alert>
        </div>
      )}
      {problem?.kind === "network" && (
        <div className="mb-4">
          <Alert variant="error">Couldn't reach evidence-service. Try again.</Alert>
        </div>
      )}
      {problem?.kind === "other" && (
        <div className="mb-4">
          <Alert variant="error">{problem.message}</Alert>
        </div>
      )}
      {justAdded && (
        <div className="mb-4">
          <Alert variant="info">
            Logged {justAdded.item_type} — id <code>{justAdded.id}</code>.
          </Alert>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextInput
          label="Item type"
          value={itemType}
          onChange={(e) => setItemType(e.target.value)}
          error={fieldErr.item_type}
          placeholder="e.g. physical, digital_file, photograph, weapon"
          maxLength={50}
          required
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="ev-desc" className="text-sm font-medium text-ink-muted">
            Description
          </label>
          <textarea
            id="ev-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            required
            className={
              "rounded-md border px-3 py-2 text-sm text-ink shadow-sm " +
              "focus:outline-none focus:ring-2 focus:ring-accent-command/50 " +
              (fieldErr.description ? "border-bad/30" : "border-hair")
            }
          />
          {fieldErr.description && (
            <p className="text-xs text-bad">{fieldErr.description}</p>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="ev-file" className="text-sm font-medium text-ink-muted">
            File (optional — omit for a physical item)
          </label>
          <input
            id="ev-file"
            ref={fileRef}
            type="file"
            className="text-sm text-ink-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-surface-2"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="ev-collected-at" className="text-sm font-medium text-ink-muted">
            Collected at
          </label>
          <input
            id="ev-collected-at"
            type="datetime-local"
            value={collectedAt}
            onChange={(e) => setCollectedAt(e.target.value)}
            required
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
        </div>
        <div>
          <Button type="submit" loading={busy}>
            Add evidence
          </Button>
        </div>
      </form>
    </Card>
  );
}

// --- One logged item: hash, custody chain, verify ----------------------
function EvidenceCard({ item }: { item: EvidenceItem }) {
  const custodyQuery = useQuery({
    queryKey: ["custody", item.id],
    queryFn: () => evidenceApi.custody(item.id),
  });

  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<HashVerification | null>(null);
  const [verifyProblem, setVerifyProblem] = useState<Problem | { kind: "no-file" } | null>(
    null,
  );

  async function verify() {
    setVerifying(true);
    setVerifyProblem(null);
    setVerifyResult(null);
    try {
      const result = await evidenceApi.verify(item.id);
      setVerifyResult(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setVerifyProblem({ kind: "no-file" });
      } else {
        setVerifyProblem(classify(err));
      }
    } finally {
      setVerifying(false);
    }
  }

  return (
    <Card>
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h3 className="font-medium text-ink">{item.item_type}</h3>
          <p className="text-sm text-ink-muted">{item.description}</p>
        </div>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-muted">
          {item.status}
        </span>
      </div>

      <dl className="mb-4 grid grid-cols-[7rem_1fr] gap-y-1 text-xs">
        <dt className="text-ink-faint">Evidence id</dt>
        <dd className="font-mono text-ink-muted">{item.id}</dd>
        <dt className="text-ink-faint">SHA-256</dt>
        <dd className="font-mono break-all text-ink-muted">
          {item.sha256_hash ?? "— (no digital file)"}
        </dd>
      </dl>

      {item.sha256_hash && (
        <div className="mb-4">
          <Button variant="secondary" onClick={verify} loading={verifying}>
            Verify integrity
          </Button>
          {verifyProblem?.kind === "no-file" && (
            <p className="mt-2 text-sm text-warn">
              No stored file to verify (409) — was it removed from the vault?
            </p>
          )}
          {verifyProblem && verifyProblem.kind === "forbidden" && (
            <p className="mt-2 text-sm text-bad">
              Needs the <code>evidence.vault.read</code> permission.
            </p>
          )}
          {verifyResult && (
            <div className="mt-3">
              <Alert variant={verifyResult.match ? "info" : "error"}>
                <span className="font-semibold">
                  {verifyResult.match ? "Match: file is intact." : "MISMATCH — tampering detected."}
                </span>
                <div className="mt-1 font-mono text-xs break-all">
                  <div>stored: {verifyResult.stored_hash}</div>
                  <div>computed: {verifyResult.computed_hash}</div>
                </div>
              </Alert>
            </div>
          )}
        </div>
      )}

      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
        Chain of custody
      </h4>
      {custodyQuery.isLoading && <Spinner label="Loading chain…" />}
      {custodyQuery.error instanceof ApiError && custodyQuery.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>evidence.vault.read</code> permission to view custody.
        </Alert>
      )}
      {custodyQuery.data && (
        <ol className="flex flex-col gap-2 border-l-2 border-hair pl-4">
          {custodyQuery.data.map((ev: CustodyEvent) => (
            <li key={ev.id} className="text-sm">
              <span className="font-medium text-ink">{ev.action}</span>{" "}
              <span className="text-ink-faint">
                — {new Date(ev.occurred_at).toLocaleString()}
              </span>
              {ev.to_officer && (
                <span className="text-ink-faint">
                  {" "}
                  · to <span className="font-mono text-xs">{ev.to_officer.slice(0, 8)}…</span>
                </span>
              )}
              {ev.acknowledgement && (
                <span className="ml-1 rounded-full bg-ok/10 px-2 py-0.5 text-xs text-ok">
                  acknowledged
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
