# Code flow map

**Design only: every application filename/function below is proposed. None exists yet.** This file is the intended detailed implementation map. After implementation, keep it synchronized with actual paths, signatures, callers/callees, transaction boundaries, and failure behavior. Do not describe planned functions as runtime evidence.

## Planned layout and responsibility

```text
app/
  main.py                    create_app(), app = create_app()
  config.py                  Settings, get_settings()
  db.py                      engine/session factory, get_session()
  errors.py                  domain errors + HTTP exception handlers
  models.py                  six SQLAlchemy table mappings
  schemas/                   request/response models by feature
  api/                       users/groups/expenses/balances/settlements/search/analytics/categories
  services/                  feature operations and write transactions
  queries/                   feature-specific SQLAlchemy selects/aggregates
  domain/
    money.py                 to_minor(), format_money()
    splits.py                equal_shares(), validate_custom_shares()
    balances.py              direct_balances(), net_positions()
    settlements.py           suggest_transfers(), validate_settlement()
    categories.py            classify_description(), category rules/version
    search.py                feature directory and ranking helpers
migrations/                  Alembic environment and versioned migrations
tests/
  unit/                      pure money/split/balance/category/plan tests
  integration/               API + real PostgreSQL constraints/transactions
scripts/seed_demo.py          explicit repeatable synthetic seed command
```

Modules are grouped by responsibility without a generic repository base class. Schema modules distinguish equal/custom input using split_type. Update this map if implementation chooses fewer modules; the map must follow the code, not force empty layers.

## Startup and request entry points

```text
Docker Compose starts PostgreSQL -> database health check
  -> migration step: alembic upgrade head -> schema at current revision
  -> Uvicorn loads app.main:app
     -> module calls create_app()
        -> get_settings() validates configuration
        -> configure engine/session factory
        -> register error handlers
        -> register /api/v1 routers and health routes
```

Do not run ad hoc schema creation on each API request or auto-migrate independently in every worker. Liveness needs no DB query; readiness checks database connectivity. Shutdown disposes the engine.

Each route obtains `Session` from `get_session()`; dependency cleanup closes it. The dependency does not independently commit. Routers parse/serialize; services enforce business rules. Domain errors propagate to centralized handlers, which map them to the documented HTTP envelope. Write services use one transaction context; failure rolls back all writes.

## User creation and listing

```text
POST /users -> users_router.create_user(payload, session)
  -> UserCreate validates trimmed nonblank name and length
  -> users_service.create_user(session, payload)
     -> transaction -> insert User -> flush to obtain ID -> commit
  -> UserRead -> 201

GET /users -> users_router.list_users(filters, session)
  -> users_queries.list_users(q, limit, offset)
     -> parameterized name predicate + stable order + count
  -> Page[UserRead] -> 200
```

Duplicate names are permitted. GET user detail queries by ID and maps missing user to 404.

## Groups and membership

```text
POST /groups -> groups_router.create_group()
  -> GroupCreate -> groups_service.create_group()
     -> transaction -> insert Group(INR, timezone) -> commit
  -> GroupRead -> 201

PUT /groups/{group_id}/members/{user_id}
  -> groups_router.add_member()
  -> groups_service.add_member(session, group_id, user_id)
     -> transaction
     -> groups_queries.lock_group(group_id) [SELECT FOR UPDATE; 404 if absent]
     -> users_queries.require_user(user_id) [404 if absent]
     -> groups_queries.find_membership(group_id, user_id)
     -> if present return existing membership; otherwise insert -> commit
  -> MemberRead -> 200 existing / 201 new
```

Lock-before-read makes concurrent additions and expense member snapshots consistent. Group/member listing uses paginated queries. Group detail uses a count aggregate, avoiding one member lookup per result.

## Expense creation: equal and custom

