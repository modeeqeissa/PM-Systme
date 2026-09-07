import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Card } from "@pmp/ui";
import { accessClaims, clearTokens } from "../lib/auth";
import { getCases, getLastSync, outboxAll, type CachedCase, type OutboxIncident } from "../lib/db";
import { useOnline } from "../lib/net";
import { syncNow } from "../lib/sync";

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  investigating: "Investigating",
  referred_prosecution: "Referred — prosecution",
  closed: "Closed",
  suspended: "Suspended",
};

export function CasesPage() {
  const navigate = useNavigate();
  const online = useOnline();
  const claims = accessClaims();

  const [cases, setCases] = useState<CachedCase[] | null>(null);
  const [outbox, setOutbox] = useState<OutboxIncident[]>([]);
  const [lastSync, setLastSync] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setCases(await getCases());
    setOutbox(await outboxAll());
    setLastSync(await getLastSync());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // one sync attempt on mount (best-effort; offline just no-ops)
  useEffect(() => {
    void doSync(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function doSync(silent = false) {
    setSyncing(true);
    setNote(null);
    try {
      const r = await syncNow();
      if (r.needsReauth) {
        clearTokens();
        navigate("/login", { replace: true });
        return;
      }
      if (!silent) {
        if (!r.online) setNote("Still offline — nothing synced.");
        else if (r.synced > 0)
          setNote(`Synced ${r.synced} queued incident${r.synced === 1 ? "" : "s"}.`);
        else setNote("Up to date.");
      }
    } finally {
      setSyncing(false);
      await load();
    }
  }

  const pending = outbox.filter((o) => o.state === "queued");
  const rejected = outbox.filter((o) => o.state === "rejected");

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">My cases</h1>
          {claims && <p className="text-xs text-slate-500">{claims.badge_number}</p>}
        </div>
        <button
          className="text-sm text-slate-500 underline"
          onClick={() => {
            clearTokens();
            navigate("/login", { replace: true });
          }}
        >
          Sign out
        </button>
      </header>

      {!online && (
        <div className="mb-3">
          <Alert variant="error">
            Offline — showing the last synced data. New incidents queue on this
            device and sync automatically when you reconnect.
          </Alert>
        </div>
      )}

      <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
        <span>
          {lastSync
            ? `Last synced ${new Date(lastSync).toLocaleString()}`
            : "Not synced yet"}
        </span>
        <Button variant="secondary" loading={syncing} onClick={() => doSync(false)}>
          Sync now
        </Button>
      </div>

      {note && (
        <div className="mb-3">
          <Alert variant="info">{note}</Alert>
        </div>
      )}

      {(pending.length > 0 || rejected.length > 0) && (
        <Card className="mb-3">
          {pending.length > 0 && (
            <p className="text-sm text-amber-800">
              {pending.length} incident{pending.length === 1 ? "" : "s"} queued on
              this device, waiting to sync.
            </p>
          )}
          {rejected.map((o) => (
            <p key={o.id} className="mt-1 text-sm text-rose-700">
              An incident was rejected by the server ({o.lastError}). It will not
              retry — re-file it.
            </p>
          ))}
        </Card>
      )}

      <Link
        to="/incident"
        className="mb-4 flex items-center justify-center rounded-md bg-slate-900 px-4 py-3 text-sm font-medium text-white"
      >
        File an incident
      </Link>

      {cases == null ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : cases.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-500">
            No cases cached yet. They appear here after a sync while online.
          </p>
        </Card>
      ) : (
        <ul className="flex flex-col gap-2">
          {cases.map((c) => (
            <li key={c.id}>
              <Card>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{c.case_number}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                    {STATUS_LABEL[c.status] ?? c.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Opened {new Date(c.opened_at).toLocaleDateString()}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
