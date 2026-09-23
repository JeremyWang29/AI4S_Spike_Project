---
title: '引导式范围填写与回传后纳排确认'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
baseline_commit: 'c4f16cc5f4a015bc07d44a57a16fef043a20eac5'
context: []
---

<frozen-after-approval reason="Q1—Q12 accepted and final scope confirmed by user">

## Intent

Replace blank/manual scope forms with project-informed, human-confirmed suggestions and structured boundaries, then derive inclusion/exclusion criteria from actual returned-record feedback. User confirmed all Q1—Q12 recommendations and implementation on 2026-09-23. Existing dirty documents are earlier authorized work: preserve unrelated changes. After verification commit and push GitHub as already authorized.

## Boundaries & Constraints

Five research fields object/mechanism/method/outcome/context get 3–5 distinct AI options with reasons, multi-selection, editing and free entry. No auto-selection or fictional filler: insufficient context returns questions; mechanisms are hypotheses. Required project title/direction/core keywords; each research field is answered or explicitly not_applicable/exploratory. Dates default unlimited, selectable start/end inclusive through day; literature publication date; patent publication/application selector default publication. Language/type multi-select default unlimited, mutually exclusive. Literature and patent types separate. No mandatory include/exclude first round.

Terms grouped by keyword with relation original/synonym/broader/narrower/related, provenance and decisions. Accepted synonyms join original block; broader/narrower become explicit expansion/focus variants requiring user confirmation; related terms supplementary, never implicit main AND/OR. Keep original decisions, no automatic NOT.

Model context limited to current authorized project basics and confirmed answers; no private external projects, full texts or protected Gold. Same inputs reuse suggestions; changed inputs flag affected selections for review without overwriting edits; stale responses cannot commit. Config unavailable/failure/denied external processing leaves manual path. Implement configurable real HTTP adapter and mocked tests, never claim live provider verification without credentials. No provider currently configured, no graph service: indicate unavailable instead of simulating graph facts. Respect server-side project external-use policy, timeout/output limits and configurable call quota; retries/cache do not silently increase paid calls.

After return: import actual title/abstract/identifiers with platform and task provenance, project-scoped deduplication, deterministic stratified random first sample20 (or actual shortfall), append samples without repeats, retain seed/population identity. Human labels relevant/irrelevant/uncertain; reasons selectable/free text. Propose criteria from labels/reasons, user edits and explicitly confirms new version; show affected relevant records before exclusions apply. Preserve raw returns, scope/criteria history; invalidate dependent plans and affected annotations/Gold/evaluations, never reuse old pass metrics. Freeze official Gold/evaluate requires confirmed criteria; diagnostic20 is not Gold or precision. Existing official evaluation remains disabled; no fabricated new qualification.

</frozen-after-approval>

## Code Map

- `platform/backend/modules/projects/{services,views,models}.py`: persisted scope save/confirm/edit; `_mutate` wraps project lock/revision/idempotency/events. External calls outside lock with fixed inputs and final permission/revision checks. Scope history immutable.
- `modules/models/__init__.py`: ModelPolicy only, no actual provider. Add configurable candidate gateway; server secrets only.
- `modules/knowledge/services.py`: freeze flat concepts; extend typed decisions while retaining legacy selectors.
- `modules/retrieval/decomposition.py`: keep text five-field projection for compatibility; main vs supplemental/variant term handling must consume typed terms correctly, not flatten all accepted expansions.
- `modules/materials/__init__.py`: dataclasses only, import-summary stores counts, no actual records. New durable return/sample/criteria objects may live in projects for this integrated scope workflow, do not claim materials import-summary is a record store. Bind population, scope versions and project auth.
- `platform/frontend/src/components/ScopePanel.vue`, `m0Controllers.js`, `api.js`, `App.vue`: reuse draft preservation/version guards; add recommendation choices, date/select controls and feedback panel reachable in real-project UI. Legacy confirmed scopes remain read-only and readable; successor edits map old year/language/type strings without rewriting history or silently narrowing them.

## Tasks & Acceptance

- [x] Backend schema/compatibility: structured boundary and per-field selection status; first-round optional criteria; typed provenance and formal term projection; migrations for suggestion receipts and record/sample/criteria data. Server rejects forged provenance, unknown enums, invalid dates and cross-project references.
- [x] Candidate generation service/endpoints: settings for provider URL/model/key, external-use policy and quotas; safe structured response validation (3–5 choices or clarification), fixed source/input/model fingerprints and persisted cache; stale response and concurrent same-input dedup. Manual fallback stays functional. No live secrets required in repo.
- [x] Return/feedback endpoints: bounded JSON/CSV literature or patent record import with provenance, canonical identity dedupe; seed+stratum sample20, append, labels and reasons, criteria proposal/impact/explicit confirmation; scope successor+dependency invalidation atomically. Expose dedicated real workflow APIs; no frontend-only state.
- [x] UI forms and feedback panel; selected values persisted; show sources/status and unknown-date precision limitations; first entry requests recommendations, regeneration explicit, user values preserved; source and parent/variant labels understandable in Chinese.
- [x] Tests and documentation: new backend + frontend production-controller tests, full regression, migrations, PG concurrency and real browser walkthrough. Document provider setup/schema/limits. Root updates product/architecture baselines and acceptance records; implementation agent focuses code, tests and provider setup docs.

