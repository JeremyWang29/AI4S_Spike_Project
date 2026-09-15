---
title: 'M0：入口与范围硬化'
type: 'feature'
created: '2026-09-14'
status: 'in-review'
baseline_commit: '4af37cba1bf82d4813091743f01c0c29ef51b261'
route: 'dispatch'
review_loop_iteration: 1
implementation_status: complete
acceptance_status: pending-environment
context:
  - '{project-root}/outputs/architecture/architecture-ai4s-2026-09-09/ARCHITECTURE-SPINE.md'
  - '{project-root}/outputs/development-plan/ai4s-staged-development-20260911/分阶段开发计划.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Project creation persists, but scope interviews remain browser previews. Identity, recovery, deployment and legacy command boundaries do not satisfy M0.

**Approach:** Complete all M0 deliverables, preserving existing files and the preview UI. Make authorized project scope edits durable, versioned, recoverable and auditable.

## Boundaries & Constraints

**Always:** Use project-owned commands, transactions, actor-scoped idempotency, revision guards, ordered events and explicit dependencies. Keep confirmed content immutable. Invite activation never grants project membership automatically. Administrators have no implicit private-project access. Use fixed interview questions while AI/KG providers are unavailable; show availability honestly.

**Never:** Delete existing projects, promote browser preview state into scientific facts, trust submitted approval booleans, issue rewards from submitted reviewers, or implement M1–M6 production workflows. Production deployment and live data migration require a separate operational run; this change supplies and tests additive migrations and deployment tooling.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Create | Same actor/key/payload repeated | One complete project and event chain | Changed payload: 409 |
| Scope | Four groups, candidate decisions, resolved conflicts | Explicit confirmation freezes a version | Incomplete: 422; stale revision: 409 |
| Edit | Previously confirmed scope | New draft; dependent applicability invalidated | Preserve previous content and decisions |
| Access | Nonmember, including administrator | No project, count, task or file disclosure | Uniform 404 |
| Credentials | Expired/replayed token or repeated failure | No activation/reset; bounded login attempts | Generic denial or 429 |
| Recovery | Missing projection or failed task | Rebuilt state or authorized retry action | No automatic external paid retry |
| Legacy | Forged approvals, malformed counts/AST | No formal qualification or reward | Structured 4xx / unconfigured blocker |

</frozen-after-approval>

## Code Map

- `platform/backend/modules/projects/views.py`: creation transaction is reusable; `_project` is owner-only; `_mutate` lacks events; legacy commands trust requests.
- `platform/backend/modules/projects/models.py`: reuse Project, ResearchConstraint, WorkflowProjection, CreateRequest and MutationRecord. WorkflowState is not scientific provenance.
- `platform/backend/modules/execution/models.py`: Event/Outbox/Inbox/Task provide persistent primitives; stream ordering differs from project revision.
- `platform/backend/modules/identity/__init__.py`: preserve the authorization intersection; reconcile its old role names with the four-role matrix.
- `platform/frontend/src/App.vue`, `workflow.js`, `api.js`: replace real-project scope storage and actions; preserve isolated demo behavior and visual structure.

## Tasks & Acceptance

**Execution:**
- [x] `platform/backend/modules/identity/{models,services,views,apps}.py`, `migrations/`, `config/{settings,urls}.py` — implement expiring single-use hashed invitations/reset tokens, password validation, login throttling, session revocation and audit. Provide administrator issuance and user redemption interfaces; no automatic email sending.
- [x] `platform/backend/config/errors.py`, `modules/projects/management/commands/create_test_user.py` — ensure view exceptions return structured errors; restrict test-account creation/reset to development.
- [x] `platform/backend/modules/identity/authorization.py`, `modules/projects/views.py` — centralize membership checks for list/detail/commands/tasks. Owner manages members and scope; researcher edits scope; reviewer reads assigned projects and performs only assigned review actions; administrator manages accounts, not private content. File requests deny unless both project and material authorization exist.
- [x] `platform/backend/modules/projects/{models,services,views}.py`, `migrations/`, `modules/knowledge/{models,services,apps}.py`, `migrations/` — persist interview answers, four fixed groups, candidate provenance/decisions, conflict records and immutable confirmed concepts. Validate years, required fields, duplicate/include-exclude conflicts and explicit resolution notes; manual semantic review remains recorded, not an AI certainty claim.
- [x] `platform/backend/modules/projects/services.py`, `modules/execution/{models,services}.py`, migrations — atomically create dependencies/events/outbox; preserve version history; invalidate only linked downstream applicability. Rebuild projections from authoritative objects/events with watermarks and replay deduplication. Expose failed-task recovery without stale writes.
- [x] `platform/backend/modules/projects/views.py`, `modules/projects/validation.py` — bound input sizes and validate types, enums, finite nonnegative counts, references and AST depth. Reject fabricated formal qualification, decision readiness and rewards until authoritative later-stage records exist; keep exploratory results explicitly nonformal.
- [x] `platform/frontend/src/{App.vue,api.js,workflow.js}`, `components/{LoginPanel,ScopePanel,AccountPanel}.vue` — add account redemption/session controls and member administration; load/save real scope via API with pending/error/conflict recovery, editable candidate replacements and version history. Refetch on project change; stale responses cannot overwrite another project. Never show browser-only edits as saved.
- [x] `platform/backend/config/{settings,celery}.py`, `platform/backend/Dockerfile`, `platform/deploy/{compose.yaml,.env.example}`, `platform/backend/entrypoint.sh` — fail closed outside development without secrets; require secure same-origin sessions; isolate database/files/queue per environment. Run one migration service before API/worker and fix worker runtime path.
- [ ] `platform/tests/{contracts,scenarios}/test_m0.py`, `platform/frontend/test/` — cover the matrix, privilege negatives, transaction fault injection, two-session conflicts, token races and stale task results. Exercise PostgreSQL locking separately from SQLite functional tests.
- [x] `platform/docs/{OPERATIONS,ACCEPTANCE}.md`, `platform/docs/openapi.yaml` — document commands, role matrix, environment/migration recovery, test evidence and remaining operational prerequisites.

