import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import {
  ApiError,
  training,
  type AttendanceStatus,
  type TrainingSession,
} from "../../lib/api";
import { currentClaims } from "../../lib/auth";
import { hasPerm } from "../../lib/rbac";
import { classify, ProblemAlert, type Problem } from "../../lib/problem";
import { localInputToIso, toLocalInputValue } from "../../lib/datetime";

const ATT_LABEL: Record<AttendanceStatus, string> = {
  registered: "Registered",
  attended: "Attended",
  absent: "Absent",
};

export function CourseDetailPage() {
  const { courseId = "" } = useParams();
  const id = Number(courseId);
  const navigate = useNavigate();
  const canWrite = hasPerm("training.cert.write");

  const courseQ = useQuery({
    queryKey: ["tr-course", id],
    queryFn: () => training.courses.list().then((cs) => cs.find((c) => c.id === id) ?? null),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  if (courseQ.error instanceof ApiError && courseQ.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <Link to="/training/courses" className="mb-4 inline-block text-sm text-ink-faint underline">
          ← Back to catalog
        </Link>

        {courseQ.isLoading && <Card><Spinner label="Loading course…" /></Card>}
        {courseQ.error instanceof ApiError && courseQ.error.status === 403 && (
          <Alert variant="error">
            Your role can't view this course (needs <code>training.cert.read</code>).
          </Alert>
        )}
        {courseQ.data === null && !courseQ.isLoading && (
          <Alert variant="error">No course with that id.</Alert>
        )}

        {courseQ.data && (
          <>
            <Card className="mb-6">
              <h1 className="text-xl font-semibold text-ink">{courseQ.data.title}</h1>
              <p className="mt-1 text-sm text-ink-faint">
                valid {courseQ.data.validity_months} months
                {courseQ.data.mandatory && " · mandatory"}
              </p>
            </Card>

            <MaterialsSection courseId={id} canWrite={canWrite} />
            <SessionsSection courseId={id} canWrite={canWrite} />
            <AssessmentsSection courseId={id} canWrite={canWrite} />
          </>
        )}
      </div>
    </div>
  );
}

function MaterialsSection({ courseId, canWrite }: { courseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const q = useQuery({
    queryKey: ["tr-materials", courseId],
    queryFn: () => training.materials.forCourse(courseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  async function upload(e: FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setProblem({ kind: "validation", fields: { file: "Choose a file" } });
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const form = new FormData();
      form.set("title", title.trim());
      form.set("file", file);
      await training.materials.upload(courseId, form);
      await qc.invalidateQueries({ queryKey: ["tr-materials", courseId] });
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setRemovingId(id);
    setProblem(null);
    try {
      await training.materials.remove(id);
      await qc.invalidateQueries({ queryKey: ["tr-materials", courseId] });
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-ink">Materials</h2>
      <p className="mb-3 text-sm text-ink-faint">
        docs §9.3.5 — course documents, stored object-storage-backed like evidence files.
      </p>
      <ProblemAlert problem={problem} service="training-service" forbiddenHint="Needs training.cert.write." />

      {canWrite && (
        <form onSubmit={upload} className="mb-4 flex flex-col gap-3">
          <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <div className="flex flex-col gap-1">
            <label htmlFor="mat-file" className="text-sm font-medium text-ink-muted">File</label>
            <input
              id="mat-file"
              ref={fileRef}
              type="file"
              className="text-sm text-ink-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-sm file:font-medium"
            />
          </div>
          <div>
            <Button type="submit" loading={busy}>Upload material</Button>
          </div>
        </form>
      )}

      {q.isLoading && <Spinner label="Loading materials…" />}
      {q.error instanceof ApiError && q.error.status === 403 && (
        <Alert variant="error">Needs <code>training.cert.read</code> to view materials.</Alert>
      )}
      {q.data && q.data.length === 0 && <p className="text-sm text-ink-faint">No materials yet.</p>}
      <ul className="flex flex-col gap-2">
        {(q.data ?? []).map((m) => (
          <li key={m.id} className="flex items-center justify-between border-b border-hair pb-2 text-sm last:border-0">
            <span>
              {m.title}{" "}
              <span className="ml-1 font-mono text-xs text-ink-faint">{m.file_ref}</span>
            </span>
            {canWrite && (
              <Button variant="secondary" loading={removingId === m.id} onClick={() => remove(m.id)}>
                Delete
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SessionsSection({ courseId, canWrite }: { courseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const claims = currentClaims();
  const q = useQuery({
    queryKey: ["tr-sessions", courseId],
    queryFn: () => training.sessions.list(courseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const [scheduledAt, setScheduledAt] = useState(() => toLocalInputValue(new Date()));
  const [location, setLocation] = useState("");
  const [capacity, setCapacity] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function schedule(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await training.sessions.create({
        course_id: courseId,
        scheduled_at: localInputToIso(scheduledAt),
        location: location.trim() || null,
        instructor_officer_id: claims?.sub ?? null,
        capacity: capacity ? Number(capacity) : null,
      });
      await qc.invalidateQueries({ queryKey: ["tr-sessions", courseId] });
      setLocation("");
      setCapacity("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-ink">Sessions</h2>
      <p className="mb-3 text-sm text-ink-faint">
        docs §9.3.5 — scheduled instances of this course, with per-officer attendance.
      </p>
      <ProblemAlert problem={problem} service="training-service" forbiddenHint="Needs training.cert.write." />

      {canWrite && (
        <form onSubmit={schedule} className="mb-4 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="sess-at" className="text-sm font-medium text-ink-muted">Scheduled at</label>
            <input
              id="sess-at"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              required
              className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
            />
          </div>
          <TextInput label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="optional" />
          <TextInput label="Capacity" type="number" min="1" value={capacity} onChange={(e) => setCapacity(e.target.value)} placeholder="optional" />
          <div><Button type="submit" loading={busy}>Schedule session</Button></div>
        </form>
      )}

      {q.isLoading && <Spinner label="Loading sessions…" />}
      {q.error instanceof ApiError && q.error.status === 403 && (
        <Alert variant="error">Needs <code>training.cert.read</code> to view sessions.</Alert>
      )}
      {q.data && q.data.length === 0 && <p className="text-sm text-ink-faint">No sessions scheduled.</p>}
      <div className="flex flex-col gap-3">
        {(q.data ?? []).map((s) => (
          <SessionRow key={s.id} session={s} canWrite={canWrite} />
        ))}
      </div>
    </Card>
  );
}

function SessionRow({ session: s, canWrite }: { session: TrainingSession; canWrite: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const attQ = useQuery({
    queryKey: ["tr-attendance", s.id],
    queryFn: () => training.sessions.attendance(s.id),
    enabled: open,
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const [officerId, setOfficerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function register(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await training.sessions.register(s.id, { officer_id: officerId.trim() });
      await qc.invalidateQueries({ queryKey: ["tr-attendance", s.id] });
      setOfficerId("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(attendanceId: string, status: AttendanceStatus) {
    setProblem(null);
    try {
      await training.sessions.setAttendanceStatus(attendanceId, status);
      await qc.invalidateQueries({ queryKey: ["tr-attendance", s.id] });
    } catch (err) {
      setProblem(classify(err));
    }
  }

  return (
    <div className="border-b border-hair pb-3 last:border-0">
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink">
          {new Date(s.scheduled_at).toLocaleString()}
          {s.location && ` · ${s.location}`}
          {s.capacity != null && ` · cap ${s.capacity}`}
        </span>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide attendance" : "Attendance"}
        </Button>
      </div>

      {open && (
        <div className="mt-3">
          <ProblemAlert problem={problem} service="training-service" forbiddenHint="Needs training.cert.write." />
          {canWrite && (
            <form onSubmit={register} className="mb-3 flex gap-2">
              <TextInput label="Officer id" value={officerId} onChange={(e) => setOfficerId(e.target.value)} placeholder="uuid" required />
              <div className="self-end"><Button type="submit" loading={busy}>Register</Button></div>
            </form>
          )}
          {attQ.isLoading && <Spinner label="Loading attendance…" />}
          {attQ.data && attQ.data.length === 0 && (
            <p className="text-sm text-ink-faint">Nobody registered yet.</p>
          )}
          <ul className="flex flex-col gap-2">
            {(attQ.data ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm">
                <span className="font-mono text-xs">{a.officer_id}</span>
                <span className="flex items-center gap-2">
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted">
                    {ATT_LABEL[a.status]}
                  </span>
                  {canWrite && a.status !== "attended" && (
                    <button className="text-xs text-ink-faint underline" onClick={() => setStatus(a.id, "attended")}>
                      mark attended
                    </button>
                  )}
                  {canWrite && a.status !== "absent" && (
                    <button className="text-xs text-ink-faint underline" onClick={() => setStatus(a.id, "absent")}>
                      mark absent
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AssessmentsSection({ courseId, canWrite }: { courseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["tr-assessments", courseId],
    queryFn: () => training.assessments.forCourse(courseId),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const [title, setTitle] = useState("");
  const [passingScore, setPassingScore] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await training.assessments.create(courseId, {
        title: title.trim(),
        passing_score: Number(passingScore),
      });
      await qc.invalidateQueries({ queryKey: ["tr-assessments", courseId] });
      setTitle("");
      setPassingScore("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <h2 className="text-lg font-semibold text-ink">Assessments</h2>
      <p className="mb-3 text-sm text-ink-faint">
        docs §9.3.5 — pass/fail is derived from the passing score at grading time.
      </p>
      <ProblemAlert problem={problem} service="training-service" forbiddenHint="Needs training.cert.write." />

      {canWrite && (
        <form onSubmit={create} className="mb-4 flex flex-col gap-3">
          <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <TextInput label="Passing score" type="number" min="0" max="100" value={passingScore} onChange={(e) => setPassingScore(e.target.value)} required />
          <div><Button type="submit" loading={busy}>Add assessment</Button></div>
        </form>
      )}

      {q.isLoading && <Spinner label="Loading assessments…" />}
      {q.error instanceof ApiError && q.error.status === 403 && (
        <Alert variant="error">Needs <code>training.cert.read</code> to view assessments.</Alert>
      )}
      {q.data && q.data.length === 0 && <p className="text-sm text-ink-faint">No assessments yet.</p>}
      <div className="flex flex-col gap-3">
        {(q.data ?? []).map((a) => (
          <AssessmentRow key={a.id} assessmentId={a.id} title={a.title} passingScore={a.passing_score} canWrite={canWrite} />
        ))}
      </div>
    </Card>
  );
}

function AssessmentRow({
  assessmentId,
  title,
  passingScore,
  canWrite,
}: {
  assessmentId: string;
  title: string;
  passingScore: number | string;
  canWrite: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const resultsQ = useQuery({
    queryKey: ["tr-results", assessmentId],
    queryFn: () => training.assessments.results(assessmentId),
    enabled: open,
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const [officerId, setOfficerId] = useState("");
  const [score, setScore] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function grade(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      await training.assessments.recordResult(assessmentId, {
        officer_id: officerId.trim(),
        score: Number(score),
      });
      await qc.invalidateQueries({ queryKey: ["tr-results", assessmentId] });
      setOfficerId("");
      setScore("");
    } catch (err) {
      setProblem(classify(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-hair pb-3 last:border-0">
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink">
          {title} <span className="text-ink-faint">· pass ≥ {String(passingScore)}</span>
        </span>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide results" : "Results"}
        </Button>
      </div>

      {open && (
        <div className="mt-3">
          <ProblemAlert problem={problem} service="training-service" forbiddenHint="Needs training.cert.write." />
          {canWrite && (
            <form onSubmit={grade} className="mb-3 flex gap-2">
              <TextInput label="Officer id" value={officerId} onChange={(e) => setOfficerId(e.target.value)} placeholder="uuid" required />
              <TextInput label="Score" type="number" min="0" max="100" value={score} onChange={(e) => setScore(e.target.value)} required />
              <div className="self-end"><Button type="submit" loading={busy}>Record</Button></div>
            </form>
          )}
          {resultsQ.isLoading && <Spinner label="Loading results…" />}
          {resultsQ.data && resultsQ.data.length === 0 && (
            <p className="text-sm text-ink-faint">No results recorded.</p>
          )}
          <ul className="flex flex-col gap-2">
            {(resultsQ.data ?? []).map((r) => (
              <li key={r.id} className="flex items-center justify-between text-sm">
                <span className="font-mono text-xs">{r.officer_id}</span>
                <span className="flex items-center gap-2">
                  <span className="text-ink-muted">{String(r.score)}</span>
                  <span
                    className={
                      "rounded-full px-2 py-0.5 text-xs font-medium " +
                      (r.passed ? "bg-ok/10 text-ok" : "bg-bad/10 text-bad")
                    }
                  >
                    {r.passed ? "Pass" : "Fail"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
