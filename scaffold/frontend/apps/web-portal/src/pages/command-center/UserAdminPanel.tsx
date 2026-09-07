import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Badge, Button, GlassCard, GlassPanel, SectionLabel, Spinner } from "@pmp/ui";
import {
  ApiError,
  iamAdmin,
  validationErrors,
  type AdminRole,
  type AdminUser,
  type AdminUserCreate,
} from "../../lib/api";
import { hasPerm } from "../../lib/rbac";

const STATUS_TONE = { active: "ok", suspended: "warn", deactivated: "bad" } as const;

/** B4 — user & role administration against iam-service's existing admin
 *  endpoints. View gated on `iam.user.read`; create + deactivate re-check
 *  `iam.user.write`, role reassignment re-checks `iam.role.write`. Every
 *  mutation here hits an endpoint that already emits an audit event
 *  (UserCreated / UserDeactivated / UserRoleReassigned). */
export function UserAdminPanel() {
  const qc = useQueryClient();
  const canWrite = hasPerm("iam.user.write");
  const canAssignRoles = hasPerm("iam.role.write");
  const canReadRoles = hasPerm("iam.role.read");

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [applied, setApplied] = useState({ q: "", status: "" });
  const [showCreate, setShowCreate] = useState(false);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  const usersQ = useQuery({
    queryKey: ["admin-users", applied],
    queryFn: () => iamAdmin.users({ q: applied.q || undefined, status: applied.status || undefined }),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const rolesQ = useQuery({
    queryKey: ["admin-roles"],
    queryFn: () => iamAdmin.roles(),
    enabled: canReadRoles,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const deactivate = useMutation({
    mutationFn: (u: AdminUser) => iamAdmin.setStatus(u.id, "deactivated"),
    onSuccess: (_d, u) => {
      setBanner({ kind: "success", text: `${u.badge_number} deactivated — sessions revoked, audit event emitted.` });
      invalidate();
    },
    onError: (e) => setBanner({ kind: "error", text: msg(e) }),
  });

  const forbidden = usersQ.error instanceof ApiError && usersQ.error.status === 403;
  const otherError =
    usersQ.error && !forbidden && !(usersQ.error instanceof ApiError && usersQ.error.status === 401);
  const users = usersQ.data ?? [];

  return (
    <div className="flex flex-col gap-5">
      {banner && (
        <Alert variant={banner.kind === "success" ? "success" : "error"}>{banner.text}</Alert>
      )}

      <GlassPanel compact>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setApplied({ q: q.trim(), status: statusFilter });
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">Search</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="badge / name / email"
              className={inputCls}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">Status</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={inputCls}>
              <option value="">any</option>
              <option value="active">active</option>
              <option value="suspended">suspended</option>
              <option value="deactivated">deactivated</option>
            </select>
          </label>
          <Button type="submit" variant="secondary">
            Apply
          </Button>
          {canWrite && (
            <Button type="button" onClick={() => setShowCreate((s) => !s)}>
              {showCreate ? "Close" : "New user"}
            </Button>
          )}
        </form>
      </GlassPanel>

      {showCreate && canWrite && (
        <CreateUserForm
          roles={rolesQ.data ?? []}
          onDone={(u) => {
            setShowCreate(false);
            setBanner({ kind: "success", text: `Created ${u.badge_number} — audit event emitted.` });
            invalidate();
          }}
          onError={(t) => setBanner({ kind: "error", text: t })}
        />
      )}

      {forbidden && (
        <Alert variant="error">
          Your role can't view user accounts — needs <code>iam.user.read</code>.
        </Alert>
      )}
      {otherError && <Alert variant="error">Couldn't load users: {(usersQ.error as Error).message}</Alert>}

      <GlassPanel compact>
        <SectionLabel>
          {users.length} account{users.length === 1 ? "" : "s"}
          {usersQ.isFetching ? " · loading…" : ""}
        </SectionLabel>
        {usersQ.isLoading ? (
          <div className="mt-3">
            <Spinner label="Loading users…" />
          </div>
        ) : users.length === 0 ? (
          <p className="mt-3 text-sm text-ink-faint">No accounts match.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-hair text-xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="py-2 pr-3 font-medium">Badge</th>
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">MFA</th>
                  <th className="py-2 pr-3 font-medium">Roles</th>
                  <th className="py-2 pr-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <UserRow
                    key={u.id}
                    user={u}
                    roles={rolesQ.data ?? []}
                    canWrite={canWrite}
                    canAssignRoles={canAssignRoles}
                    onDeactivate={() => deactivate.mutate(u)}
                    deactivating={deactivate.isPending && deactivate.variables?.id === u.id}
                    onRolesSaved={(names) => {
                      setBanner({ kind: "success", text: `${u.badge_number} roles → ${names.join(", ") || "none"} (audit event emitted).` });
                      invalidate();
                    }}
                    onError={(t) => setBanner({ kind: "error", text: t })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>

      <RoleMatrix canReadRoles={canReadRoles} />
    </div>
  );
}

function UserRow({
  user,
  roles,
  canWrite,
  canAssignRoles,
  onDeactivate,
  deactivating,
  onRolesSaved,
  onError,
}: {
  user: AdminUser;
  roles: AdminRole[];
  canWrite: boolean;
  canAssignRoles: boolean;
  onDeactivate: () => void;
  deactivating: boolean;
  onRolesSaved: (names: string[]) => void;
  onError: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [picked, setPicked] = useState<number[]>(() => user.roles.map((r) => r.id));

  const save = useMutation({
    mutationFn: () => iamAdmin.setRoles(user.id, picked),
    onSuccess: () => {
      setEditing(false);
      onRolesSaved(roles.filter((r) => picked.includes(r.id)).map((r) => r.name));
    },
    onError: (e) => onError(msg(e)),
  });

  return (
    <>
      <tr className="border-b border-hair/60 align-top">
        <td className="py-2 pr-3 font-mono text-xs text-ink">{user.badge_number}</td>
        <td className="py-2 pr-3 text-ink">{user.full_name}</td>
        <td className="py-2 pr-3">
          <Badge tone={STATUS_TONE[user.status]}>{user.status}</Badge>
        </td>
        <td className="py-2 pr-3">
          <Badge tone={user.mfa_enrolled ? "ok" : "neutral"}>{user.mfa_enrolled ? "enrolled" : "no"}</Badge>
        </td>
        <td className="py-2 pr-3 text-xs text-ink-muted">
          {user.roles.length ? user.roles.map((r) => r.name).join(", ") : "—"}
        </td>
        <td className="py-2 pr-3 text-right">
          <div className="flex justify-end gap-2">
            {canAssignRoles && (
              <button
                onClick={() => {
                  setPicked(user.roles.map((r) => r.id));
                  setEditing((v) => !v);
                }}
                className="rounded border border-hair px-2 py-1 text-xs text-ink-muted hover:bg-surface-3"
              >
                {editing ? "Cancel" : "Edit roles"}
              </button>
            )}
            {canWrite && user.status === "active" && (
              <button
                onClick={onDeactivate}
                disabled={deactivating}
                className="rounded border border-bad/40 px-2 py-1 text-xs text-bad hover:bg-bad/10 disabled:opacity-50"
              >
                {deactivating ? "…" : "Deactivate"}
              </button>
            )}
          </div>
        </td>
      </tr>
      {editing && canAssignRoles && (
        <tr className="border-b border-hair/60">
          <td colSpan={6} className="py-3">
            <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-2 p-3">
              <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">Roles</span>
              {roles.map((r) => (
                <label key={r.id} className="flex items-center gap-1.5 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={picked.includes(r.id)}
                    onChange={(e) =>
                      setPicked((p) => (e.target.checked ? [...p, r.id] : p.filter((x) => x !== r.id)))
                    }
                  />
                  {r.name}
                </label>
              ))}
              <Button onClick={() => save.mutate()} loading={save.isPending}>
                Save roles
              </Button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function CreateUserForm({
  roles,
  onDone,
  onError,
}: {
  roles: AdminRole[];
  onDone: (u: AdminUser) => void;
  onError: (text: string) => void;
}) {
  const [form, setForm] = useState<AdminUserCreate>({
    badge_number: "",
    email: "",
    password: "",
    full_name: "",
    station_id: "",
    role_ids: [],
  });
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});

  const create = useMutation({
    mutationFn: () =>
      iamAdmin.createUser({
        ...form,
        email: form.email || undefined,
      }),
    onSuccess: onDone,
    onError: (e) => {
      setFieldErr(validationErrors(e));
      onError(msg(e));
    },
  });

  const set = (k: keyof AdminUserCreate, v: string) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <GlassCard accent="hr">
      <SectionLabel>New user account</SectionLabel>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        <Field label="Badge number" err={fieldErr.badge_number}>
          <input value={form.badge_number} onChange={(e) => set("badge_number", e.target.value)} className={inputCls} required />
        </Field>
        <Field label="Full name" err={fieldErr.full_name}>
          <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} className={inputCls} required />
        </Field>
        <Field label="Email (optional)" err={fieldErr.email}>
          <input type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} className={inputCls} />
        </Field>
        <Field label="Station id" err={fieldErr.station_id}>
          <input
            value={form.station_id}
            onChange={(e) => set("station_id", e.target.value)}
            className={inputCls + " font-mono text-xs"}
            placeholder="uuid"
            required
          />
        </Field>
        <Field label="Initial password" err={fieldErr.password}>
          <input
            type="password"
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            className={inputCls}
            autoComplete="new-password"
            required
          />
        </Field>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">Roles</span>
          <div className="flex flex-wrap gap-2 rounded-lg bg-surface-2 p-2">
            {roles.length === 0 && <span className="text-xs text-ink-faint">roles not loaded</span>}
            {roles.map((r) => (
              <label key={r.id} className="flex items-center gap-1.5 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={form.role_ids.includes(r.id)}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      role_ids: e.target.checked
                        ? [...f.role_ids, r.id]
                        : f.role_ids.filter((x) => x !== r.id),
                    }))
                  }
                />
                {r.name}
              </label>
            ))}
          </div>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" loading={create.isPending}>
            Create account
          </Button>
          <span className="ml-3 text-[11px] text-ink-faint">
            POST /users · <code>iam.user.write</code> · emits <code>UserCreated</code>
          </span>
        </div>
      </form>
    </GlassCard>
  );
}

function RoleMatrix({ canReadRoles }: { canReadRoles: boolean }) {
  const rolesQ = useQuery({ queryKey: ["admin-roles"], queryFn: () => iamAdmin.roles(), enabled: canReadRoles });
  const permsQ = useQuery({
    queryKey: ["admin-perms"],
    queryFn: () => iamAdmin.permissions(),
    enabled: canReadRoles,
  });

  const allPerms = useMemo(
    () => (permsQ.data ?? []).map((p) => p.code).sort(),
    [permsQ.data],
  );
  const roles = rolesQ.data ?? [];

  if (!canReadRoles) {
    return (
      <GlassPanel compact>
        <SectionLabel>Role / permission matrix</SectionLabel>
        <p className="mt-2 text-sm text-ink-faint">
          Needs <code>iam.role.read</code> to show the live matrix.
        </p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel compact>
      <SectionLabel>Role / permission matrix · live from iam-service</SectionLabel>
      {rolesQ.isLoading || permsQ.isLoading ? (
        <div className="mt-3">
          <Spinner label="Loading roles…" />
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="text-ink-faint">
                <th className="sticky left-0 bg-surface px-2 py-2 font-medium">Permission</th>
                {roles.map((r) => (
                  <th key={r.id} className="px-2 py-2 font-medium whitespace-nowrap">
                    {r.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allPerms.map((code) => (
                <tr key={code} className="border-t border-hair/60">
                  <td className="sticky left-0 bg-surface px-2 py-1.5 font-mono text-ink-muted">{code}</td>
                  {roles.map((r) => (
                    <td key={r.id} className="px-2 py-1.5 text-center">
                      {r.permissions.includes(code) ? (
                        <span className="text-ok">●</span>
                      ) : (
                        <span className="text-ink-faint/40">·</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </GlassPanel>
  );
}

const inputCls =
  "w-full rounded-lg border border-hair bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent-command/50";

function Field({ label, err, children }: { label: string; err?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</span>
      {children}
      {err && <span className="text-xs text-bad">{err}</span>}
    </label>
  );
}

function msg(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return "Forbidden — your role lacks the permission for this action.";
    if (e.status === 409) return "Conflict — that badge number or email is already in use.";
    return e.message;
  }
  return (e as Error)?.message ?? "Request failed";
}
