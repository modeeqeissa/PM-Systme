/** The 10 PMP microservices, grouped into the architecture layers the
 *  reference shell shows (Presentation -> Gateway -> Services -> Data).
 *  `proxy` is the same-origin prefix Vite forwards to each service. */
export interface ServiceDef {
  key: string;
  name: string;
  proxy: string;
  port: number;
  note: string;
}

export interface Layer {
  id: string;
  title: string;
  blurb: string;
  services: ServiceDef[];
}

export const HEALTH_LAYERS: Layer[] = [
  {
    id: "identity",
    title: "Access & Identity",
    blurb: "OAuth2 / OIDC, JWT issue + JWKS, RBAC source of truth.",
    services: [
      { key: "iam", name: "iam-service", proxy: "/api/iam", port: 8001, note: "identity_db" },
    ],
  },
  {
    id: "core",
    title: "Core Domain Services",
    blurb: "One independently deployable service per operational environment.",
    services: [
      { key: "case", name: "case-service", proxy: "/api/case", port: 8002, note: "case_db" },
      { key: "evidence", name: "evidence-service", proxy: "/api/evidence", port: 8003, note: "evidence_db · vault" },
      { key: "community", name: "community-service", proxy: "/api/community", port: 8004, note: "community_db" },
      { key: "training", name: "training-service", proxy: "/api/training", port: 8005, note: "training_db" },
      { key: "hr", name: "hr-service", proxy: "/api/hr", port: 8006, note: "hr_db" },
    ],
  },
  {
    id: "readfanout",
    title: "Read Models & Fan-out",
    blurb: "Kafka consumers — projections, notifications, the audit hash chain.",
    services: [
      { key: "dashboard", name: "dashboard-service", proxy: "/api/dash", port: 8007, note: "dashboard_db · read only" },
      { key: "notification", name: "notification-service", proxy: "/api/notification", port: 8008, note: "notification_db" },
      { key: "audit", name: "audit-service", proxy: "/api/audit", port: 8010, note: "audit_db · append only" },
    ],
  },
  {
    id: "edge",
    title: "Integration Edge",
    blurb: "The one service allowed egress to external systems (CAD / NCDB / COURTS / JAIL).",
    services: [
      { key: "integration", name: "integration-gateway-service", proxy: "/api/integration", port: 8009, note: "integration_db" },
    ],
  },
];

export const ALL_SERVICES: ServiceDef[] = HEALTH_LAYERS.flatMap((l) => l.services);
