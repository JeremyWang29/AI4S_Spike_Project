# Acceptance evidence register

## M0 implementation evidence — 2026-09-15

| Check | Observed result | Limit |
|---|---|---|
| Django full suite | 52 discovered; 48 passed, 4 PostgreSQL race tests skipped | SQLite final functional run after review patches; PostgreSQL gate remains open |
| Frontend tests | 25/25 passed | Production scope/account controllers: failure retention, stable retries, disposal fences, draft restoration, same-project revisions; preview guards |
| Frontend production build | Passed | No deployment inference |
| Migration drift | No changes detected | Model/migration consistency |
| Fresh temporary SQLite migration | All migrations applied successfully, including M0 backfill | Existing user database untouched |
| Browser desktop and 390px | Login/create, empty confirmation rejection, eleven answers, candidate decisions, save/reload, confirm V1, successor V2/history, two-tab 409 preserving local edit, logout/login restoration passed | Synthetic isolated local database, manual walkthrough |
| Historical upgrade and replay | Migrated pre-M0 project/scope/receipt from projects 0002 through latest; owner actor backfilled, replay changed no revision/event/storage | Synthetic database; not a live cutover |
| Review-patch browser rerun | Unsaved answers survived step navigation; projection rebuild V5→V6 then scope save V7 succeeded without false 409; no console errors | Isolated walkthrough database; test object text restored |
| PostgreSQL locking | Four dedicated tests implemented (create, redeem, scope-write and login/revoke races) | UNVERIFIED: Docker Desktop backend failed during inference manager initialization/socket cleanup |
| Container empty-volume startup / migration failure ordering | Compose dependency and entrypoint tooling implemented | UNVERIFIED: daemon unavailable; no production migration performed |
| Compose static configuration | Development, acceptance and pilot configurations passed `config --quiet` | Docker config credential file warning under sandbox; no daemon startup claim |
| Production/pilot, off-host backup and licensed real research | Not executed | Operational prerequisites remain |

The M0 tests include fault injection after each project creation write, unchanged replay/changed-payload conflicts, researcher/owner actor-scoped keys, administrator and reviewer negatives across reads and commands, file deny-by-default, fresh-session scope restoration, immutable history and linked-only invalidation, missing-projection rebuild with unrelated-event watermarks and replay deduplication, expiring/reissued/replayed credentials, password validation, session revocation, failed-login limits, malformed counts/AST, forged qualification/reward rejection and fenced task recovery. Later-stage domain fixtures remain exploratory and do not count as production M1–M6 implementation.

Statuses separate static review, automated implementation tests, and real-pilot evidence. A missing real-world dependency remains `UNCONFIGURED` or `UNVERIFIED`; it is never converted into a pass.

| Scope | Automated evidence | Real evidence | Current status |
|---|---|---|---|
| S01–S04, S06–S10, S12, S14–S17, S19 | `platform/tests/`（当前自动化规则与API覆盖） | Required for actual platform data | IMPLEMENTED / PILOT_PENDING |
| S05, S07, S11, S13, S18 | Domain contract represented; persistent workflows incomplete | Required | PARTIAL |
| T01–T09, T12, T14, T17, T19–T20 | Contract and scenario tests | Fault injection still required | PARTIAL |
| T10, T11, T21 | Protocol documented in source architecture | Raw capacity and off-host recovery records absent | UNVERIFIED |
| Real ferroptosis/radioresistance pilot | Project fixture and dependency behavior only | Licensed exports, reviewers, and measurements absent | PILOT_PENDING |

## Evidence rules

Each execution record must identify the actor, object/version, input fingerprints, event order, expected and actual output, UTC time, and executor. Restricted text and model material must stay in the project evidence domain. CI receives synthetic or de-identified identifiers only.

自动化测试通过只证明当前实现的规则与接口行为，不代表整组场景的生产故障注入或真实材料验收已经完成。正式状态以本表的 `Current status` 和对应原始证据为准。

## Review closure and remaining M0 gates

All 16 independent-review findings (including duplicate reports) were triaged and patched. Historical approvals are presented as exploratory while stored history remains intact; retries bind the task target; inactive memberships can be removed; frozen concepts have real dependency edges; login persists its session under the account lock; internal errors have safe correlated logs. Frontend handlers fence disposed components and retain uncertain-request keys and per-project in-memory edits.

**Implementation and local verification are complete; formal M0 acceptance remains pending.** The four PostgreSQL concurrency tests must execute without skips on an isolated PostgreSQL database. Container verification must also demonstrate empty-volume startup and refusal to start API/worker after migration failure. Docker Desktop initialization failure prevented those checks; no environment gate is waived. The spec remains in review until these prerequisites pass.
