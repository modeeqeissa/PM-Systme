import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { ApiError, iam } from "../lib/api";
import { hasSession, setTokens } from "../lib/auth";
import { syncNow } from "../lib/sync";

export function LoginPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"credentials" | "mfa">("credentials");
  const [badge, setBadge] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (hasSession()) {
    navigate("/", { replace: true });
    return null;
  }

  async function submitCredentials(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await iam.login(badge.trim(), password);
      setMfaToken(r.mfa_token);
      setStep("mfa");
    } catch (err) {
      setError(
        err instanceof ApiError && err.offline
          ? "No connection — sign in needs to reach iam-service."
          : "Badge number or password not recognised.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const pair = await iam.verifyMfa(mfaToken, code.trim());
      setTokens(pair.access_token, pair.refresh_token);
      void syncNow().catch(() => {});
      navigate("/", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.offline
          ? "No connection — try again when you have signal."
          : "That code didn't verify. Check your authenticator and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <Card>
        <h1 className="text-xl font-semibold text-slate-900">PMP Field</h1>
        <p className="mb-4 text-sm text-slate-500">
          Sign in once with signal — your session then works offline.
        </p>

        {error && (
          <div className="mb-4">
            <Alert variant="error">{error}</Alert>
          </div>
        )}

        {step === "credentials" ? (
          <form onSubmit={submitCredentials} className="flex flex-col gap-4">
            <TextInput
              label="Badge number"
              value={badge}
              onChange={(e) => setBadge(e.target.value)}
              autoComplete="username"
              required
            />
            <TextInput
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <Button type="submit" loading={busy}>
              Continue
            </Button>
          </form>
        ) : (
          <form onSubmit={submitCode} className="flex flex-col gap-4">
            <TextInput
              label="6-digit authenticator code"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoFocus
              required
            />
            <Button type="submit" loading={busy}>
              Sign in
            </Button>
            <button
              type="button"
              className="text-sm text-slate-500 underline"
              onClick={() => {
                setStep("credentials");
                setCode("");
                setError(null);
              }}
            >
              Start over
            </button>
          </form>
        )}
      </Card>
    </div>
  );
}
