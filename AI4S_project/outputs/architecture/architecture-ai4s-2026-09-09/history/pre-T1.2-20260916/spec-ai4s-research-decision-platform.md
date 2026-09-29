---
title: 'AI4S研究决策平台完整系统开发'
type: 'feature'
created: '2026-09-10'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'eede881651ab3858e482bb0bb3f50785ff617ad4'
context:
  - 'outputs/architecture/architecture-ai4s-2026-09-09/ARCHITECTURE-SPINE.md'
  - 'outputs/architecture/architecture-ai4s-2026-09-09/验收与实施映射.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前只有产品与技术设计以及一个单用户 SQLite 原型，尚无可供10个邀请制账号、3人同时操作的正式平台。研究者无法在一个受控系统内完成可复现检索、证据与导航分析、空白验证、选题决策、知识图谱贡献和持续监测。

**Approach:** 在新 `platform/` 目录建设 Vue 3、Django 5.2、PostgreSQL 17、Celery 5.6 与 RabbitMQ 4.3 的模块化单体，按 M0—M4 顺序交付完整流程。每阶段只在对应契约和测试通过后放行，未配置的平台规则、算法、许可、模型与运维能力明确显示为阻断状态。

## Boundaries & Constraints

**Always:** 产品 V0.10 是业务规则基线，架构约束 AD-1—AD-16 是跨模块不变量；文献与专利分支独立判定；Gold 每个独立范围有效总量至少50且调优/验收组均含正负例，两组查全率和查准率均以未舍入值达到 `>=85%`；命中使用 `hit/miss/unknown`；所有读取、下载、检索、模型、缓存和导出执行身份、项目、当前许可、权益、用途与状态的权限交集；外部模型仅处理许可和项目策略同时允许的材料；批准、发布、奖励、删除与付费操作必须版本化、幂等、可审计、可恢复。

**Never:** 不覆盖或改写 `ai4s-research-decision-platform/` 及其 SQLite 数据；不继承旧 PASS、二态评估、严格 `>85%` 或文献专利强耦合逻辑；不把生成的检索式当作已执行，不把共现/引文当作因果证据，不把潜在空白当作立项依据；不以模型补造缺失平台规则、科学阈值、许可事实或证据；不宣称尚未实测的容量、模型质量、真实平台兼容性或 RPO/RTO 已通过。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 检索闭环 | 选择平台、词表/图谱、Gold 与人工回传 | 版本化检索式、六关结果、三态评估、合格后不可变批准与语料快照 | 不满足项返回明确阻断、责任角色和恢复动作 |
| 证据与导航 | 固定语料、切面、策略和文本覆盖 | 可追溯趋势/主题/引文/证据图谱；空白经补查和专家三关后进入候选 | 缺字段或证据时保留“未检索到/不足/冲突”状态 |
| 图谱贡献 | 最终接纳子集、许可、双审核与贡献者确认 | 原子发布资格事件；唯一奖励按许可和 FIFO 计时 | 子集、重合率、许可或库版本变化则重新确认/审核 |
| 并发与恢复 | 重投、旧 Worker、删除、权限到期或未知付费结果 | 无重复业务结果，不泄漏内容；旧输出只留历史；未知付费待对账 | 409/422/403/404/429/503 使用统一业务错误体 |

</frozen-after-approval>

## Code Map

- `platform/backend/config/` — Django/DRF、会话/CSRF、PostgreSQL、Celery、环境与统一错误契约。
- `platform/backend/modules/` — 按技术方案建立 identity、projects、retrieval、materials、evaluation、knowledge、analysis、research、assets、entitlements、execution、models、operations；模块只写自有模型。
- `platform/backend/ports/` 与 `platform/backend/adapters/` — 文件、平台规则、模型、关键日记和旧格式解析边界；迁移旧解析纯函数，不复用旧权限/评估路径。
- `platform/frontend/` — 登录与项目、检索工作台、Gold评估、研究导航、证据/空白/选题、图谱后台、监测与任务状态页面。
- `platform/tests/contracts/`、`platform/tests/scenarios/`、`platform/tests/fixtures/` — API契约、S01—S16、T01—T21、平台样例和真实任务脱敏夹具。
- `platform/deploy/` 与 `platform/docs/` — 锁定依赖、容器、备份/恢复、监控、OpenAPI、迁移映射和验收证据。
- `ai4s-research-decision-platform/scope_interview.py`、`assets/app.js` — 仅作访谈状态机和 CSV/JSON/RIS/BibTeX 迁移参考；原目录保持不变。

