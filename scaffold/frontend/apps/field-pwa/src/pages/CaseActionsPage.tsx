import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { OutcomeAlert, nowLocalInput } from "../components/queued";
import { accessClaims, getAccessToken } from "../lib/auth";
import { ApiError, persons as personsApi, type PersonRow } from "../lib/api";
import { getCase, outboxAll, storageHeadroom, type CachedCase, type OutboxItem } from "../lib/db";
import { useOnline } from "../lib/net";
import {
  fileArrest,
  fileEvidence,
  fileStatement,
  runQueuedWrite,
  type WriteOutcome,
} from "../lib/sync";

export function CaseActionsPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
  const online = useOnline();
  const [cse, setCase] = useState<CachedCase | undefined>();
  const [queued, setQueued] = useState<OutboxItem[]>([]);
  const [headroom, setHeadroom] = useState<Awaited<ReturnType<typeof storageHeadroom>>>(null);

  const reload = useCallback(async () => {
    setCase(await getCase(caseId));
    setQueued((await outboxAll()).filter((o) => o.caseId === caseId && o.state === "queued"));
    setHeadroom(await storageHeadroom());
  }, [caseId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <Link to="/" className="mb-4 inline-block text-sm text-slate-500 underline">
        ← My cases
      </Link>
      <h1 className="text-lg font-semibold text-slate-900">
        {cse ? cse.case_number : "Case"}
      </h1>
      <p className="mb-4 text-sm text-slate-500">
        Record work against this case. Everything is saved on this device first
        and synced with an idempotency key — a retry can't duplicate it.
      </p>

      {!online && (
        <div className="mb-3">
          <Alert variant="error">Offline — new records queue on this device.</Alert>
        </div>
      )}
      {headroom && headroom.pctUsed > 80 && (
        <div className="mb-3">
          <Alert variant="error">
            Device storage {headroom.pctUsed.toFixed(0)}% full ({headroom.usedMB.toFixed(0)} /{" "}
            {headroom.quotaMB.toFixed(0)} MB). Sync soon — large evidence files may not save.
          </Alert>
        </div>
      )}

      {queued.length > 0 && (
        <Card className="mb-3">
          <p className="text-sm text-amber-800">
            Queued on this device for this case:{" "}
            {queued.map((q) => q.kind).join(", ")}.
          </p>
        </Card>
      )}

      <StatementSection caseId={caseId} onDone={reload} onReauth={() => navigate("/login", { replace: true })} />
      <ArrestSection caseId={caseId} onDone={reload} onReauth={() => navigate("/login", { replace: true })} />
      <EvidenceSection caseId={caseId} onDone={reload} onReauth={() => navigate("/login", { replace: true })} />
    </div>
  );
}

function Section({
  title,
  fr,
  children,
}: {
  title: string;
  fr: string;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="mb-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Add"}
        </Button>
      </div>
      <p className="mt-1 text-xs text-slate-500">{fr}</p>
      {open && <div className="mt-3">{children(() => setOpen(false))}</div>}
    </Card>
  );
}

function DateField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type="datetime-local"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
      />
    </div>
  );
}

type SectionProps = { caseId: string; onDone: () => void; onReauth: () => void };

function useSubmit(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<WriteOutcome | null>(null);
  async function run(enqueueFn: () => Promise<string>, onSuccess: () => void) {
    setBusy(true);
    setOutcome(null);
    try {
      const r = await runQueuedWrite(enqueueFn);
      setOutcome(r);
      if (r.kind === "synced" || r.kind === "queued") onSuccess();
      await Promise.resolve(onDone());
    } finally {
      setBusy(false);
    }
  }
  return { busy, outcome, run };
}

