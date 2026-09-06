import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { ApiError, training, type Certification, type Course } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../../lib/problem";

export function CourseCatalogPage() {
  const navigate = useNavigate();
  const canWrite = hasPerm("training.cert.write");

  const coursesQuery = useQuery({
    queryKey: ["tr-courses"],
    queryFn: () => training.courses.list(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const certsQuery = useQuery({
    queryKey: ["tr-certifications"],
    queryFn: () => training.certifications.list(),
    retry: false,
  });

  if (coursesQuery.error instanceof ApiError && coursesQuery.error.status === 401) {
    navigate("/login", { replace: true });
    return null;
  }

  const certsByCourse = new Map<number, Certification[]>();
  for (const c of certsQuery.data ?? []) {
    certsByCourse.set(c.course_id, [...(certsByCourse.get(c.course_id) ?? []), c]);
  }

  return (
    <div>
      <NavBar />
      <div className="mx-auto max-w-3xl px-4 pb-10">
        <h1 className="text-xl font-semibold text-slate-900">Course catalog</h1>
        <p className="mb-6 text-sm text-slate-500">
          FR-TRAIN-01 — courses and the certifications each one issues on completion.
        </p>

        {canWrite && <NewCourseForm />}

        {coursesQuery.isLoading && (
          <Card>
            <Spinner label="Loading courses…" />
          </Card>
        )}
        {coursesQuery.error instanceof ApiError && coursesQuery.error.status === 403 && (
          <Alert variant="error">
            Your role can't view courses (needs <code>training.cert.read</code>).
          </Alert>
        )}
        {coursesQuery.data && coursesQuery.data.length === 0 && (
          <Card>
            <p className="text-sm text-slate-500">No courses in the catalog yet.</p>
          </Card>
        )}
        <div className="flex flex-col gap-4">
          {(coursesQuery.data ?? []).map((course) => (
            <CourseCard
              key={course.id}
              course={course}
              certs={certsByCourse.get(course.id) ?? []}
              canWrite={canWrite}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function NewCourseForm() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", validity_months: "", mandatory: false });
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
      await training.courses.create({
        title: form.title.trim(),
        validity_months: Number(form.validity_months),
        mandatory: form.mandatory,
      });
      setDone(true);
      setForm({ title: "", validity_months: "", mandatory: false });
      await qc.invalidateQueries({ queryKey: ["tr-courses"] });
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
        <h2 className="text-lg font-semibold text-slate-900">Add course</h2>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "Add course"}
        </Button>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <ProblemAlert
            problem={problem}
            service="training-service"
            forbiddenHint="Your role can't add courses (needs training.cert.write)."
          />
          {done && <Alert variant="info">Course added.</Alert>}
          <TextInput label="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} error={fe.title} required />
          <TextInput
            label="Validity (months)"
            type="number"
            min="1"
            value={form.validity_months}
            onChange={(e) => setForm((f) => ({ ...f, validity_months: e.target.value }))}
            error={fe.validity_months}
            required
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.mandatory}
              onChange={(e) => setForm((f) => ({ ...f, mandatory: e.target.checked }))}
            />
            Mandatory
          </label>
          <div>
            <Button type="submit" loading={busy}>
              Add course
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

function CourseCard({
  course,
  certs,
  canWrite,
}: {
  course: Course;
  certs: Certification[];
  canWrite: boolean;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    title: course.title,
    validity_months: String(course.validity_months),
    mandatory: course.mandatory,
  });
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState(false);
  const fe = fieldErrors(problem);

  async function run(fn: () => Promise<unknown>) {
    setProblem(null);
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["tr-courses"] });
      await qc.invalidateQueries({ queryKey: ["tr-certifications"] });
      setEditing(false);
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
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-medium text-slate-900">{course.title}</h3>
          <p className="text-sm text-slate-500">
            valid {course.validity_months} months
            {course.mandatory && " · mandatory"}
          </p>
        </div>
        {canWrite && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setEditing((v) => !v)}>
              {editing ? "Cancel" : "Edit"}
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => run(() => training.courses.remove(course.id))}
            >
              Delete
            </Button>
          </div>
        )}
      </div>

      <div className="mt-2">
        <ProblemAlert
          problem={problem}
          service="training-service"
          forbiddenHint="Your role can't edit courses (needs training.cert.write)."
        />
      </div>

      {editing && (
        <form
          className="mt-3 flex flex-col gap-3 border-t border-slate-100 pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(() =>
              training.courses.update(course.id, {
                title: form.title.trim(),
                validity_months: Number(form.validity_months),
                mandatory: form.mandatory,
              }),
            );
          }}
        >
          <TextInput label="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} error={fe.title} />
          <TextInput
            label="Validity (months)"
            type="number"
            min="1"
            value={form.validity_months}
            onChange={(e) => setForm((f) => ({ ...f, validity_months: e.target.value }))}
            error={fe.validity_months}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={form.mandatory} onChange={(e) => setForm((f) => ({ ...f, mandatory: e.target.checked }))} />
            Mandatory
          </label>
          <div>
            <Button type="submit" loading={busy}>
              Save
            </Button>
          </div>
        </form>
      )}

      <div className="mt-3 border-t border-slate-100 pt-3">
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Certifications
        </h4>
        {certs.length === 0 && <p className="text-sm text-slate-500">None defined.</p>}
        <ul className="flex flex-col gap-1 text-sm">
          {certs.map((c) => (
            <li key={c.id} className="flex items-center justify-between">
              <span>Certification #{c.id}</span>
              {canWrite && (
                <button
                  className="text-xs text-slate-500 underline hover:text-rose-600"
                  onClick={() => run(() => training.certifications.remove(c.id))}
                >
                  remove
                </button>
              )}
            </li>
          ))}
        </ul>
        {canWrite && (
          <Button
            variant="secondary"
            className="mt-2"
            loading={busy}
            onClick={() => run(() => training.certifications.create({ course_id: course.id }))}
          >
            Add certification
          </Button>
        )}
      </div>
    </Card>
  );
}
