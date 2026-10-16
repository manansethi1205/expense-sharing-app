# Recruiter demo on Render

**Verified live URL:** https://expense-sharing-app-inda.onrender.com/ (2026-10-16). The manually created service initially connected to an empty database; logs reported `relation "groups" does not exist`. Setting its Docker Command to `python -m scripts.start_render` ran migrations and seeded the trip. Health Check Path is `/health/ready`. A successful connectivity check alone does not prove tables exist.

The UI is served at `/` by FastAPI. It calls the same `/api/v1` endpoints documented in Swagger; it has no separate balance calculator or mock financial results. CSS and JavaScript are bundled in `app/static/`, with no Node build or CDN dependency.

## Deploy the free demo

1. Open [Deploy to Render](https://render.com/deploy?repo=https://github.com/manansethi1205/expense-sharing-app) while signed into your Render account. Alternatively create a new Blueprint from this GitHub repository, using the root `render.yaml` file.
2. Review the resources before applying: one **free** Docker web service and one **free** PostgreSQL 17 database, both in Singapore. If your account has already used its free database allowance, stop and resolve that constraint rather than selecting a paid plan unintentionally.
3. Render sets `DATABASE_URL` from the database's internal connection string. PostgreSQL URI normalization selects the installed Psycopg 3 driver. No credential goes into Git or frontend JavaScript. External database access is disabled by `ipAllowList: []`; the app uses Render's private network.
4. The Docker startup override runs `python -m scripts.start_render`: Alembic upgrades to head, the idempotent seed creates the synthetic trip if absent, then Uvicorn binds to `0.0.0.0:$PORT`. The database must be available; failed migrations prevent the server from accepting traffic.
5. Wait for a successful deployment and `/health/ready` returning 200. Open the **actual URL Render assigns**. Names may receive a suffix; do not assume a URL before deployment finishes.
6. Check `/`, `/docs` and `/health/ready`. Create a fresh demo trip, add an expense, view its shares, record one external repayment and confirm balances change. Share the root URL with the recruiter after this verification.

The startup migration is a pragmatic single-instance free-demo choice because Render's dedicated pre-deploy command is a paid-service feature. Do not scale this startup arrangement to multiple migrating instances. A production/paid setup should use a separate migration job/pre-deploy step and a controlled seed policy.

## What a recruiter can try

- The seeded trip has Dinner INR 1,200 paid by Mohit, Taxi INR 600 paid by Rahul and Hotel INR 3,000 paid by Mohit.
- Initial total spending is **INR 4,800**. Each of three members consumed **INR 1,600**. Mohit paid INR 4,200 and should receive INR 2,600; Rahul owes INR 1,000 and Ankit owes INR 1,600.
- **Create a fresh demo trip** uses normal API calls to create a separate group with that same scenario. This avoids resetting another reviewer's work. The new group ID stays in the browser URL and can be shared directly.
- Add an equal/custom expense, inspect the saved shares, and correct a category.
- Change the personal-view member to distinguish consumption from cash paid. Date filters affect analytics; outstanding balances remain all-time.
- Open Settle up, compare fewer-payment and original-creditor modes, then record a full or partial repayment. This only records a synthetic external payment; it does not execute a real transfer.
- Create a blank trip and add existing/new people. Search finds groups, users, expenses and feature documentation. Some search results intentionally open the API result or documentation in another tab.

All stored data is shared across visitors, without authentication. Use synthetic data only. A fresh-trip creation consists of multiple API requests; a network failure can leave partial synthetic records and the UI explains this before creation. POST requests have no idempotency key, so do not blindly retry after an uncertain response. There is no global reset or deletion control.

## Free-tier lifetime

Render's [free-tier documentation](https://render.com/docs/free) states that free web services spin down after inactivity and free PostgreSQL databases expire **30 days after creation**. A cold start can make the first page slow. A free link is appropriate for a short review window, not an indefinite portfolio deployment. Check its status before sending it and plan renewal/redeployment or an explicitly approved paid database if the interview process extends beyond that date. There is no paid resource in the checked-in Blueprint.

The existing PDF guides are version-stamped to backend revision `c5a0a64`. They remain the reference for those financial APIs; this document describes the subsequent UI and Render deployment additions.

## Sources

- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render FastAPI deployment](https://render.com/docs/deploy-fastapi)
- [Render free-tier limits](https://render.com/docs/free)
