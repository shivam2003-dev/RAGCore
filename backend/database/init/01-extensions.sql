-- Runs once on first container start (empty data volume).
-- Alembic owns all schema DDL; only extensions live here because
-- CREATE EXTENSION requires superuser and migrations run as the app role.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram similarity for fuzzy keyword matching
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- server-side UUID generation fallback

-- Dedicated database for pytest runs (kept isolated from dev data).
CREATE DATABASE cvum_test OWNER cvum;
\connect cvum_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