**Acceptance Criteria:**
- Given a saved scope, when the browser closes and a fresh session opens, then answers, decisions and versions restore from the server.
- Given a create transaction interrupted after any object write, when rolled back and retried, then no partial project, duplicate event or request remains.
- Given a confirmed version with dependent fixtures, when a successor is saved, then only reachable current applicability changes and old approval content remains unchanged.
- Given missing projection rows, when rebuilt twice, then state and event watermarks match without duplicate effects.
- Given role and credential fixtures, when every read/mutation path is exercised, then unauthorized paths disclose nothing and key operations have actor/time/object audit records without secrets.
- Given empty deployment volumes, when migration succeeds, then API/worker can start; failed migration or missing nondevelopment keys prevents startup.

## Implementation Notes

- 2026-09-15: Implementation and independent-review patches complete. Final local evidence: 52 backend tests discovered, 48 passed / 4 PostgreSQL-only skipped; 25 frontend tests passed; production build and migration drift check passed. Pre-M0 migration/replay and browser draft/revision regression checks passed. PostgreSQL concurrency and container startup gates remain unverified because Docker Desktop fails to initialize; test execution task stays open and spec status stays in-review. M0 is not formally released.

## Spec Change Log

## Review Triage Log

| Finding | Verdict / route | Evidence |
|---|---|---|
| B1 cross-task receipt | high / patch | _mutate hashes action/body but retry target lives only in URL. Bind task target without changing API. |
| B2 legacy formal claims | high / patch | Status still exposes stored pre-M0 approvals without a current nonformal annotation. Preserve historical storage and neutralize current response claims. |
| B3 malformed evidence status | medium / patch | List/dict status reaches set membership and raises TypeError. Validate consumed fields. |
| B4 concurrent login/revocation | high / patch | Session persistence occurs after lock-free login while revocation locks user and enumerates rows. Serialize login and persist its session inside the same user lock. |
| B5 self-action revision conflict | medium / patch | Account commands update parent revision while scope caches old revision. Propagate confirmed same-project revisions without replacing dirty answers. |
| B6 scope preview restoration | medium / patch | initialPreview always creates unconfirmed scope for real projects, including preview reset. Derive persisted status from server metadata. |
| B7 unsaved navigation | medium / patch | ScopePanel unmount destroys dirty answers on step/project change. Preserve in-memory drafts or require explicit discard. |
| B8 account retry keys | medium / patch | Each click generates a new key after uncertain outcome. Retain attempt payload/key through retry. |
| B9 concept dependency | high / patch | freeze_concepts returns actual ConceptVersion without a scope-to-concept edge, so traversal cannot reach it. Add edge atomically and test real descendant. |
| B10 opaque exceptions | medium / patch | Unexpected errors become generic 500 without correlated logging. Log a safe exception classification and trace, without request bodies/secrets. |
| V1 component regression gap | medium / patch | Tests exercise helper booleans only; actual response-handler guard removal is undetected. Add controlled async component/controller execution. |
| V2 historical migration gap | medium / patch | Empty-database migrations never exercise actor backfill. Add pre-M0 data migration and API receipt replay scenario. |
| E1 stale AccountPanel event | high / patch | Keyed unmount retains old props; id equality inside old instance still succeeds and emits unscoped revision. Add disposal and parent project-id checks. |
| E2 cross-task receipt | high / patch | Same defect as B1; retain separate finding record and patch together. |
| E3 inactive member removal | medium / patch | Active-user lookup occurs before remove; inaccessible member cannot be revoked. Remove membership independently of activation. |
| E4 malformed platform | medium / patch | platform list reaches dictionary lookup. Validate platform/type before lookup and cover legacy input matrix. |

## Review Resolution

- B1/E2: task target bound into action fingerprint; cross-task receipt test passes.
- B2: historical state/receipt response sanitized without overwriting storage; legacy migration replay test passes.
- B3/E4: malformed fields and execution/import consistency checked; structured 422 cases pass.
- B4: session persisted inside account lock; PostgreSQL login/revoke regression implemented, environment execution pending.
- B5/B6/B7/B8/E1: production controllers integrated; revision sync, persisted status, per-project drafts, stable keys and disposal fencing pass automated/browser checks.
- B9: real concept dependency and invalidation tested.
- B10: safe correlated error logging tested without exception material.
- V1: actual production controllers exercised with controlled promises, plus browser integration.
- V2: historical projects 0002 upgrade, actor backfill and unchanged receipt replay tested.
- E3: inactive membership removal tested.

## Verification

- Backend Django test suite, migration drift check, fresh database migrate, and PostgreSQL concurrency scenarios must pass.
- `npm.cmd --prefix platform/frontend test` and `npm.cmd --prefix platform/frontend run build` must pass.
- Browser walkthrough: login, create, four interview groups, save/reload, conflicts, confirm/edit/history, denied access and retry; desktop and 390px widths.
- Validate isolated Compose configurations and startup ordering. Record unavailable runtime checks as unverified; never infer deployment success from static checks.
