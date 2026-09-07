# PMP — Kubernetes manifests (generic, portable)

Plain YAML for the 10 PMP microservices, **not tied to any cloud or on-prem
target** and **not deployable as-is**. Every value a real deployment must
supply is a `REPLACE_ME…` placeholder or lives in a Secret *template*. Adjust
these for your environment (Kustomize overlay, Helm-ify, or edit in place).

```
infra/k8s/
  kustomization.yaml          # applies cluster/ + all services/<svc>/
  cluster/
    namespaces.yaml           # 12 namespaces: 10 service + pmp-gateway + pmp-data
    default-deny.yaml          # per-namespace default-deny (Ingress+Egress)
  services/<svc>/              # one dir per service (docs §3.6)
    deployment.yaml            # initContainer runs `alembic upgrade head`, then the app
    service.yaml               # ClusterIP only — never public (§3.5)
    configmap.yaml             # non-secret env
    secret.template.yaml       # placeholder keys ONLY — never commit real values
    hpa.yaml                   # autoscaling/v2, CPU 70%
    resourcequota.yaml         # per-namespace quota (§3.6)
    networkpolicy.yaml         # per-service allow rules on top of default-deny
```

One namespace per service, `pmp-<svc>` (docs §3.6). `pmp.gov/tier: sensitive`
marks **`pmp-evidence`** and **`pmp-hr`** — stricter network posture and a
dedicated encryption-key Secret (§3.6 / NFR-SEC-05). Ports match CLAUDE.md's
table (iam 8001 … audit 8010).

## Validation done (NOT a deployment)

Rendered with Kustomize and schema-checked with **kubeconform `-strict`**
against Kubernetes **1.29** — 92 objects, **all valid**, 0 errors:

```
kubectl kustomize infra/k8s | kubeconform -strict -summary -kubernetes-version 1.29.0
# Summary: 92 resources found parsing stdin - Valid: 92, Invalid: 0, Errors: 0, Skipped: 0
```

This confirms the manifests are well-formed, schema-correct, and internally
consistent (env-var names match each service's `app/config.py`; container /
Service ports match CLAUDE.md; DB names match `infra/init-databases.sql`).
**It was not applied to a cluster** — no live API validation, admission,
scheduling, or connectivity was tested.

`kubectl apply --dry-run=client -k infra/k8s` also parses/builds cleanly
(full client dry-run needs a reachable cluster for its OpenAPI download).

---

## What you MUST fill in before a real deployment

### 1. Images
Every `deployment.yaml` uses `REPLACE_ME_REGISTRY/pmp-<svc>:REPLACE_ME_TAG`
for both the `migrate` initContainer and the app container. Point these at your
built images (same image for both — the initContainer just runs `alembic`).
The container command assumes `uvicorn` is on `PATH` in the image (it is — it's
a runtime dependency).

### 2. Secrets — `services/<svc>/secret.template.yaml`
Templates only. Do **not** commit a filled-in copy. Supply via your secret
manager as a `Secret` with these exact keys, or an `ExternalSecret` /
`SecretProviderClass` that projects them:

| Service | Keys |
|---|---|
| all | `<PREFIX>_DB_PASSWORD` (or `<PREFIX>_DB_OWNER_PASSWORD` + `<PREFIX>_DB_APP_PASSWORD` for `evidence` and `audit`) |
| `iam` | `IAM_JWT_PRIVATE_KEY` (RS256 PEM — the JWKS signing key), `IAM_MFA_ENC_KEY` (urlsafe-base64 32-byte Fernet key) |
| `evidence` | `EVIDENCE_VAULT_KEY` (dedicated evidence-vault encryption key — §3.6 / NFR-SEC-05) |
| `hr` | `HR_DISCIPLINE_ENC_KEY` — **provisioned but not yet consumed.** Reserved for field-level encryption of discipline records; hr-service does not read it today. Kept so evidence and HR each have their own key per §3.6. |

**Which secret manager:** not decided. Options: External Secrets Operator +
(AWS Secrets Manager / GCP Secret Manager / Vault), or the CSI Secrets Store
driver. Pick one and replace the plain `Secret` templates with the
corresponding `ExternalSecret` / `SecretProviderClass`.

