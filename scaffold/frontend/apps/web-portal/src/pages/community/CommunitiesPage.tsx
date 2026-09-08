import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, community, type Community, type Organization } from "../../lib/api";
import { currentClaims } from "../../lib/auth";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

export function CommunitiesPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("community.write");

  const communitiesQ = useQuery({
    queryKey: ["cm-communities"],
    queryFn: () => community.communities.list(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const orgsQ = useQuery({
    queryKey: ["cm-organizations"],
    queryFn: () => community.organizations.list(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (communitiesQ.error instanceof ApiError && communitiesQ.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  const communities = communitiesQ.data ?? [];
  const byId = new Map(communities.map((c) => [c.id, c.name]));

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <h1 className="text-xl font-semibold text-ink">Communities &amp; partners</h1>
        <p className="mb-6 text-sm text-ink-faint">
          docs §9.3.4 — named neighbourhood groups (per station) and the partner
          organizations that work with them.
        </p>

        {canWrite && <NewCommunityForm />}

        {communitiesQ.isLoading && (
          <Card>
            <Spinner label="Loading communities…" />
          </Card>
        )}
        {communitiesQ.error instanceof ApiError && communitiesQ.error.status === 403 && (
          <Alert variant="error">
            Your role can't view communities (needs <code>community.read</code>).
          </Alert>
        )}
        {communities.length === 0 && !communitiesQ.isLoading && (
          <Card>
            <p className="text-sm text-ink-faint">No communities yet.</p>
          </Card>
        )}
        <div className="flex flex-col gap-4">
          {communities.map((c) => (
            <CommunityCard key={c.id} community={c} canWrite={canWrite} />
          ))}
        </div>

        <h2 className="mb-3 mt-10 text-lg font-semibold text-ink">Partner organizations</h2>
        {canWrite && <NewOrganizationForm communities={communities} />}
        {orgsQ.data && orgsQ.data.length === 0 && (
          <Card>
            <p className="text-sm text-ink-faint">No organizations yet.</p>
          </Card>
        )}
        <div className="flex flex-col gap-3">
          {(orgsQ.data ?? []).map((o: Organization) => (
            <Card key={o.id}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-ink">{o.name}</h3>
                  {o.contact_name && (
                    <p className="text-sm text-ink-faint">
                      {o.contact_name}
                      {o.contact_phone ? ` · ${o.contact_phone}` : ""}
                    </p>
                  )}
                </div>
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted">
                  {o.community_id ? (byId.get(o.community_id) ?? "linked") : "unaffiliated"}
                </span>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function CommunityCard({ community: c, canWrite }: { community: Community; canWrite: boolean }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(c.name);
  const [description, setDescription] = useState(c.description ?? "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await community.communities.update(c.id, {
        name: name.trim(),
        description: description.trim() || null,
      });
      await qc.invalidateQueries({ queryKey: ["cm-communities"] });
      setEditing(false);
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      {!editing ? (
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-medium text-ink">{c.name}</h3>
            <p className="text-sm text-ink-faint">
              station <span className="font-mono text-xs">{c.station_id.slice(0, 8)}…</span>
            </p>
            {c.description && <p className="mt-1 text-sm text-ink-muted">{c.description}</p>}
          </div>
          {canWrite && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
          )}
        </div>
      ) : (
        <form onSubmit={save} className="flex flex-col gap-3">
          <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
          <TextInput label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          <TextInput label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" loading={busy}>Save</Button>
            <Button type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function NewCommunityForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const claims = currentClaims();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState(false);
  const fe = fieldErrors(problem);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setDone(false);
    setBusy(true);
    try {
      await community.communities.create({
        name: name.trim(),
        station_id: stationId.trim(),
        description: description.trim() || null,
      });
      setDone(true);
      setName("");
      setDescription("");
      await qc.invalidateQueries({ queryKey: ["cm-communities"] });
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
        <h2 className="text-lg font-semibold text-ink">New community</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "New community"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <ProblemAlert problem={problem} service="community-service" forbiddenHint="Your role can't create communities (needs community.write)." />
          {done && <Alert variant="info">Community created.</Alert>}
          <TextInput label="Name" value={name} onChange={(e) => setName(e.target.value)} error={fe.name} required />
          <TextInput label="Station id" value={stationId} onChange={(e) => setStationId(e.target.value)} error={fe.station_id} placeholder="uuid" required />
          <TextInput label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <div>
            <Button type="submit" loading={busy}>Create community</Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function NewOrganizationForm({ communities }: { communities: Community[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [communityId, setCommunityId] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState(false);
  const fe = fieldErrors(problem);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setDone(false);
    setBusy(true);
    try {
      await community.organizations.create({
        name: name.trim(),
        community_id: communityId || null,
        contact_name: contactName.trim() || null,
        contact_phone: contactPhone.trim() || null,
      });
      setDone(true);
      setName("");
      setContactName("");
      setContactPhone("");
      setCommunityId("");
      await qc.invalidateQueries({ queryKey: ["cm-organizations"] });
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-ink">New organization</h3>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "New organization"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
          {done && <Alert variant="info">Organization created.</Alert>}
          <TextInput label="Name" value={name} onChange={(e) => setName(e.target.value)} error={fe.name} required />
          <div className="flex flex-col gap-1">
            <label htmlFor="org-community" className="text-sm font-medium text-ink-muted">
              Community (optional)
            </label>
            <select
              id="org-community"
              value={communityId}
              onChange={(e) => setCommunityId(e.target.value)}
              className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
            >
              <option value="">— unaffiliated —</option>
              {communities.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <TextInput label="Contact name" value={contactName} onChange={(e) => setContactName(e.target.value)} />
          <TextInput label="Contact phone" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
          <div>
            <Button type="submit" loading={busy}>Create organization</Button>
          </div>
        </form>
      )}
    </Card>
  );
}
