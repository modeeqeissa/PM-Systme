import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { OutcomeAlert, nowLocalInput } from "../components/queued";
import { accessClaims } from "../lib/auth";
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
  const { busy, outcome, run } = useSubmit(onDone);
  const [suspectId, setSuspectId] = useState("");
  const [arrestDate, setArrestDate] = useState(nowLocalInput);
  const [location, setLocation] = useState("");
  const [legalBasis, setLegalBasis] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!claims) return;
    void run(
      () =>
        fileArrest(caseId, {
          officer_id: claims.sub,
          suspect_id: suspectId.trim(),
          arrest_date: new Date(arrestDate).toISOString(),
          location: location.trim() || null,
          legal_basis: legalBasis.trim() || null,
        }),
      () => {
        setSuspectId("");
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
          <TextInput label="Suspect id" value={suspectId} onChange={(e) => setSuspectId(e.target.value)} placeholder="uuid" required />
          <DateField id="ar-date" label="Arrest date" value={arrestDate} onChange={setArrestDate} />
          <TextInput label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="optional" />
          <TextInput label="Legal basis" value={legalBasis} onChange={(e) => setLegalBasis(e.target.value)} placeholder="optional" />
          <Button type="submit" loading={busy}>
            Record arrest
          </Button>
        </form>
      )}
    </Section>
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
