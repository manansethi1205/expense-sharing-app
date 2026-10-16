# Code flow map

This maps the implemented code. Names/paths below are actual references. Keep it synchronized with decisions.md when behavior changes.

## Module map

| Module | Responsibility |
| --- | --- |
| app/main.py | create_app(), global app, all HTTP handlers, health routes |
| app/config.py | Settings, cached get_settings(); environment/.env configuration |
| app/db.py | session_factory(), get_session(); normal request session; get_report_session() for read-only repeatable-read reports |
| app/errors.py | DomainError, envelope(), register_handlers() |
| app/models.py | Base, User, Group, Member, Expense, Share, Settlement, utcnow() |
| app/schemas.py | Strict input shapes, default_equal(), typed output/Page models |
| app/services.py | Transactions, group locking, CRUD, history, ledger/balances, settlements |
| app/search.py | Entity SQL, feature directory, ranking, scope, merged pagination |
| app/reporting.py | summarize(), breakdown(), consumption/cash-flow reports |
| app/domain/money.py | to_minor(), format_money(); exact paise conversion |
| app/domain/splits.py | equal_shares(), validate_custom_shares() |
| app/domain/balances.py | Transfer, direct_balances(), net_positions(), remove_circulation() |
| app/domain/settlements.py | Plan, exact_partition(), greedy_transfers(), suggest_transfers(), validate_settlement() |
| app/domain/categories.py | Classification, classify_description(), versioned keyword/phrase rules |
| migrations/env.py | Online/offline Alembic environment |
| migrations/versions/0001_initial.py | Initial schema |
| migrations/versions/0002_aggregate_settlement_limit.py | Remove the per-expense settlement cap; downgrade refuses incompatible existing payments |
| scripts/seed_demo.py | seed(); atomic repeatable synthetic data |
| scripts/benchmark_settlements.py | benchmark(); separate timing and memory measurements |
| scripts/smoke_http.py | smoke(base); assignment scenario against a real HTTP server |

Domain functions do not import FastAPI, ORM models, or database sessions. Queries live with feature operations; there are no unused repository/query/router layers.

## Startup and sessions

```text
docker compose up --build
  db -> pg_isready
  migrate -> alembic upgrade head
    migrations/env.py -> database URL -> engine -> revisions 0001 then 0002
  api -> uvicorn app.main:app
    app = create_app()
      supplied Settings or get_settings()
      session_factory() -> lazy engine + sessionmaker(expire_on_commit=False)
      register_handlers() -> include /api/v1 router -> health routes
```

Startup does not create tables or run migrations independently per API worker. Engine connections use pre-ping and a five-second connection timeout. Lifespan shutdown disposes the engine. Liveness requires no DB; readiness runs SELECT 1 and maps database errors to 503. Readiness tests connectivity, not schema revision.

`get_session(request)` yields one Session and closes it afterward. Closing rolls back uncommitted reads and releases locks. Mutating service functions own `with session.begin()` boundaries, committing success and rolling back exceptions. Dependencies never auto-commit. Write routes do not query first and accidentally open another transaction before calling a write service.

## Validation and errors

FastAPI validates parameters/Pydantic bodies before calling handlers. Input forbids unknown keys; text is trimmed/nonblank; body IDs are strict positive integers. Decimal amounts must be finite, at most two meaningful decimal places, and use distinct bounds: INR 10,000,000 per expense, signed BIGINT capacity per settlement. Input.postgres_compatible_text() and SafeText/reject_null_text() reject null characters in stored/query text before any database call. Expenses/settlements require positive amounts; custom shares may be zero. Timestamps require a timezone offset; GroupCreate validates an IANA timezone. ErrorRead/ErrorContent describe the common error envelope in OpenAPI; membership creation also documents its 201 alternative.

