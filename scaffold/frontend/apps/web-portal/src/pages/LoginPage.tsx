import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Alert, Button, Card, TextInput } from "@pmp/ui";
import { ApiError, iam } from "../lib/api";
import { hasValidToken, setToken } from "../lib/auth";

type Step = "credentials" | "enroll" | "totp";

function credentialError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "Wrong badge number or password.";
    if (err.status === 403) return "This account is suspended or deactivated.";
    if (err.status === 423)
      return "Account locked after too many failed attempts. Contact ICT / security.";
    return err.message;
  }
  return "Could not reach iam-service. Is it running on :8001?";
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const dest = location.state?.from ?? "/cases";

  const [step, setStep] = useState<Step>("credentials");
  const [badge, setBadge] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrollment, setEnrollment] = useState<{ secret: string; uri: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // already signed in? go straight through.
  useEffect(() => {
    if (hasValidToken()) navigate(dest, { replace: true });
    // only on mount — a fresh sign-in navigates explicitly
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submitCredentials(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await iam.login(badge.trim(), password);
      if (res.mfa_enrolled) {
        setStep("totp");
      } else {
        const enr = await iam.enrollMfa(res.mfa_token);
        setEnrollment({ secret: enr.secret, uri: enr.otpauth_uri });
        setStep("enroll");
      }
    } catch (err) {
      setError(credentialError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // fetch a fresh mfa_token, then exchange it + the TOTP code for a JWT
      const login = await iam.login(badge.trim(), password);
      const pair = await iam.verifyMfa(login.mfa_token, code.trim());
      setToken(pair.access_token);
      navigate(dest, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("That code didn't match. Try the current 6-digit code.");
      } else {
        setError(credentialError(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <Card>
        <h1 className="mb-1 text-lg font-semibold text-slate-900">PMP Command Portal</h1>
        <p className="mb-6 text-sm text-slate-500">Sign in with your badge number.</p>

        {error && (
          <div className="mb-4">
            <Alert variant="error">{error}</Alert>
          </div>
        )}

        {step === "credentials" && (
          <form onSubmit={submitCredentials} className="flex flex-col gap-4">
            <TextInput
              label="Badge number"
              value={badge}
              onChange={(e) => setBadge(e.target.value)}
              autoFocus
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
        )}

        {step === "enroll" && enrollment && (
          <div className="flex flex-col gap-4">
            <Alert variant="info">
              This account has no authenticator yet. Add this secret to your TOTP app,
              then enter the current code.
            </Alert>
            <div className="rounded-md bg-slate-100 p-3 font-mono text-xs break-all text-slate-700">
              {enrollment.secret}
            </div>
            <p className="text-xs text-slate-500 break-all">{enrollment.uri}</p>
            <Button onClick={() => setStep("totp")} variant="secondary">
              I've added it — enter code
            </Button>
          </div>
        )}

        {step === "totp" && (
          <form onSubmit={submitCode} className="flex flex-col gap-4">
            <TextInput
              label="6-digit authenticator code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              required
            />
            <Button type="submit" loading={busy}>
              Sign in
            </Button>
            <button
              type="button"
              className="text-xs text-slate-500 underline"
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
      <p className="mt-4 text-center text-xs text-slate-400">
        Talks to iam-service on <code>:8001</code>. Needs docker-compose + iam-service up.
      </p>
    </div>
  );
}
