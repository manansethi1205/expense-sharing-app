# Verification record

Verified 2026-10-16 (Asia/Calcutta). The full pytest run used Windows 10, Python 3.13.0 and PostgreSQL 17.11. Container build/startup and live HTTP checks additionally passed on Linux/Python 3.12.14/PostgreSQL 17.11; Python 3.12 is also the declared minimum and CI target.

## Results

| Check | Result |
| --- | --- |
| Full pytest suite, real PostgreSQL | 83 passed, no warnings; audit regression 17.74 seconds |
| Pure unit suite | 50 cases, including 625 independent optimizer inputs and 100 seeded cycle graphs |
| Integration suite | 33 tests, separate migrated PostgreSQL schema per test |
| Simultaneous settlements | Separate connections: one 300.00 payment succeeds; another is rejected against a 400.00 debt |
| Exact optimizer | Greedy counterexample: five transfers versus exact four, including API execution of the exact plan |
| Migration/model comparison | No new upgrade operations detected |
| Upgrade/downgrade/re-upgrade | Passed in an isolated integration schema |
| Demo seed repeated | First run created three users/group/expenses; second returned the same group without duplication |
| Ruff lint / format | Passed |
| Docker Compose parsing | `docker compose config --quiet` passed |
| Docker image | Build passed, runtime requirements installed with hashes, nonroot app user |
| Compose startup | Database healthy -> migration exited successfully -> API healthy |
| Container live scenario | scripts.smoke_http passed: equal dinner, analytics, exact plan, payments, cleared balance, search |
| Container seed repeated | Created synthetic demo once; second invocation returned same group without duplication |
| Container platform | Linux, Python 3.12.14, PostgreSQL 17.11 |
| Real HTTP | Health, docs/OpenAPI, balances, suggestions, analytics, search all returned 200 |

Full suite command used a local test-only database URL with `pytest -q -p no:cacheprovider`. Disabling the optional cache plugin avoided a Windows sandbox ownership warning in the already-created cache directory; no tests or application warnings were suppressed. HTTPX was replaced with HTTPX2, supported by the installed Starlette TestClient, and Alembic's explicit path separator removed its configuration deprecation warning.

## Settlement benchmark

`python -m scripts.benchmark_settlements`, seeded random inputs, three cases per size. Time includes partition reconstruction. Memory tracing is a separate run because tracing changes timing. Measurements are local samples, not a worst-case or production SLA.

| Nonzero balances | Algorithm | Median ms | Maximum sampled ms | Peak traced MiB |
| --- | --- | ---: | ---: | ---: |
| 8 | Exact DP | 0.268 | 0.302 | 0.015 |
| 12 | Exact DP | 6.369 | 6.538 | 0.221 |
| 16 | Exact DP | 136.294 | 155.798 | 3.503 |
| 17 | Greedy | 0.038 | 0.046 | 0.003 |

The default threshold remains 16; configuration may lower it, never raise it above 16. Greedy metadata remains conservative even when a particular heuristic result happens to be optimal.

## Limits of this verification

- Docker was initially inaccessible, then became available from the authorized build command. The first image build hit a package download timeout; a longer pip read timeout allowed the hashed dependency install/build to complete. Image startup, migrations, health checks, smoke scenario, and repeatable seeding all passed.
- Public repository and its baseline successful CI were verified. It is now renamed/described as [expense-sharing-app](https://github.com/manansethi1205/expense-sharing-app). The fixed implementation is published via normal fast-forward pushes; [Actions](https://github.com/manansethi1205/expense-sharing-app/actions) shows the latest workflow result.
- To run genuine PostgreSQL tests while Docker was inaccessible, portable binaries were downloaded from EDB into ignored `.tools/` and a separate cluster initialized under ignored `.test-data/`. This is workspace verification infrastructure, not a second database backend or required project installation path.
- Native task processes (API on 8000 and PostgreSQL on 55432) were stopped after verification. The temporary Compose verification stack used API port 8001/database port 55433 and was then stopped. The normal project stack is started on the README's default ports for review; setup does not depend on ignored verification files.

## Audit regression evidence

- Aggregate direct and simplified suggestions of INR 20,000,000 now POST successfully after two individually valid INR 10,000,000 expenses. Exact metadata remains accurate.
- A debt plus an independent three-member cycle now suggests only the necessary direct payment; history retains the explanatory cycle after net clearing.
- Null characters in user/group names, descriptions, notes, and search return 422 instead of an unhandled database error.
- Category context covers bus/flight tickets and mixed hotel-dinner/flight descriptions. Multiword feature discovery covers custom splits/user creation/membership and other capabilities.
- SQL report totals retain personal-share semantics and show names; category/date/timezone filters and pagination cover all matching expenses beyond the top five.
- Coordinated report/writer test confirms REPEATABLE READ + READ ONLY, allows a concurrent expense write, and keeps all report totals on the earlier snapshot.
- Migration 0002/model comparison and rollback-safe downgrade refusal pass; large recorded settlements are preserved.
- The complete Postman collection's 21 HTTP requests run twice in an isolated schema with dynamic IDs. Pytest validates the requests/capture/status flow; the embedded JavaScript assertions are included for Postman, not evaluated as JavaScript by pytest.


## UI and Render preparation - 2026-10-16

- The expanded suite passed **87 tests** on the existing isolated local PostgreSQL setup (28.34 seconds). Ruff lint/format and Node JavaScript syntax checks passed.
- The Render-style startup migrated, seeded and served UI/API successfully on localhost:8010. The native server binds to the configured PORT. No fresh Docker image build is claimed for this step because Docker Desktop is stopped; CI builds the image after publication.
- In Brave, a fresh synthetic trip was created through the UI. A custom INR 1,000 expense saved exact shares 500/300/200; the split dialog confirmed them. A manual category correction persisted with source=manual. Feature search returned analytics documentation results.
- A synthetic INR 300 partial repayment reduced Ankit's suggestion from INR 1,800 to INR 1,500 and appeared in payment history. Baseline seed trip remained unchanged.
- At phone width, document scroll width equaled client width (375 pixels), with no page-level horizontal overflow. Viewport override was then reset. docs/ui-preview.png captures the real seeded overview.
- Render Blueprint and provider behavior were checked against official Render documentation. Cloud deployment is pending Render account access; no public service URL is fabricated.
