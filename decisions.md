# Decision register

Status: proposal, 2026-10-16. No application implementation exists. User-confirmed requirements are marked **required**; proposed implementation decisions are marked **proposed**. Approval of this document is not assumed. Record future changes here with date, reason, alternatives, consequences, and links to implementation/tests.

| ID | Status | Decision and reason | Tradeoffs / alternatives |
| --- | --- | --- | --- |
| D01 | required | Discuss architecture before building application code. Create planning documentation now as explicitly requested. | Runtime setup/testing remains pending. |
| D02 | required | Use Python/FastAPI, matching the user's strongest backend experience. | Flask/Django bring no clear assignment benefit relative to familiarity. FastAPI is a framework; Python is the language. |
| D03 | proposed | Use PostgreSQL as the sole initial database. Strong relational integrity and serialized settlement validation fit the problem. | Service/container startup costs more than SQLite; avoid spending time testing two backends. |
| D04 | proposed | Do not use a graph database. Model membership relationally and compute settlement graphs in Python. | Less suitable for future deep social traversals, which are absent from requirements. No speculative speed claim. |
| D05 | proposed | SQLAlchemy 2 synchronous ORM with Psycopg 3 driver. | Explicit session lifecycle and mapping code; async can be added if measured throughput warrants it. |
| D06 | proposed | Alembic migrations from the first schema. | Adds one configuration step; makes schema setup/versioning reviewable. |
| D07 | proposed | Pydantic v2 for API schemas; pydantic-settings for config. | Separate ORM/API schemas require mapping but prevent persistence concerns leaking into requests. |
| D08 | proposed | Uvicorn serves the FastAPI application. | Additional runtime dependency; standard ASGI serving role. |
| D09 | proposed | Modular monolith: routers, services/queries, models, pure domain functions. | Fewer abstraction layers than a generic repository or microservices architecture; refactor only when needed. |
| D10 | proposed | One SQLAlchemy session per request; write service owns atomic commit/rollback. | Requires consistent transaction discipline; dependencies must not auto-commit separately. |
| D11 | proposed | Store money as BIGINT paise, use Decimal at API boundary, serialize decimal strings. | Conversion helpers and precision validation needed. Float arithmetic rejected. Numeric input retained for assignment compatibility. |
| D12 | proposed | INR-only groups initially; timezone defaults to Asia/Kolkata; event storage is UTC. | No FX or multi-currency support; reproducible date-boundary semantics. |
| D13 | required | Equal split includes all group members; payer never owes themselves. | Save payer share for consumption analytics while skipping payer debt edge. |
| D14 | proposed | Save explicit shares for every expense, snapshotting membership at creation. | Extra rows, but stable history, custom splits, and correct personal analytics. |
| D15 | proposed | Allocate indivisible paise by ascending user ID, quotient/remainder. | Reproducible and exact total; small systematic rounding bias. Do not claim perfectly equal fractions when impossible. |
| D16 | required | Support custom splits as an explicit bonus mode; equal remains default. | Universal equal-only interpretation conflicts with custom bonus; document mode separation for evaluator. |
| D17 | proposed | Custom split lists every current member once; allow zero shares. | More verbose than subset participants but preserves clear membership scope. |
| D18 | proposed | Require payer and settlement participants to be group members; enforce composite foreign keys. | Small schema redundancy in expense_shares.group_id enables stronger database checks. |
| D19 | proposed | Use six tables: users, groups, group_members, expenses, expense_shares, settlements. | Categories are a fixed enum; no extra category management table or mutable balance table. |
| D20 | proposed | Validate cross-row share total in the service and write atomically. | Database row checks alone cannot enforce the aggregate; tests are essential. A trigger is unnecessary initial complexity. |
| D21 | proposed | Derive balances from immutable records. No cached running balances. | Aggregation cost grows with history; avoids dual sources of truth at demo scale. |
| D22 | proposed | Separate direct obligations from group net positions and simplified plans. | More explanation required; prevents falsely equating net clearing with erasing historical pairwise cycles. |
| D23 | proposed | Greedy heap-based debtor/creditor matching with ID tiebreakers. | O(n log n) after aggregation, short deterministic plan, no guarantee of globally minimum transfers. |
| D24 | required | Record partial/full settlements as separate records. | External cash/UPI/bank payment is recorded, not executed or verified by this backend. |
| D25 | proposed | Validate settlements in explicit direct/simplified mode and store the mode. | Slightly larger API; distinguishes pairwise caps from net-position caps. |
| D26 | proposed | Lock the group row before membership additions or financial writes; revalidate within transaction. | Serializes writes per group, appropriate for small groups; prevents concurrent stale-cap/membership decisions. |
| D27 | proposed | Financial records immutable; category-only edits allowed initially. No deletion/removal routes. | Mistakes require a later reversal mechanism; avoids silently rewriting history. |
| D28 | proposed | Version API under /api/v1 and nest group resources. Use PUT for idempotent membership addition. | Routes differ from assignment's examples, which explicitly allow alternative design. |
| D29 | proposed | Use IDs in balances with names as labels, not names as JSON keys. | More verbose response; duplicate names remain unambiguous. |
| D30 | proposed | Bounded limit/offset pagination with deterministic order. | Simpler than cursors; concurrent inserts can shift pages, acceptable for demo. |
| D31 | proposed | Consistent error envelope; 404 absent resources, 422 invalid payloads, 409 invalid current state. | Need a framework validation exception handler and documented codes. |
| D32 | required | Unified search is the nominated mandatory enhancement, covering entities and product features. | Additional analytics/suggestions remain requested scope rather than replacing search. |
| D33 | proposed | SQL substring search plus static feature index, deterministic exact/prefix/substring ranking. | No typo tolerance or scalable arbitrary-substring guarantee. Defer pg_trgm/Elasticsearch. |
| D34 | proposed | Search filters intersect group/user scopes; escaped SQL wildcards; combined capped pagination. | Demo scoping is not authorization; efficient large-scale unified ranking would need more work. |
| D35 | proposed | Rule-based category suggestions using standard-library normalization/regex and versioned dictionaries. | Explainable and offline; limited semantic understanding; manual override and other fallback required. |
| D36 | proposed | Store category/source/rule on creation; manual choices win; GET never reclassifies history. | Old records do not improve automatically when rules improve, preserving stable reports. |
| D37 | required | Spending analytics cover personal share, paid amount, category and time/group breakdowns. | More queries/tests than a simple expense total; product clarity is valuable. |
| D38 | proposed | Exclude reimbursements from spending, show cash flow separately; avoid multiplied joins. | Must explicitly define each metric and date basis; current balance stays lifetime. |
| D39 | required | Unit tests include expense creation, balances, and validation; add API/database integration coverage. | Tests consume scope budget but target the highest weighted evaluation areas. |
| D40 | proposed | pytest plus HTTPX/TestClient, isolated PostgreSQL test database, pure domain tests without DB. | Database integration setup is heavier than SQLite tests but matches real constraint/locking behavior. |
| D41 | required | Docker support for reproducible submission. | Image builds add startup time; document exact verified commands after implementation. |
| D42 | proposed | Docker Compose API + PostgreSQL + single migration step and health checks. | More configuration than one container; migration must finish before API startup. |
| D43 | proposed | Ruff for lint/format; pyproject with pinned generated dependency lock/export. | One tool for code style; version pins/lock generated and verified during implementation, not invented now. |
| D44 | proposed | No authentication, frontend, queues, Redis, LLM, OCR, bank integration, or cross-group netting initially. | Focused backend demo; must not represent caller-supplied user IDs as verified identity. |
| D45 | required | Public GitHub repo named expense-sharing-app, with suitable description/README. | Remote creation awaits connected GitHub access; never claim a remote exists before confirmation. |
| D46 | required | Maintain this register and detailed flow.md alongside code changes. | Ongoing documentation cost; planned names are clearly distinguished from implemented functions. |
| D47 | proposed | Budget 12 hours across core, all bonuses, requested enhancements, tests, Docker/docs. | Tight target; no additional feature commitments without revisiting scope. |
| D48 | proposed | Defer CSV export, budget alerts, duplicate warnings, CI, and idempotent POSTs until scope allows. | Useful product improvements; idempotency especially requires payload binding, persistent keys, and concurrency tests. |
| D49 | proposed | Use ordinary local Git initialization and an initial documentation commit. | Does not create GitHub repository; local/remote completion are tracked separately. |
| D50 | proposed | Backdated expenses use current recording-time membership; no historical membership reconstruction. | Simple and deterministic but cannot model members joining/leaving before a backdated event. |
| D51 | proposed | Do not install runtime packages or create runnable Docker files during design discussion. | Keeps the user's no-build-first instruction intact; setup instructions explicitly remain planned. |
| D52 | proposed | Read each balance ledger as a single event projection; use a consistent snapshot for multi-query analytics. | Ordinary separate READ COMMITTED queries can observe different concurrent states; projection/CTE structure needs care. |
| D53 | proposed | Unified search accepts trimmed queries of 1-100 characters and offset <= 1000. | Bounds merged candidate retrieval; large-history navigation relies on entity-specific history filters. |

## Maintenance contract

For every new dependency, endpoint, table/constraint, algorithm, product behavior, assumption, or departure from this proposal, add a decision or update the affected row with a dated change entry. Record actual alternatives and material consequences; do not manufacture alternatives solely to fill a template. Link implementation/tests when they exist. Supersede old choices rather than silently deleting the reasoning.

## Pending choices and actions

- Discuss the proposed PostgreSQL choice and equal/custom split semantics before application implementation.
- Choose/document numeric maximum and concrete compatible dependency versions during implementation.
- Create and push the public GitHub repository after GitHub access is connected.
- Replace planned setup/flow details with verified commands and actual function references as code is built.
