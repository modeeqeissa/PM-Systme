-- Runs once on first container start. Creates one database per microservice,
-- matching docs Section 3.3 / 9.1. Add new services here AND in CLAUDE.md's table.
CREATE DATABASE identity_db;
CREATE DATABASE case_db;
CREATE DATABASE evidence_db;
CREATE DATABASE community_db;
CREATE DATABASE training_db;
CREATE DATABASE hr_db;
CREATE DATABASE dashboard_db;
CREATE DATABASE notification_db;
CREATE DATABASE integration_db;
CREATE DATABASE audit_db;