`schemas.default_equal()` adds split_type=equal before discriminated union validation. EqualExpense forbids a splits field; CustomExpense requires a nonempty Split list. `DomainError` becomes the common error envelope. RequestValidationError -> 422 with sanitized locations/messages; HTTPException -> same envelope; IntegrityError -> generic 409 without SQL/connection details. Missing resources -> 404; invalid custom split shape/total -> 422; invalid current membership/payment state -> 409. Transaction rollback occurs before error formatting.

## Users, groups, and membership

| Handler in main.py | Calls/behavior |
| --- | --- |
| create_user | services.create_user -> transaction -> User insert/flush -> commit -> UserRead |
| list_users | escaped case-insensitive name filter -> services.page -> count + ordered slice |
| get_user | services.require_user -> session.get(User) -> 404 if missing |
| create_group | services.create_group -> transaction -> Group insert/flush -> group_dict -> commit |
| list_groups | optional user existence/membership/name filters -> group_page -> count/slice + batched member counts |
| get_group | require_group -> group_dict with member count |
| add_member | services.add_member -> transaction -> require_group(lock=True) -> require_user -> existing membership or insert -> commit; 200 existing/201 new |
| list_members | require_group -> count + ordered Member/User join -> MemberRead page |

`require_group(lock=True)` selects FOR UPDATE. All group financial/category writes and membership additions acquire this lock before reading state. Duplicate membership additions remain idempotent under concurrency. Names may duplicate; IDs distinguish entities.

## Expense creation

```text
main.create_expense -> services.create_expense
  transaction:
    require_group(lock=True)
    member_labels() -> complete current membership, sorted by ID
    require payer in nonempty group
    to_minor(amount)
    equal_shares() OR validate_custom_shares(converted shares)
    explicit category? Classification(manual) : classify_description()
    insert Expense -> flush ID
    insert all Share rows, including payer/zero shares -> flush
    expense_dict() -> labels/shares/formatted money
  commit -> ExpenseRead, 201
```

`equal_shares()` uses quotient/remainder in paise; ascending IDs receive remainder paise. `validate_custom_shares()` rejects duplicates, missing/outsider IDs, negatives, and an incorrect total. Inserts are atomic. Historical shares never change with future membership. Backdated events use recording-time membership. Payer consumption is stored but does not become self-debt.

`classify_description()` v2 normalizes Unicode/case/punctuation, consumes matched phrase tokens only, and collects categories from all remaining context. Generic ticket words are weak fallback evidence, so bus/flight tickets resolve to travel. Unrelated conflicting categories yield other instead of being hidden by a phrase. Rule IDs remain bounded strings. Manual input bypasses classification; GET never reclassifies older saved rules.

## History and category correction

- `list_expenses` -> require_group(read=True) -> group/payer/category/description/date filters -> expense_page -> page count/slice -> batch member labels and shares -> expense_dict with supplied context, avoiding per-expense lookups.
- `get_expense` -> shared group lock -> require_expense checks group AND expense IDs -> expense_dict with payer and saved shares.
- `correct_category` -> service transaction -> exclusive group lock -> require matching expense -> category/source=manual/rule=null -> flush/serialize -> commit.

`date_bounds()` converts local inclusive from / exclusive to dates to UTC using the group's timezone; invalid intervals return 422. `filter_dates()` applies SQL bounds. No financial edit/delete endpoint exists.

## Ledger and balances

```text
main.group_balances -> services.get_balances -> balance_data
  require_group(read=True) [FOR SHARE]
  member_labels()
  load_ledger() [one UNION ALL statement]
    Expense JOIN Share excluding payer share -> obligation Transfer rows
    Settlement -> recorded payment Transfer rows
  net_positions() + direct_balances()
  transfer_dict() / formatted positions -> BalanceRead
```

Shared locks keep membership/labels/financial records consistent through request completion, allowing other readers. The single ledger statement observes shares and settlements at one READ COMMITTED snapshot. Net positions subtract debtor obligations/add creditor obligations; settlements credit sender/debit receiver. Net total remains zero.

