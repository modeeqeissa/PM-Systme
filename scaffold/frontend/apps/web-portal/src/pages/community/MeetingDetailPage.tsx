import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, community, type Decision, type DecisionStatus } from "../../lib/api";
import { currentClaims } from "../../lib/auth";
import { hasPerm } from "../../lib/rbac";
import { classify, ProblemAlert, type Problem } from "../../lib/problem";

const DECISION_STATUS_LABEL: Record<DecisionStatus, string> = {
  pending: "Pending",
  implemented: "Implemented",
  abandoned: "Abandoned",
};

export function MeetingDetailPage() {
  const { meetingId = "" } = useParams();
  const navigate = useNavigate();
  const canWrite = hasPerm("community.write");

  const meetingQ = useQuery({
    queryKey: ["cm-meeting", meetingId],
    queryFn: () => community.meetings.get(meetingId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (meetingQ.error instanceof ApiError && meetingQ.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <Link to="/community/meetings" className="mb-4 inline-block text-sm text-ink-faint underline">
          ← Back to meetings
        </Link>

        {meetingQ.isLoading && (
          <Card><Spinner label="Loading meeting…" /></Card>
        )}
        {meetingQ.error instanceof ApiError && meetingQ.error.status === 404 && (
          <Alert variant="error">No meeting with that id.</Alert>
        )}
        {meetingQ.error instanceof ApiError && meetingQ.error.status === 403 && (
          <Alert variant="error">
            Your role can't view this meeting (needs <code>community.read</code>).
          </Alert>
        )}

        {meetingQ.data && (
          <>
            <Card className="mb-6">
              <h1 className="text-xl font-semibold text-ink">{meetingQ.data.location}</h1>
              <p className="mt-1 text-sm text-ink-faint">
                {meetingQ.data.meeting_date} · facilitator{" "}
                <span className="font-mono text-xs">{meetingQ.data.facilitator_id.slice(0, 8)}…</span>
              </p>
              {meetingQ.data.community_id && (
                <p className="text-sm text-ink-faint">
                  community <span className="font-mono text-xs">{meetingQ.data.community_id.slice(0, 8)}…</span>
                </p>
              )}
              {meetingQ.data.attendee_summary && (
                <p className="mt-2 text-sm text-ink-muted">{meetingQ.data.attendee_summary}</p>
              )}
            </Card>

            <MinutesSection meetingId={meetingId} canWrite={canWrite} />
            <DecisionsSection meetingId={meetingId} canWrite={canWrite} />
          </>
        )}
      </div>
    </div>
  );
}

function MinutesSection({ meetingId, canWrite }: { meetingId: string; canWrite: boolean }) {
  const qc = useQueryClient();
  const claims = currentClaims();
  const q = useQuery({
    queryKey: ["cm-minutes", meetingId],
    queryFn: () => community.minutes.get(meetingId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const exists = !(q.error instanceof ApiError && q.error.status === 404) && !!q.data;
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      if (exists) {
        await community.minutes.update(meetingId, { content: content.trim() });
      } else {
        await community.minutes.create(meetingId, {
          content: content.trim(),
          recorded_by: claims?.sub ?? "",
        });
      }
      await qc.invalidateQueries({ queryKey: ["cm-minutes", meetingId] });
      setEditing(false);
      setContent("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Minutes</h2>
        {canWrite && !editing && (
          <Button
            variant="secondary"
            onClick={() => {
              setContent(exists ? q.data!.content : "");
              setEditing(true);
            }}
          >
            {exists ? "Edit minutes" : "Record minutes"}
          </Button>
        )}
      </div>
      <p className="mb-3 text-sm text-ink-faint">
        docs §9.3.4 — one formal minutes record per meeting.
      </p>

      {q.isLoading && <Spinner label="Loading minutes…" />}
      {q.error instanceof ApiError && q.error.status === 403 && (
        <Alert variant="error">Needs <code>community.read</code> to view minutes.</Alert>
      )}

      {editing ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />
          <textarea
            aria-label="Minutes content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            required
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
          <div className="flex gap-2">
            <Button type="submit" loading={busy}>Save minutes</Button>
            <Button type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </form>
      ) : exists ? (
        <p className="whitespace-pre-wrap text-sm text-ink-muted">{q.data!.content}</p>
      ) : (
        !q.isLoading && <p className="text-sm text-ink-faint">No minutes recorded yet.</p>
      )}
    </Card>
  );
}

function DecisionsSection({ meetingId, canWrite }: { meetingId: string; canWrite: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["cm-decisions", meetingId],
    queryFn: () => community.decisions.forMeeting(meetingId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await community.decisions.create(meetingId, { description: description.trim() });
      await qc.invalidateQueries({ queryKey: ["cm-decisions", meetingId] });
      setDescription("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  async function move(d: Decision, status: DecisionStatus) {
    setMovingId(d.id);
    setProblem(null);
    try {
      await community.decisions.setStatus(d.id, status);
      await qc.invalidateQueries({ queryKey: ["cm-decisions", meetingId] });
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setMovingId(null);
    }
  }

  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-ink">Decisions</h2>
      <p className="mb-3 text-sm text-ink-faint">
        docs §9.3.4 — formal resolutions, each with a pending / implemented / abandoned status.
      </p>

      <ProblemAlert problem={problem} service="community-service" forbiddenHint="Needs community.write." />

      {canWrite && (
        <form onSubmit={add} className="mb-4 flex flex-col gap-2">
          <textarea
            aria-label="New decision"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            required
            placeholder="The resolution made…"
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
          <div>
            <Button type="submit" loading={busy}>Record decision</Button>
          </div>
        </form>
      )}

      {q.isLoading && <Spinner label="Loading decisions…" />}
      {q.error instanceof ApiError && q.error.status === 403 && (
        <Alert variant="error">Needs <code>community.read</code> to view decisions.</Alert>
      )}
      {q.data && q.data.length === 0 && (
        <p className="text-sm text-ink-faint">No decisions recorded yet.</p>
      )}
      <ul className="flex flex-col gap-3">
        {(q.data ?? []).map((d) => (
          <li key={d.id} className="border-b border-hair pb-3 text-sm last:border-0">
            <div className="flex items-start justify-between gap-3">
              <p className="text-ink-muted">{d.description}</p>
              <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium text-ink-muted">
                {DECISION_STATUS_LABEL[d.status]}
              </span>
            </div>
            {canWrite && d.status === "pending" && (
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" onClick={() => move(d, "implemented")} loading={movingId === d.id}>
                  Mark implemented
                </Button>
                <Button variant="secondary" onClick={() => move(d, "abandoned")} loading={movingId === d.id}>
                  Abandon
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