function StatementSection({ caseId, onDone, onReauth }: SectionProps) {
  const claims = accessClaims();
  const { busy, outcome, run } = useSubmit(onDone);
  const [partyType, setPartyType] = useState("witness");
  const [text, setText] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    void run(
      () =>
        fileStatement(caseId, {
          recorded_by: claims.sub,
          party_type: partyType,
          statement_text: text.trim(),
        }),
      () => setText(""),
    );
  }

  return (
    <Section title="Record statement" fr="FR-CASE-05 — witness / suspect / victim account.">
      {() => (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <OutcomeAlert outcome={outcome} noun="statement" onReauth={onReauth} />
          <div className="flex flex-col gap-1">
            <label htmlFor="st-party" className="text-sm font-medium text-slate-700">
              Party type
            </label>
            <select
              id="st-party"
              value={partyType}
              onChange={(e) => setPartyType(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              <option value="witness">Witness</option>
              <option value="suspect">Suspect</option>
              <option value="victim">Victim</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="st-text" className="text-sm font-medium text-slate-700">
              Statement
            </label>
            <textarea
              id="st-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <Button type="submit" loading={busy}>
            Record statement
          </Button>
        </form>
      )}
    </Section>
  );
}

function ArrestSection({ caseId, onDone, onReauth }: SectionProps) {
  const claims = accessClaims();
  const online = useOnline();
  const { busy, outcome, run } = useSubmit(onDone);
  const [suspect, setSuspect] = useState<PersonRow | null>(null);
  const [arrestDate, setArrestDate] = useState(nowLocalInput);
  const [location, setLocation] = useState("");
  const [legalBasis, setLegalBasis] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims || !suspect) return;
    void run(
      () =>
        fileArrest(caseId, {
          officer_id: claims.sub,
          suspect_id: suspect.id,
          arrest_date: new Date(arrestDate).toISOString(),
          location: location.trim() || null,
          legal_basis: legalBasis.trim() || null,
        }),
      () => {
        setSuspect(null);
        setLocation("");
        setLegalBasis("");
      },
    );
  }

  return (
    <Section title="Record arrest" fr="FR-CASE-04 — suspect, time, legal basis.">
      {() => (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <OutcomeAlert outcome={outcome} noun="arrest" onReauth={onReauth} />
          <SuspectField online={online} value={suspect} onChange={setSuspect} />
          <DateField id="ar-date" label="Arrest date" value={arrestDate} onChange={setArrestDate} />
          <TextInput label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="optional" />
          <TextInput label="Legal basis" value={legalBasis} onChange={(e) => setLegalBasis(e.target.value)} placeholder="optional" />
          <Button type="submit" loading={busy} disabled={!suspect}>
            Record arrest
          </Button>
        </form>
      )}
    </Section>
  );
}

/**
 * Resolve or register the arrested person (docs §9.3.2). `suspect_id` is a real
 * FK now and `persons` has no offline idempotency key, so this is online-only:
 * when offline the officer is told to reconnect before recording the arrest.
 * The arrest itself still queues once a person is chosen and survives a later
 * connectivity drop before sync.
 */
