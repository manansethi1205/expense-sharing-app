# Final verification record

Verified 16 October 2026 (Asia/Calcutta). Application baseline: `72f1182`; API: `0.1.0`; Alembic head: `0002`. Documentation-only revisions package this final submission without changing the financial implementation.

## Final results

| Check | Result / scope |
| --- | --- |
| Complete local suite | **87 passed in 24.26 seconds**, no skips; Windows/Python 3.13.0/PostgreSQL 17.11 |
| Unit suite | **54 tests**, including exact accounting, independent optimizer checks, 100 seeded cycle graphs, provider URL normalization and UI asset serving |
| PostgreSQL integration | **33 tests**, each in a separate migrated schema; includes concurrency, migration safety and Postman replay |
| Ruff lint / format | Passed |
| Browser JavaScript | Node syntax check passed; 5 focused response checks for JSON success, structured 422, plain 500, HTML 502 and malformed success bodies |
| Application CI | [Run 38897558178](https://github.com/manansethi1205/expense-sharing-app/actions/runs/38897558178) completed successfully for `72f1182`; Python 3.12, PostgreSQL tests, Ruff, Compose validation and Docker build |
| Docker/Compose | Image build, migrations, healthy API/DB, repeatable seed and live scenario previously verified; current application image also built successfully in CI and on Render |
| Live Render API | Health, groups, analytics and settlement suggestions returned 200 after migrations |
| Hosted HTTP workflow | `scripts.smoke_http` passed against https://expense-sharing-app-inda.onrender.com, using a separate synthetic trip |
| Live seed | Three members, spending **4800.00**, two suggested repayments; the original seeded trip was preserved |
| Hosted platform | Free Render Docker web service; managed **PostgreSQL 18, Oregon**, verified in dashboard |
| UI/browser | Fresh trip, custom 500/300/200 split, saved split dialog, manual category correction, feature search and partial repayment verified |
| Mobile | At phone viewport width, page scroll width and client width both 375 px; temporary viewport override reset afterward |
| Final document package | Three refreshed PDFs (12/33/15 pages), every rendered page visually reviewed; 25 API operations covered; 21-request collection and both environments validated; explicit archive entries and SHA-256 hashes verified |

The hosted smoke check covers health/OpenAPI, user/group creation, membership, equal expense allocation, balances, personal analytics, exact suggestions, recorded repayments, settled-state verification and search. It leaves a separate synthetic smoke trip for inspection and does not reset the seed.

The final setup guide includes a screenshot captured from the public Render deployment. The screenshot and expected-value examples represent the verified starting scenario, not a promise that shared records never change.

## Reproduce the checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit -q
docker compose --profile test up -d --wait test-db
uv run --env-file .env pytest -q
```

Use `.env.example` to configure an isolated `TEST_DATABASE_URL`. It must be a PostgreSQL database ending in `_test` and differ from the application URL. The role needs CREATE SCHEMA privileges. Each integration case migrates a generated schema, then drops only that schema. Integration tests explicitly skip if no test URL is configured; a unit-only pass is not evidence that all 87 ran.

For a synthetic/disposable HTTP instance:

```sh
uv run python -m scripts.smoke_http --base-url http://localhost:8000
```

Changing the base URL to the hosted demo creates another synthetic trip and records its repayments. The final hosted run was verified, so repeated live writes are unnecessary merely to read the submission.

## Accounting and regression evidence

- Equal splits conserve exact paise; one-member expenses produce no self-debt. Custom splits reject duplicate, outsider, omitted and incorrect-total allocations.
- Saved participant shares remain unchanged after adding members. Payer consumption is included in analytics and excluded from self-debt.
- Concurrent settlement requests serialize on the group row; the second validates against updated debt. Group reports use a read-only repeatable-read snapshot that permits concurrent expense writing while keeping all report totals consistent.
- A proposed INR 20,000,000 payment can clear two individually capped INR 10,000,000 expenses. Downgrading migration 0002 refuses incompatible larger payments atomically rather than rewriting history.
- The exact solver matches an independent tiny oracle and improves the documented greedy counterexample from five transfers to four. Threshold routing and conservative optimality metadata are covered.
- Direct suggestions cancel cycles while preserving net positions and existing creditor relationships. Historical balance cycles remain explanatory rather than actionable new payments.
- Search tests cover escaped wildcards, scope intersection, multiword feature discovery, duplicate names and stable pagination. Category tests cover transport tickets, contextual phrases, ambiguity and manual override.
- The 21-request Postman sequence runs twice in an isolated schema with captured IDs. Pytest replays HTTP/capture/status behavior; it does not execute the collection's JavaScript assertions as JavaScript.
- Browser walkthrough: a custom INR 1,000 bill saved 500/300/200 shares; recording a synthetic INR 300 repayment reduced Ankit's suggestion from INR 1,800 to INR 1,500 and added a history entry. Those local walkthrough records are separate from the public seed.

## Settlement benchmark

These are previously measured local samples, not a worst-case or production SLA. `python -m scripts.benchmark_settlements` uses three seeded cases per size. Timing and memory tracing are measured separately.

| Nonzero balances | Strategy | Median ms | Maximum sample ms | Peak traced MiB |
| --- | --- | ---: | ---: | ---: |
| 8 | Exact | 0.268 | 0.302 | 0.015 |
| 12 | Exact | 6.369 | 6.538 | 0.221 |
| 16 | Exact | 136.294 | 155.798 | 3.503 |
| 17 | Greedy | 0.038 | 0.046 | 0.003 |

The configurable exact threshold defaults to 16 and can be lowered to zero, never raised above 16.

## Render deployment finding and resolution

The initial deployment first used a localhost DB URL, then connected successfully to Render PostgreSQL but still returned 500 for groups. Render logs showed `psycopg.errors.UndefinedTable: relation groups does not exist`. The manually created service had an empty Docker Command, so migrations had not run.

Set Docker Command to `python -m scripts.start_render` and Health Check Path to `/health/ready`. The startup migrated, seeded and served successfully. No credentials, existing region, database URL or paid compute choice was changed during that repair. The public dashboard and full HTTP workflow passed after deployment. The subsequent client error-message fix was deployed as `72f1182`.

## Verification limits

- Full isolated integration tests run against PostgreSQL 17; deployed PostgreSQL 18 passed the real HTTP scenario. This is not a claim that the full integration suite was rerun against the managed PostgreSQL 18 instance.
- Readiness checks database connectivity with SELECT 1, not migration revision or every table. Migrations-before-serving and actual group/expense requests verify the schema path.
- Browser checks cover the principal UI flows and one phone breakpoint, not every browser/device combination.
- The free Render host can sleep, and its free database expires 30 days after creation. Shared synthetic data may change through reviewer activity. This demo does not provide authentication or production uptime guarantees.
- Native PostgreSQL tools and authoring previews under ignored `.tools/`, `.test-data/` and `tmp/pdfs/` are workspace verification infrastructure, not setup prerequisites. The final ZIP excludes them and all credentials.
