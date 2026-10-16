# Final project submission

Expense Sharing App / Fairshare UI | 16 October 2026

## Review links

- **Live application:** https://expense-sharing-app-inda.onrender.com/
- **Interactive API documentation:** https://expense-sharing-app-inda.onrender.com/docs
- **Source repository:** https://github.com/manansethi1205/expense-sharing-app
- **Verification:** [docs/verification.md](docs/verification.md)
- **Download all recruiter documents:** [final submission ZIP](output/expense-sharing-final-submission.zip)

Application baseline `72f1182` is verified by [GitHub CI](https://github.com/manansethi1205/expense-sharing-app/actions/runs/38897558178). API version is `0.1.0`; Alembic schema head is `0002`. Later documentation-only commits package this final edition without changing financial behavior.

## Suggested five-minute walkthrough

1. Open the live application and select **Goa Trip (demo)**. If the free host is asleep, allow roughly a minute for startup.
2. The three bills are Dinner INR 1,200, Taxi INR 600 and Hotel INR 3,000. Total spending is **INR 4,800**, and each member's allocated consumption is **INR 1,600**.
3. Switch the personal view: Mohit paid INR 4,200 and receives INR 2,600; Rahul paid INR 600 and owes INR 1,000; Ankit owes INR 1,600.
4. Use **Create a fresh demo trip** before making changes. Add an equal/custom expense, inspect **View split**, and correct its category.
5. In **Settle up**, inspect the proposed payments and record a synthetic partial repayment. Balances and payment history update from saved backend data.

Existing shared groups may have changed through other reviews. A fresh demo trip recreates the starting scenario. The Postman collection intentionally uses a separate dinner-only scenario, where Rahul and Ankit each owe Mohit INR 400.

## Requirement coverage

| Assignment area | Delivered |
| --- | --- |
| Users and groups | Create/list/detail APIs; idempotent membership; member listing |
| Expense recording and history | Positive amounts, valid group and payer, all-member equal default, saved shares, no self-debt; filters and pagination |
| Balances | Structured direct debts and signed net positions; exact integer-paise arithmetic |
| Mandatory product enhancement | Unified search across users, groups, expenses and feature aliases |
| Additional product features | Explainable category inference/manual correction; personal/group consumption and cash-flow analytics; settlement suggestions |
| Optional bonuses | Recorded partial/full settlements, explicit custom splits, unit/integration tests and Docker support |
| Delivery | Public GitHub, responsive live UI on Render, README, API/setup/schema PDFs, architecture/decisions/flow documentation and Postman |

## Engineering choices to review

PostgreSQL's relational constraints and atomic writes fit memberships, expenses and allocation snapshots. Saved shares preserve historical obligations when group membership changes. Integer paise prevents floating-point drift. Group row locks serialize concurrent financial mutations; SQL reports use read-only repeatable-read snapshots without blocking expense recording.

Settlement suggestions use an exact zero-sum partition optimizer for at most 16 nonzero balances, with a deterministic greedy fallback above that threshold. Response metadata states whether a minimum transaction count is guaranteed. Direct mode cancels circulation while preserving creditor relationships. The threshold bounds exponential computation rather than hiding an unbounded optimization cost.

The final local suite has **87 passing tests**: 54 unit and 33 PostgreSQL integration. The deployed application passed the real HTTP expense-to-settlement smoke workflow. See verification evidence for scope and limits.

## Documents included

- Setup Instructions PDF: hosted walkthrough, local setup, Docker, environment, tests and Render deployment/troubleshooting.
- API Documentation PDF: all 25 HTTP operations, model fields, examples, validation, money/date conventions and live UI/API behavior.
- Database Schema Explanation PDF: all six tables, relationships, constraints, indexes, transaction rules, migrations and hosted persistence.
- README, decisions.md and flow.md: architecture, choices/tradeoffs, assumptions and actual function flow.
- Postman collection plus Local/Render environments, offline OpenAPI JSON, deployment guide and verification record.

## Scope and hosting limits

The live service is an assignment demo with shared synthetic data and no authentication. It records payments completed externally; it does not send money. It supports INR only. Financial edits/deletion, idempotency keys, membership removal and currency conversion remain deliberate future work.

Render uses a free web service and a managed PostgreSQL 18 database in Oregon. The local/test image and reusable Blueprint use PostgreSQL 17; both share the same schema. Free web services can sleep, and free databases expire **30 days after creation**. This is a short review-window deployment, with reproducible local setup available if the hosted window expires. [Hosting limits](https://render.com/docs/free)