```text
POST /groups/{group_id}/expenses
  -> expenses_router.create_expense(group_id, discriminated_payload, session)
     -> Pydantic: finite positive Decimal, precision, text length, split shape
     -> expenses_service.create_expense(session, group_id, payload)
        -> money.to_minor(payload.amount) [exact conversion, no float arithmetic]
        -> transaction
        -> groups_queries.lock_group(group_id)
        -> groups_queries.list_all_member_ids(group_id) [complete snapshot, not paginated]
        -> require nonempty members and payer membership
        -> equal mode: splits.equal_shares(amount_minor, sorted_member_ids)
        -> custom mode: splits.validate_custom_shares(member_ids, supplied_shares)
        -> verify all shares >= 0 and sum == amount_minor
        -> category explicit? choose manual
           otherwise categories.classify_description(description)
        -> insert Expense -> flush ID
        -> insert all ExpenseShare rows, including payer share
        -> flush constraints -> construct response -> commit
     -> ExpenseRead using money.format_money() -> 201
```

Custom validation converts every supplied share using the same exact money helper, checks unique member IDs, requires complete membership coverage, and checks exact total. Equal mode rejects a splits array. Category classification is pure and makes no network requests. If any insert fails, no partial expense survives. New members added later do not change saved shares.

## Expense history and category correction

```text
GET /groups/{group_id}/expenses
  -> require_group -> validate filters/time range
  -> expenses_queries.list_expenses(group_id, filters, page)
     -> join/load payer without per-row lookup
     -> order occurred_at DESC, id DESC; separate count
  -> page response

GET /groups/{group_id}/expenses/{expense_id}
  -> expenses_queries.require_expense(group_id AND expense_id)
  -> load saved shares and user labels -> detail response

PATCH /groups/{group_id}/expenses/{expense_id}/category
  -> validate supported category
  -> transaction -> lock group -> require matching expense
  -> update category, source=manual, rule=null -> commit -> response
```

No general expense PATCH means monetary history cannot be accidentally rewritten. Group scoping is checked in the query, not only in route syntax.

## Balance reads

```text
GET /groups/{group_id}/balances?view=direct|net
  -> balances_router.get_balances()
  -> balances_service.get_group_balances(session, group_id, view)
     -> require_group
     -> balances_queries.load_group_ledger(group_id)
        [one statement/CTE or equivalent consistent ledger snapshot]
     -> domain.balances.net_positions(expenses, shares, settlements)
     -> domain.balances.direct_balances(expenses, shares, settlements) if direct requested
     -> format amounts and user labels; is_settled = all net positions zero
  -> response
```

Ledger loading must produce a consistent read of expense and settlement records; avoid separate default READ COMMITTED queries observing different financial states. The simplest planned implementation reads a combined event projection in one SQL statement. Group writes are serialized, but ordinary reads still need this consistent snapshot design.

`direct_balances()` adds every nonpayer share as participant -> payer; settlements subtract sender -> receiver; reciprocal edges cancel. Negative pair totals reverse direction; zero edges disappear. A simplified payment can therefore produce a zero-net historical cycle. `is_settled` always uses net positions. Direct response includes an explanation flag/message when pairwise edges remain but the group is net-settled.

`net_positions()` credits paid expenses, debits personal shares, credits settlements sent, and debits settlements received. Include zero-position members in the net view. Assert/test conservation rather than rounding a discrepancy away. User-level balances reuse the same logic per group and do not invent cross-group obligations.

## Settlement suggestions

```text
GET /groups/{group_id}/settlement-suggestions?mode=simplified
  -> settlement_service.preview()
     -> balances_queries.load_group_ledger()
     -> net_positions()
     -> domain.settlements.suggest_transfers(copy_of_positions)
        -> creditor and debtor heaps with stable user-ID tiebreakers
        -> pop largest credit/debt
        -> emit min(credit, debt); update leftovers; repeat
     -> return advisory transfers + currency + mode + explanation
```

Direct mode returns nonzero direct debt edges as transfers; it may take more payments and preserve original creditor relationships. Both previews are reads and never insert settlements. Labels are loaded in a batch. Amount conservation and no-self-payment hold in both modes. Suggestions are not guaranteed globally optimal.

## Recording settlements

