# Render deployment and operations

Final recruiter edition - 16 October 2026

## Verified live deployment

- UI: https://expense-sharing-app-inda.onrender.com/
- Swagger: https://expense-sharing-app-inda.onrender.com/docs
- OpenAPI: https://expense-sharing-app-inda.onrender.com/openapi.json
- Readiness: https://expense-sharing-app-inda.onrender.com/health/ready
- Source: https://github.com/manansethi1205/expense-sharing-app

The existing web service was created manually on Render's free Docker tier. The live managed database is **PostgreSQL 18 in Oregon**, confirmed in the dashboard. The local Docker/test setup and reusable `render.yaml` specify PostgreSQL 17; the Blueprint selects Singapore for a separate new deployment. These are distinct deployment configurations using the same application/schema. No existing region, database URL or compute plan was changed during the deployment repair.

FastAPI serves the Fairshare UI at `/`, static assets at `/static`, and financial APIs under `/api/v1`. The browser displays real saved backend results. There is no separate frontend build, mock balance engine or external CDN dependency.

## Existing service settings

| Setting | Value |
| --- | --- |
| Runtime / compute | Docker / Free |
| Repository branch | main |
| Docker Command | `python -m scripts.start_render` |
| Health Check Path | `/health/ready` |
| `DATABASE_URL` | Render PostgreSQL Internal Database URL, set privately in service Environment |
| `EXACT_SETTLEMENT_THRESHOLD` | `16` |
| `PORT` | Supplied by Render and read by the startup script |

No `.env` upload is needed on Render. The localhost connection in `.env.example` is for local development. Do not add `API_PORT`, `DB_PORT`, `TEST_DB_PORT` or `TEST_DATABASE_URL` to the hosted application; those configure local Compose/testing.

`scripts.start_render.main()` applies Alembic head, idempotently seeds synthetic data and starts Uvicorn on `0.0.0.0:$PORT`. A migration failure stops startup. An existing seeded trip is preserved rather than overwritten. Startup migration is a single-instance free-demo compromise; production scaling should use a separate migration stage.

## Deploy a separate copy

1. Use [Deploy to Render](https://render.com/deploy?repo=https://github.com/manansethi1205/expense-sharing-app) or create a Blueprint from the root `render.yaml` in your account.
2. Review its two resources: one free Docker web service and one free PostgreSQL 17 database in Singapore. Only one free database is allowed per workspace; resolve an existing allocation instead of unintentionally selecting a paid plan.
3. The Blueprint links `DATABASE_URL` through `fromDatabase` and sets `ipAllowList: []` on the database to disable external connections. It configures the startup command and readiness path. These Blueprint properties do not automatically apply to a manually created service.
4. For manual creation, create PostgreSQL first, keep both services in the same region, copy its Internal Database URL into the web service environment and enter the settings above. The app normalizes the standard PostgreSQL URI to the installed Psycopg driver without losing encoded passwords/query options.
5. Wait for deployment completion, then check `/`, `/docs`, `/health/ready` and `/api/v1/groups`. A 200 readiness response proves connectivity; a group response and populated UI additionally establish that schema/seed operations succeeded.
6. Use a fresh demo group to try expense recording and partial settlement. Share the actual assigned URL only after verifying the workflow.

## Recruiter walkthrough

The initial seeded trip has Dinner INR 1,200 paid by Mohit, Taxi INR 600 paid by Rahul and Hotel INR 3,000 paid by Mohit. Total spending is INR 4,800, with INR 1,600 allocated to each member. Mohit receives INR 2,600; Rahul owes INR 1,000 and Ankit INR 1,600. Shared reviewer actions can change an existing group; **Create a fresh demo trip** recreates the starting scenario without resetting another group.

The UI supports equal/custom shares, category correction, personal-view switching, period reports, lifetime balances, suggested payments, partial repayment recording, people and global search. Payments only record synthetic external transfers. The 21-request Postman walkthrough uses a separate dinner-only group and captures IDs; select the Render environment to run it on the hosted API. The fixed-ID `docs/demo.http` example is for an empty local database only.

## Deployment troubleshooting

| Symptom | Diagnosis / action |
| --- | --- |
| Connection refused at localhost:5432 | `DATABASE_URL` still points at local development; use the Render internal connection URL and deploy the saved setting. |
| Readiness 200, but relation groups does not exist | Connectivity is valid but migrations were skipped. Set Docker Command to `python -m scripts.start_render` and redeploy. This was the actual initial deployment failure and is resolved. |
| UI HTTP 500/502 error | Check current Render logs; do not treat all backend failures as cold starts. The UI safely handles plain-text/HTML failures and preserves structured validation errors. |
| Cold-start loading screen | Free service is waking up. Allow roughly one minute, then retry; persistent failures need logs/readiness checks. |
| Expired database | Review database status/lifetime in Render. Upgrade only with explicit budget approval, or reprovision an intended demo database and update the connection. |

The original missing-table failure was fixed by applying the startup command; the public expense-to-settlement smoke script passed afterward. See [verification evidence](verification.md).

## Hosting lifetime and scope

Render's free web service sleeps after **15 minutes without inbound traffic**, and wakeup takes about a minute. Free PostgreSQL expires **30 days after creation** and is not an indefinite portfolio database. Check the dashboard before sending the link or extending the review window. No paid resource is introduced by the checked-in Blueprint. [Official free-tier limits](https://render.com/docs/free)

This shared demo has no authentication. Use synthetic data only. Fresh-trip setup consists of multiple requests and can leave partial synthetic records if a request fails; it is not a transactional reset. Creation POSTs have no idempotency keys. The startup seed never deletes or rewrites reviewer history.

The final PDFs now include this deployment, application baseline `72f1182`, API `0.1.0` and schema `0002`. They can be reviewed independently of hosted availability. [Regeneration tooling](tooling/README.md)

## References

- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render Docker settings](https://render.com/docs/docker)
- [Environment variables](https://render.com/docs/configure-environment-variables)
- [PostgreSQL connection guidance](https://render.com/docs/postgresql-creating-connecting)
