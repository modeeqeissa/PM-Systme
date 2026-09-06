/**
 * Shared request-error classification + a standard alert, so every domain
 * screen handles 403 / 422 / network / other the same way the case-detail
 * cards already do.
 */
import { Alert } from "@pmp/ui";
import { ApiError, validationErrors } from "./api";

export type Problem =
  | { kind: "validation"; fields: Record<string, string> }
  | { kind: "forbidden" }
  | { kind: "notfound" }
  | { kind: "network" }
  | { kind: "other"; message: string };

export function classify(err: unknown): Problem {
  if (err instanceof ApiError) {
    if (err.status === 422) return { kind: "validation", fields: validationErrors(err) };
    if (err.status === 403) return { kind: "forbidden" };
    if (err.status === 404) return { kind: "notfound" };
    return { kind: "other", message: err.message };
  }
  return { kind: "network" };
}

export function fieldErrors(problem: Problem | null): Record<string, string> {
  return problem?.kind === "validation" ? problem.fields : {};
}

/** Non-field problems as a one-line alert. `service` names the backend for the network case. */
export function ProblemAlert({
  problem,
  service,
  forbiddenHint,
}: {
  problem: Problem | null;
  service: string;
  forbiddenHint?: string;
}) {
  if (!problem || problem.kind === "validation") return null;
  if (problem.kind === "forbidden") {
    return (
      <Alert variant="error">
        {forbiddenHint ?? "Your role doesn't allow this action."}
      </Alert>
    );
  }
  if (problem.kind === "notfound") return <Alert variant="error">Not found.</Alert>;
  if (problem.kind === "network") {
    return <Alert variant="error">Couldn't reach {service}. Try again.</Alert>;
  }
  return <Alert variant="error">{problem.message}</Alert>;
}