function SuspectField({
  online,
  value,
  onChange,
}: {
  online: boolean;
  value: PersonRow | null;
  onChange: (p: PersonRow | null) => void;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PersonRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [dob, setDob] = useState("");
  const [nid, setNid] = useState("");

  if (!online && !value) {
    return (
      <Alert variant="error">
        Recording an arrest needs a connection to look up or register the person.
        Reconnect and try again.
      </Alert>
    );
  }

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm">
        <span className="text-slate-900">
          {value.last_name}, {value.first_name}
          {value.national_id ? ` · ID ${value.national_id}` : ""}
        </span>
        <Button type="button" variant="secondary" onClick={() => onChange(null)}>
          Change
        </Button>
      </div>
    );
  }

  async function doSearch() {
    const token = getAccessToken();
    if (!token || term.trim().length < 2) return;
    setBusy(true);
    setErr(null);
    try {
      setResults(await personsApi.search(token, term.trim()));
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 403 ? "Needs the case.read permission." : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function doCreate() {
    const token = getAccessToken();
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      const p = await personsApi.create(token, {
        first_name: first.trim(),
        last_name: last.trim(),
        date_of_birth: dob || null,
        national_id: nid.trim() || null,
      });
      onChange(p);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setErr("That national ID already belongs to someone — search for them.");
      else if (e instanceof ApiError && e.status === 403) setErr("Needs the case.write permission.");
      else setErr("Couldn't create the person.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-300 p-3">
      <span className="text-sm font-medium text-slate-700">Suspect</span>
      {err && <Alert variant="error">{err}</Alert>}

      {!creating && (
        <>
          <div className="flex gap-2">
            <input
              aria-label="Search people"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void doSearch();
                }
              }}
              placeholder="Search by name"
              className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <Button type="button" variant="secondary" onClick={doSearch} loading={busy}>
              Search
            </Button>
          </div>
          {results && results.length === 0 && (
            <p className="text-xs text-slate-500">No match. Register a new person below.</p>
          )}
          {results && results.length > 0 && (
            <ul className="flex flex-col rounded-md border border-slate-200">
              {results.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => onChange(p)}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                  >
                    {p.last_name}, {p.first_name}
                    {p.national_id ? ` · ID ${p.national_id}` : ""}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button type="button" variant="secondary" onClick={() => setCreating(true)}>
            + New person
          </Button>
        </>
      )}

      {creating && (
        <div className="flex flex-col gap-2">
          <TextInput label="First name" value={first} onChange={(e) => setFirst(e.target.value)} />
          <TextInput label="Last name" value={last} onChange={(e) => setLast(e.target.value)} />
          <div className="flex flex-col gap-1">
            <label htmlFor="sus-dob" className="text-sm font-medium text-slate-700">
              Date of birth (optional)
            </label>
            <input
              id="sus-dob"
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <TextInput label="National ID" value={nid} onChange={(e) => setNid(e.target.value)} placeholder="optional" />
          <div className="flex gap-2">
            <Button type="button" onClick={doCreate} loading={busy} disabled={!first.trim() || !last.trim()}>
              Create &amp; select
            </Button>
            <Button type="button" variant="secondary" onClick={() => setCreating(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceSection({ caseId, onDone, onReauth }: SectionProps) {
  const claims = accessClaims();
  const { busy, outcome, run } = useSubmit(onDone);
  const [itemType, setItemType] = useState("");
  const [description, setDescription] = useState("");
  const [collectedAt, setCollectedAt] = useState(nowLocalInput);
  const [file, setFile] = useState<File | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    void run(
      () =>
        fileEvidence(
          caseId,
          {
            case_id: caseId,
            item_type: itemType.trim(),
            description: description.trim(),
            collected_by: claims.sub,
            collected_at: new Date(collectedAt).toISOString(),
          },
          file ?? undefined,
        ),
      () => {
        setItemType("");
        setDescription("");
        setFile(null);
      },
    );
  }

  return (
    <Section
      title="Log evidence"
      fr="FR-EVID-01/02 — a photo/file is stored on this device until sync, then hashed server-side."
    >
      {() => (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <OutcomeAlert outcome={outcome} noun="evidence item" onReauth={onReauth} />
          <TextInput label="Item type" value={itemType} onChange={(e) => setItemType(e.target.value)} placeholder="e.g. photograph, weapon, document" required />
          <div className="flex flex-col gap-1">
            <label htmlFor="ev-desc" className="text-sm font-medium text-slate-700">
              Description
            </label>
            <textarea
              id="ev-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              required
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="ev-file" className="text-sm font-medium text-slate-700">
              Photo / file (optional)
            </label>
            <input
              id="ev-file"
              type="file"
              accept="image/*,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
            {file && (
              <p className="text-xs text-slate-500">
                {file.name} — {(file.size / 1e6).toFixed(2)} MB (held on this device until sync)
              </p>
            )}
          </div>
          <DateField id="ev-at" label="Collected at" value={collectedAt} onChange={setCollectedAt} />
          <Button type="submit" loading={busy}>
            Log evidence
          </Button>
        </form>
      )}
    </Section>
  );
}