Acceptance: Given project basics and allowed configured mocked provider, generation returns validated 3–5 options and typed terms; repeated same-input call uses receipt, deny/unconfigured calls do not externalize data. Given date/multiselect/not_applicable/exploratory answers, save and first confirmation work without criteria, invalid or conflicting boundary returns recoverable error. Given accepted broader term, main block is unchanged until explicit variant selection. Given import duplicates across platforms/tasks, fixed sample is reproducible, additions disjoint, provenance preserved; all feedback persists on reload. Given confirmed criteria changed after preview, server rejects stale impact and needs fresh confirmation; raw records and old version remain intact, downstream old applicability invalidated. Given cross-project ids/reviewer/stale revisions/forged recommendation fields, commands reject and leave no partial write. No protected Gold input enters recommendation/feedback APIs. Given legacy scope, history reads unchanged and successor is safely editable.

## Implementation Notes

User already approved full cohesive flow and manual fallback. Technical choices needed for safe implementation may be resolved using existing contracts without another business interview. Provider credentials/quality baseline will remain explicit deployment prerequisites, not fake defaults. Formal retrieval platform compilation and official Gold subsystem are not part of this change.

## Verification

Django full suite and migrations --check; Node tests/build; dedicated PostgreSQL concurrency tests for receipt and feedback mutations; browser create/save/restore/boundary/manual fallback/import/sample/confirm on isolated data. Track exact results and limitations.

## Review Triage Log

2026-09-23 independent blind/edge/verification review (17 individual findings; locations checked against callers):

| # | Layer / claim | Verdict and evidence | Route / resolution |
| --- | --- | --- | --- |
| 1 | Blind: HTTP model URL leaks bearer key | high: `http_generate` previously opened arbitrary configured HTTP URL with Authorization | patch: require HTTPS before opening |
| 2 | Blind: pending receipt leaves UI waiting | medium: identical in-flight request returns pending and no old refresh control | patch: add no-cost status check button |
| 3 | Blind: stale receipt cannot auto-retry | false: explicit regeneration is available and intentionally spends a separately approved attempt; silent new paid call contradicts frozen cost rule | reject; stale message directs explicit retry |
| 4 | Blind: changed inputs reject saved option IDs | medium: selection verification had only current-input receipts and `edit` erased IDs | patch: preserve saved IDs, require review, validate new IDs against current receipt |
| 5 | Blind: unknown synonym parent vanishes | medium: unmatched parent yielded no block and no warning | patch: validate parent keyword and emit unresolved mapping if block absent |
| 6 | Blind: model `original` enters main | medium: provider schema previously permitted original relation | patch: generated terms restricted to synonym/broader/narrower/related |
| 7 | Blind: latest sample hides older records | medium: UI filtered on last sample only | patch: show all samples in current scope and use correct originating sample for label |
| 8 | Blind: merged export loses alternate text | medium: record kept first title/abstract after dedup | patch: retain each import's source variant and provenance |
| 9 | Blind: proposal placeholder can be confirmed | medium: missing reason was inserted as rule-like text | patch: leave unresolved labels out of rules and display omission |
| 10 | Blind: impact count omits prose rules | medium: automatic matching only checks `exclude_terms`; prose cannot be safely interpreted as exact filter | patch: clearly label count as keyword-only and require human review of text rules |
| 11 | Edge: direction change keeps accepted selections | medium: old direction was checked before updating scope | patch: saving direction change marks choices for review; direct confirmation rejects |
| 12 | Edge: criteria link lost on successor edit | medium: schema-v2 normalizer dropped `criteria_id` | patch: preserve server-issued link and reject forged replacement |
| 13 | Edge: unmatched synonym parent | medium: same observed outcome as #5 | patch: covered by parent check and unresolved item |
| 14 | Edge: deselected option text remains | medium: removing ID did not remove appended text | patch: preserve potentially edited text but require explicit review before confirmation |
| 15 | Edge: appended sample hides old labels | medium: same observed outcome as #7 | patch: covered by current-scope sample union |
| 16 | Gap: typed term consumer untested | medium: existing search-plan tests used only flat terms | patch: new API-to-plan scenario checks synonym parent and independent variants |
| 17 | Gap: stratification/seed untested | medium: prior sample test used only one source | patch: two-task 15+15 seeded coverage and repeatability test |