```text
POST /groups/{group_id}/settlements
  -> settlements_router.record_settlement()
  -> SettlementCreate validates positive exact money, IDs, mode
  -> settlements_service.record_settlement()
     -> transaction
     -> groups_queries.lock_group(group_id)
     -> require distinct members of this group
     -> balances_queries.load_group_ledger(group_id)
     -> net_positions() and/or direct_balances()
     -> validate_settlement(mode, sender, receiver, amount, current_ledger)
        direct: amount <= direct debt to receiver
        simplified: sender owes net, receiver is owed net, amount <= both magnitudes
     -> insert Settlement including mode and optional external-payment note
     -> flush -> commit
  -> SettlementRead -> 201
```

Never trust an earlier preview as an authorization to exceed current debt. A state conflict returns 409; rollback leaves the ledger unchanged. Holding the group lock until commit ensures a second concurrent settlement recalculates after the first. No external payment API is called. List settlements uses the history filtering/pagination pattern.

## Search

```text
GET /search?q=...&types=groups,expenses,features&user_id=...&group_id=...
  -> search_router.search() -> validated bounded query and page
  -> search_service.search()
     -> resolve optional scope intersection, return 404 for nonexistent IDs
     -> search_queries.search_entities() [parameterized escaped predicates]
        -> typed UNION projection + SQL match rank + stable global order/page
     -> domain.search.match_features() if requested
     -> combine feature/entity candidates and apply consistent global ranking/page
     -> return typed hits and total
```

Implement global pagination correctly: feature hits are a small finite set; fetch the top `offset + limit` ranked entity candidates, merge with all matching features, then slice the combined result. Entity count plus feature count supplies total. Cap offset at 1000 and trimmed query length at 1-100 characters for this initial algorithm. Scope restrictions apply in SQL before ranking. There is no per-type unlimited result fetch. Features expose API path templates such as `/api/v1/groups/{group_id}/settlement-suggestions`.

## Category classification

```text
classify_description(text)
  -> Unicode/case/punctuation normalization
  -> phrase rules, then whole-word keyword rules
  -> collect candidate categories and matched rule IDs
  -> apply explicit phrase precedence
  -> choose unique resolved category, otherwise other
  -> return category + source + rule/version/explanation
```

Manual input bypasses classification. Category reads simply return the stored assignment. Rule changes affect new records only, unless a future explicit reclassification operation is added.

## Analytics

```text
GET /users/{user_id}/analytics or /groups/{group_id}/analytics
  -> analytics_router -> validate entity, dates, timezone and bucket
  -> analytics_service.summarize()
     -> normalize local date interval to [UTC start, UTC end)
     -> analytics_queries.aggregate_share_spend() [personal consumption]
     -> analytics_queries.aggregate_paid_expenses() [expense once per payer]
     -> analytics_queries.aggregate_settlement_flows() [cash flow only]
     -> category/month/group breakdowns and totals
     -> compute percentages using exact money then display precision
     -> if current position included, obtain lifetime ledger separately and label it
  -> AnalyticsRead with currency, timezone, filters and metric definitions
```

Prefer a single aggregate query with CTEs or a consistent read-only snapshot transaction for related summary queries so concurrent writes cannot produce mismatched totals. Do not join expense totals through shares and then sum repeated expense amounts. Personal shares follow expense occurred_at; cash settlements follow settlement occurred_at. Empty intervals return zero totals and empty breakdowns. Every drill-down reuses the same filter semantics.

## Verification and documentation upkeep

Unit tests call domain helpers directly. Integration tests initialize an isolated PostgreSQL database using migrations, override session configuration, call routes with TestClient, and assert status/body plus persisted effects. Concurrency tests use separate sessions/connections and coordinated settlement attempts, not one sequential client masquerading as concurrent writes.

For each implemented endpoint, replace this proposal with actual paths/function names, add callers/callees and tests, document transaction ownership, and record material deviations in decisions.md. Before submission verify startup, migrations, seed, OpenAPI examples, Docker commands, and the full assignment scenario end-to-end.