`direct_balances()` aggregates sorted user pairs, nets reciprocal obligations, subtracts settlements, reverses negative edges, and omits zero/self edges. Simplified transfers can leave historical zero-net cycles. `is_settled` uses net positions; direct reads explain any residual cycle. Preview and recording request no further payments for a net-settled group.

`main.user_balances()` -> require_user -> sorted membership group IDs -> get_balances per group -> retain only requested user's positions/direct edges. No cross-group netting is introduced.

## Settlement planner and exact DP

```text
main.settlement_suggestions -> services.preview_settlements -> balance_data
  direct mode: remove_circulation(direct edges), strategy=direct,
               objective=preserve_original_debts, guarantee=false
  simplified: suggest_transfers(positions, configured threshold)
    require sum==0 and threshold in 0..16; discard zero positions
    active count <= threshold:
      exact_partition() -> greedy_transfers() per reconstructed subset
      strategy=exact, guarantee=true
    otherwise greedy_transfers(all active): strategy=greedy, guarantee=false
  transfer_dict() -> labels + amounts
  PlanRead: mode, strategy, objective, guarantee, count, transfers, explanation
```

`exact_partition()` sorts IDs and precomputes sums for each bitmask. For each nonempty mask choose removal bit i maximizing best[mask without i], breaking ties by ID; add one if sum[mask]==0 and save parent. Follow parents, reverse removed IDs, and close subsets at zero running sums. This maximizes zero-sum prefix closures over all orderings, equivalently the maximum number k of disjoint zero-sum blocks. With n nonzero positions, minimum transfers is n-k. Time O(n*2^n), space O(2^n).

`greedy_transfers()` uses negative-sized creditor/debtor heaps with ID tiebreakers, emits min(debt,credit), and reinserts leftovers. It changes only local heaps. Within a maximum zero-sum partition it reaches n-k total transfers; as a global fallback it offers <=n-1 transfers without a minimum-count guarantee. The empty plan is exact. Callers cannot force exact computation above the server's bound.

`remove_circulation()` builds a sorted positive-edge adjacency graph, finds a directed cycle with iterative DFS, subtracts its minimum edge amount, and repeats until acyclic. Every pass removes at least one edge; deterministic ID order stabilizes the result. Net positions and existing creditor relationships are preserved. An acyclic nonempty residual cannot be zero-net, so replaying the advertised direct payments never hits the already-settled guard before completion. Historical balance edges remain unchanged. Worst-case cancellation cost is O(E*(V+E)), bounded by one edge removal per pass.

## Settlement recording/history

`main.record_settlement()` -> service transaction -> exclusive group lock -> member_labels -> load_ledger -> net_positions/direct_balances -> reject net-settled group -> to_minor -> validate_settlement -> insert/flush Settlement -> settlement_dict -> commit -> 201.

Validation requires positive payment between distinct members. Direct cap is outstanding pairwise debt. Simplified cap is min(sender's net debt, receiver's net credit), with the required signs. Earlier previews are never treated as current validation state. Concurrent requests serialize on the group lock, so the second reads newly committed debt. This records external payments; it executes no cash/bank/UPI operation. `list_settlements()` uses a shared lock, date filters, page(), batched labels, and settlement_dict(labels=...).

## Search

`main.search()` -> search.search -> validate query length 1..100/types/offset<=1000 -> require scope IDs -> intersect user groups/group filter -> entity_query/rank -> parameterized UNION ALL users/groups/expenses -> count + top offset+limit entity candidates. Rank is exact, prefix, substring, then type/ID. Wildcards %/_ are escaped literals.

The finite FEATURES directory is matched in Python, with pipe-separated multiword aliases for every exposed product capability. Merge all feature hits with capped SQL candidates, sort consistently, slice one global page, and remove internal rank fields. Entity IDs return integers; feature keys remain strings; paths are API templates. User scope includes self/group peers; explicit group scope intersects it. Scope filters are not authentication.

