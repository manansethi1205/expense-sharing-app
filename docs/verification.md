# Verification record

Verified 2026-10-16 (Asia/Calcutta). The full pytest run used Windows 10, Python 3.13.0 and PostgreSQL 17.11. Container build/startup and live HTTP checks additionally passed on Linux/Python 3.12.14/PostgreSQL 17.11; Python 3.12 is also the declared minimum and CI target.

## Results

| Check | Result |
| --- | --- |
| Full pytest suite, real PostgreSQL | 51 passed, no warnings; final regression 9.60 seconds |
| Pure unit suite | 37 cases, including 625 independent small optimizer inputs inside one exhaustive test |
| Integration suite | 14 tests, separate migrated PostgreSQL schema per test |
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
- GitHub is not connected, so neither remote repository creation/push nor a remote CI run is claimed.
- To run genuine PostgreSQL tests while Docker was inaccessible, portable binaries were downloaded from EDB into ignored `.tools/` and a separate cluster initialized under ignored `.test-data/`. This is workspace verification infrastructure, not a second database backend or required project installation path.
- Native task processes (API on 8000 and PostgreSQL on 55432) were stopped after verification. The temporary Compose verification stack used API port 8001/database port 55433 and was then stopped. The normal project stack is started on the README's default ports for review; setup does not depend on ignored verification files.
