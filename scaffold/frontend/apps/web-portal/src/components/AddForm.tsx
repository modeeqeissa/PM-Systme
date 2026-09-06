import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button } from "@pmp/ui";
import { ApiError } from "../lib/api";
import { classify, fieldErrors, ProblemAlert, type Problem } from "../lib/problem";

/**
 * Collapsible "add X" form shell used by the domain history cards. Handles the
 * open/close toggle, the busy state, 401→/login, and the standard
 * ProblemAlert + per-field error plumbing so each card only supplies its
 * fields and the submit call.
 */
export function AddForm({
  title,
  service,
  forbiddenHint,
  submitLabel,
  openLabel,
  onSubmit,
  successText,
  children,
}: {
  title: string;
  service: string;
  forbiddenHint?: string;
  submitLabel: string;
  openLabel: string;
  onSubmit: () => Promise<void>;
  successText: (result: unknown) => ReactNode;
  children: (fieldErr: Record<string, string>) => ReactNode;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState<ReactNode | null>(null);

  async function handle(e: FormEvent) {
    e.preventDefault();
    setProblem(null);
    setDone(null);
    setBusy(true);
    try {
      await onSubmit();
      setDone(successText(undefined));
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
    <div className="mb-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">{title}</h3>
        <Button variant="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : openLabel}
        </Button>
      </div>
      {open && (
        <form onSubmit={handle} className="mt-3 flex flex-col gap-3">
          <ProblemAlert problem={problem} service={service} forbiddenHint={forbiddenHint} />
          {done && <Alert variant="info">{done}</Alert>}
          {children(fieldErrors(problem))}
          <div>
            <Button type="submit" loading={busy}>
              {submitLabel}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