## Analytics and categories

`main.user_analytics()` / `group_analytics()` -> ReportDB dependency `get_report_session()` -> connection isolation REPEATABLE READ -> transaction + SET TRANSACTION READ ONLY -> reporting.summarize -> report_scope() -> validate IDs/membership/timezone/date bounds -> filtered expense/spending CTEs -> SQL aggregates. The scope's first SELECT establishes the snapshot; every total/breakdown/top-five query uses the same snapshot without FOR SHARE locks.

User consumption sums own saved shares; paid sums own expense payments. Group spending counts each expense once; member breakdown sums shares. Categories/local calendar months/groups group consumption. Settlement cash flows are separate; cash outflow=paid+sent-received. Pre-join expenses do not become personal zero-value drill-down entries. breakdown() executes aggregate key/label/amount SQL and formats percentages with a zero-total rule. Group/member names are selected through joins. expense_rows() loads a bounded ordered page with group/payer labels. Largest expenses uses amount-descending top five; drilldown_path preserves summary filters. Lifetime balances stay at their own endpoint.

`main.user_expense_drilldown()` / `group_expense_drilldown()` use the same ReportDB/report_scope snapshot and personal/group spending CTE. expense_drilldown() adds the category predicate, counts SQL rows, and calls expense_rows() with amount/date sorting and bounded limit/offset. No full expense-ID array or full-history rows are loaded into Python. Read-session close releases the snapshot and SQLAlchemy restores the pooled connection isolation. Normal financial writes keep their existing READ COMMITTED/exclusive group-lock discipline. `/categories` exposes versioned rules without database access.

## Seed, verification, and CI

`seed_demo.seed()` -> engine/session factory -> transaction + PostgreSQL advisory lock -> existing demo group? return same ID -> otherwise insert users/group/members, three categorized expenses, and exact shares -> commit -> dispose engine. Module entry prints IDs. This avoids duplicates and partial seeds.

`benchmark()` generates three seeded cases each for 8/12/16/17 nonzero positions, times complete planning without tracing, and measures peak traced memory separately. It writes ignored benchmark-results.json; measurements are samples, not a worst-case bound.

`smoke_http.smoke(base)` uses standard-library urllib/json to issue real network requests: health/OpenAPI -> users -> group -> members -> equal dinner -> direct balances -> personal analytics -> exact plan -> record each transfer -> verify settled -> search. It returns a compact result and leaves synthetic records for inspection. The module accepts --base-url so Docker and local servers can both be verified.

Unit tests call domain helpers and input schemas. The tiny independent optimizer oracle recursively explores transfers, not the DP recurrence. `tests/conftest.py` requires a PostgreSQL test database ending in _test, creates a random schema, migrates it, builds create_app(Settings(...)), and runs TestClient requests. Cleanup disposes engines and drops only the generated schema. Concurrent settlement tests use separate connections/barriers. Migration tests compare models and execute downgrade/re-upgrade.

CI installs locked Python 3.12 dependencies, runs Ruff and the full suite against PostgreSQL, validates Compose, and builds Docker. Local results/limits are recorded in docs/verification.md; the public repository has a verified baseline CI run and subsequent pushes run the same checks. docs/verification.md links the current Actions status.

## Submission documentation

`output/pdf/` contains separate setup, API and database-schema guides stamped with the source code revision, API version and migration head. Endpoint parameters/response models come from `app.openapi()`; table columns/constraints/indexes come from `Base.metadata`. Authored sections explain accounting, validation and transaction behavior around those generated references. These static artifacts do not run in the application's request path.

The identical Postman collection copy under `output/` uses the same sequence/capture scripts as `docs/expense-sharing.postman_collection.json`. The ZIP bundles that collection and the three PDFs. PDF authoring/rendering tools are separate from backend runtime dependencies; every rendered page is visually reviewed before delivery. Regenerate the PDFs and refresh the copied collection/bundle whenever the documented API or schema changes.
