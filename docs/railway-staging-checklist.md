# Railway Staging Checklist

This documents the intended configuration for a **separate staging environment**
used to validate the PostgreSQL-backed storage path before it ever touches
production. No real values or secrets are included here — every variable
below is a placeholder name only.

This document does not itself change any Railway configuration. Creating
the staging environment and setting these variables is a manual step to be
done deliberately, outside of this repository, when explicitly approved.

## Staging environment

| Setting | Value |
|---|---|
| Railway environment | `staging` (separate from `production`) |
| Git branch | `production-readiness` |
| `STORAGE_BACKEND` | `postgres` |
| `DATABASE_URL` | Provided automatically by Railway once a PostgreSQL plugin is attached to the **staging** environment. Never copy a production connection string into staging, and never commit a real value here. |
| Pre-deploy command | `alembic upgrade head` |
| Health-check path | `/health` |

`DATABASE_URL` alone does not activate PostgreSQL — `STORAGE_BACKEND=postgres`
must also be set explicitly (see `app/config.py`). This is intentional: Railway
provisions `DATABASE_URL` as soon as the plugin is attached, before any
migration has run, so activation is a separate, deliberate step.

### Other environment variables staging needs (no real values shown)

- `TRIAL_API_KEY` — staging-only value, different from production's.
- `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` — only needed if AI features are exercised manually in staging; the automated smoke test (`scripts/smoke_test_staging.py`) never calls them.
- `ACCESS_CODE` — staging-only value, different from production's.

## Production must remain unchanged

| Setting | Value |
|---|---|
| Git branch | `main` |
| `STORAGE_BACKEND` | `json` (unset, or explicitly `json`) |
| `DATA_DIR` | Existing value, existing mounted volume — unchanged |

Nothing in this stage modifies production variables, production's branch,
or production's volume. Staging is a fully separate Railway environment
with its own database, its own variables, and its own deploy.

## Deploy sequence for staging (when explicitly approved — not part of this stage)

1. Create the `staging` Railway environment (separate from `production`).
2. Attach a PostgreSQL plugin to `staging` only.
3. Set `STORAGE_BACKEND=postgres` on `staging` only.
4. Set the pre-deploy command to `alembic upgrade head` on `staging` only.
5. Set the health-check path to `/health` on `staging` only.
6. Deploy the `production-readiness` branch to `staging` only.
7. Run `scripts/smoke_test_staging.py --base-url <staging-url> --trial-key <staging-key>` against it.
8. Do not migrate real client data into staging at any point (`data/clients.json` is never used here — the smoke test only ever creates and deletes obviously synthetic clients).

## Rollback procedure — staging only

Staging is disposable and isolated from production by construction, so
"rollback" here means returning staging to a known-clean state, not
protecting production (which was never touched):

1. **Bad deploy / broken migration**: redeploy the previous known-good
   commit on the `staging` environment. Since `STORAGE_BACKEND` lives on
   `staging` only, this never affects `production`.
2. **Staging database needs a clean slate**: detach and re-attach (or
   reset) the `staging` PostgreSQL plugin, then re-run the pre-deploy
   `alembic upgrade head` on the next deploy. There is no real client data
   in staging to lose.
3. **Smoke test leaves synthetic data behind** (e.g. a run with
   `--no-cleanup`, or a run that failed before cleanup): re-run
   `scripts/smoke_test_staging.py` with `--cleanup`, or delete the specific
   synthetic client id(s) reported in the failed run's output via
   `DELETE /clients/{id}`.
4. **Decommissioning staging entirely**: detach the PostgreSQL plugin and
   remove the `staging` environment. Production's volume, database (none
   yet), branch, and variables are entirely unaffected, since they were
   never referenced by anything in this checklist.