## Tasks & Acceptance

**Execution:**
- [ ] `platform/backend/`、`platform/frontend/`、`platform/deploy/` — 建立精确锁文件、模块边界、同域会话、项目隔离、任务/Outbox/EventStore、文件与恢复骨架，交付 M0。
- [ ] `platform/backend/modules/{retrieval,materials,evaluation}/` 与检索页面 — 实现平台规则、规范 AST、编译/反解析、人工执行、导入溯源、Gold 隔离、三态、六关、20篇反馈、批准和数据快照，交付 M1。
- [ ] `platform/backend/modules/{knowledge,analysis,research,projects}/` 与研究页面 — 实现 PDF 覆盖、词表/证据、定制切面、统计导航、七类空白、补查三关、候选与决策包，交付 M2。
- [ ] `platform/backend/modules/{assets,entitlements}/` 与图谱后台 — 实现双来源图谱、贡献确认、审核发布、撤回、唯一奖励和90天 FIFO 账本，交付 M3。
- [ ] `platform/backend/modules/models/`、`operations/`、测试和运维文档 — 实现模型许可/预算/缓存/质量门槛、持续监测、删除保留、关键日记、容量与恢复验收，交付 M4。

**Acceptance Criteria:**
- Given 全新受控环境和邀请账号, when 完成 M0—M4 部署, then 用户可走通“铁死亡介导癌症放疗抵抗”的检索、证据、导航、空白验证和定题流程，所有结论可回溯到固定版本、材料与核查记录。
- Given 产品场景 S01—S16, when 运行自动化场景测试, then 每项产生与验收映射一致的状态、事件和证据，未满足依赖不获得正式状态。
- Given 技术场景 T01—T21, when 运行契约、并发、故障、权限、模型、容量和恢复测试, then 自动化项通过，真实平台/模型/容量/RPO-RTO 项保存原始实测证据后才标记通过。
- Given 旧 MVP 数据, when 执行只读迁移, then 保存旧新 ID 映射、记录数和指纹核对，旧通过状态全部重新评估且原数据库不被修改。

## Implementation Notes

- 2026-09-10：在独立 `platform/` 目录建立 Django/DRF、Vue/Vite、PostgreSQL/RabbitMQ Compose 与精确依赖锁；旧 MVP 和 SQLite 数据未修改。
- 2026-09-10：完成可执行领域契约和项目隔离 API 骨架，覆盖规范 AST、人工执行摘要、Gold 三态与正式检查门槛、证据定位、七类空白候选、决策包、贡献确认/唯一奖励、任务围栏、模型阻断、删除与关键日记规则；项目写操作使用幂等键和 revision。
- 2026-09-10：独立复跑后端测试，并修正测试发现的正式检查缺失与证据状态混用；前端 4 项、旧 MVP 22 项测试及前端构建、迁移漂移和 Compose 配置检查通过。当前仍是研发骨架：真实平台/PDF/模型/恢复与容量证据、完整关系模型和生产 Worker/发布事务尚未完成，任务保持未勾选，验收状态见 `platform/docs/ACCEPTANCE.md`。

## Spec Change Log

## Review Triage Log

## Design Notes

完整范围包含多个可独立验收阶段，但用户已选择连续实施。依赖顺序固定为 M0→M1→M2→M3→M4；每一阶段保留可运行系统和未配置状态，后续模块通过公开服务、版本 DTO 与事件扩展，不能建立跨模块 ORM 写入。

## Verification

**Commands:**
- `uv run --project platform/backend python platform/backend/manage.py check && uv run --project platform/backend python platform/backend/manage.py test` — 后端配置、迁移、契约和场景测试通过。
- `npm --prefix platform/frontend run test && npm --prefix platform/frontend run build` — 前端交互测试与生产构建通过。
- `docker compose -f platform/deploy/compose.yaml config` — 部署清单有效且版本已锁定。
- 在 `ai4s-research-decision-platform/` 目录运行 `python -m unittest discover -s tests -v` 和 `node --test tests/test_scope_ui.cjs` — 旧 MVP 基线保持通过。