### 3. Database + Kafka + object store (the data plane)
The manifests assume an **in-cluster** data plane in namespace `pmp-data`
(label `pmp.gov/plane: data`) — e.g. CloudNativePG (Postgres, one DB per
service), Strimzi (Kafka), MinIO (evidence object store). The service
`NetworkPolicy` egress rules and the `<PREFIX>_DB_HOST` /
`EVENTS_KAFKA_BOOTSTRAP` values point there.

If instead you use **managed / off-cluster** services (RDS / Cloud SQL / MSK /
S3):
- update `<PREFIX>_DB_HOST`, `<PREFIX>_DB_PORT`, `EVENTS_KAFKA_BOOTSTRAP` in
  each `configmap.yaml`;
- replace the `namespaceSelector: { pmp.gov/plane: data }` egress rules in
  each `networkpolicy.yaml` with `ipBlock` CIDRs — every policy carries a
  commented example;
- delete the `pmp-data` namespace from `cluster/namespaces.yaml`.

Databases and roles the DB admin must create up front: the 10 databases from
`infra/init-databases.sql`, plus per-service login roles. The ConfigMaps use
example role names (`<svc>_service`, or `<svc>_owner` + `<svc>_app` for
`evidence`/`audit` — owner runs migrations, app runs the service, per
`config.py`). Rename to taste; keep ConfigMap user ↔ Secret password in sync.

**Storage class** for the data-plane PVs (Postgres / Kafka / MinIO): choose a
class with the right IOPS/durability for each and set it on the operator's
`PersistentVolumeClaim` templates. Not specified here — the data plane is out
of scope of these manifests.

### 4. Ingress / API gateway (§3.5)
No microservice is publicly reachable. All external traffic goes through the
**API gateway** (TLS termination, JWT validation, per-role rate limits, signed
context headers) — a **separate** deployment (Kong / Envoy Gateway / APISIX),
not a PMP microservice and not included here. Deploy it into a namespace
labelled `pmp.gov/role: gateway` (a placeholder `pmp-gateway` namespace is in
`cluster/namespaces.yaml`); every service `NetworkPolicy` already allows
ingress only from that label.

You must supply: the gateway itself and its route config, the public
**ingress hostname(s)** and **TLS** (cert-manager `Certificate` /
`ClusterIssuer`, or your LB's managed certs), and the WAF/rate-limit policy.

`integration-gateway` is the one service allowed egress to **external
systems** (CAD / NCDB / COURTS / JAIL, FR-INT-01..05); its `networkpolicy.yaml`
has a placeholder `ipBlock` (RFC 5737 doc range) — replace with the real
per-partner CIDRs. Mutual TLS to those systems is configured in
`integration_configs`, not in the NetworkPolicy.

### 5. Sizing — everything here is a PLACEHOLDER
- `replicas: 2`, HPA `minReplicas: 2` / `maxReplicas: 6` — **not load-tested.**
- container `resources.requests/limits` — nominal guesses.
- HPA scales on **CPU 70%** only. NFR-SCALE-01 also wants **queue-depth**
  scaling for the event consumers (`dashboard`, `notification`, `audit`) —
  that needs a custom/external metrics adapter (KEDA or prometheus-adapter);
  each of those HPAs has a commented `External` `kafka_consumergroup_lag`
  example to enable once the adapter is installed.
- `ResourceQuota` per namespace — nominal budgets.

Run a load test and set real numbers before production.

### 6. Not covered here (deliberately)
- Service mesh / mTLS for internal traffic (§3.5) — layer Istio or Linkerd on
  top; the NetworkPolicies are L3/L4 only.
- Blue/green or canary rollout (§3.6) — use Argo Rollouts / Flagger.
- Backups, monitoring (Prometheus/Grafana), log aggregation, PodDisruptionBudgets.
- The `pmp-gateway` and `pmp-data` namespaces are placeholders with baseline
  (not restricted) Pod Security — the operators that run there set their own.
