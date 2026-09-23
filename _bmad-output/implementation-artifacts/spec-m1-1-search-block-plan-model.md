---
title: 'M1.1：检索块与方案数据模型'
type: 'feature'
created: '2026-09-17'
status: 'done'
route: 'dispatch'
baseline_commit: '6daa0fb114c4adde0f77fce853e38254f69ce90c'
implementation_status: 'complete'
acceptance_status: 'technical-pass-awaiting-user'
stage: 'M1.1'
source_spec: 'spec-v012-search-plan-interview.md'
context:
  - 'outputs/research-platform-design-20260907/产品设计方案.md'
  - 'outputs/research-platform-design-20260907/检索方案示例_PSMB5_方向确认稿_20260916.md'
  - 'outputs/architecture/architecture-ai4s-2026-09-09/V0.12检索方案技术契约.md'
  - 'outputs/development-plan/ai4s-staged-development-20260911/分阶段开发计划.md'
---

# M1.1：检索块与方案数据模型

## Intent

**Problem:** M0已能确认研究范围，但系统仍把检索表达式作为零散的页面预览。用户无法看清题目与关键词被拆成哪些概念、哪些关系只是待核查假说，也无法保存带来源和执行顺序的方案草稿。

**Approach:** 从项目题目、研究方向、核心关键词、已确认范围和正式概念词表，按版本化生命科学模板生成可审阅的检索块、任务矩阵及方案执行批次。retrieval模块持久化不可变草稿和输入来源映射；前台只展示草稿与未决项，等待M1.2的追问与显式确认。

## Boundary and dependencies

- M0状态为`done / accepted-by-user`，复用其项目权限、ResearchConstraint确认版、ConceptVersion、DependencyEdge、Outbox与WorkflowProjection。项目标题默认取Project.name；可传研究题目覆盖值，必须保留原文与来源。只读当前已确认范围和与之匹配的正式概念版；版本缺失或已失效返回可恢复阻断。
- 数据归retrieval拥有；projects与knowledge只通过公开只读选择器提供版本化DTO，依赖边与事件通过负责模块的公开服务写入。不得从浏览器缓存或旧探索性查询推断正式范围。
- 本任务只生成`draft`，不得产生SearchPlanConfirmed、FormalSearchApproved、外部平台检索、Gold评估或模型调用。后续问题、批次激活、编辑确认及语义改版归M1.2；平台编译归M1.4；组合总体归M2。

## Code map and ordered tasks

1. `platform/backend/modules/projects/services.py`与`modules/knowledge/services.py`：提供权限已由调用入口核验的固定范围／正式词表只读DTO，含对象ID、版本、内容指纹及来源；不暴露受保护全文。
2. `platform/backend/modules/retrieval/{apps,models,services,views}.py`、`migrations/0001_initial.py`、`config/settings.py`和`config/urls.py`：登记retrieval Django模块；建立SearchPlan、SearchBlock、SearchPlanTask、SearchPlanBatch四类对象与公开创建／读取命令。保持现有`retrieval.domain`规范AST可复用，不能让旧探索性API直接写新方案。
3. `platform/backend/modules/retrieval/templates/life_science_v1.json`与`decomposition.py`：定义通用分面／要素结构和首个生命科学模板。规则先识别已给定词与授权词表、复合表达和显式关系疑点；生成来源片段到块的映射及结构化任务逻辑。词义无法确定、标题与关键词冲突、缩写多义时输出未决项，不静默选择。
4. `platform/backend/modules/execution/services.py`或当前负责依赖的公开服务：同事务登记scope／concept→plan依赖和SearchPlanDraftCreated事件；重复请求仅返回原草稿。范围新版使旧草稿适用性变为`needs_revalidation`，历史内容不改写。
5. `platform/frontend/src/api.js`、`App.vue`及`components/SearchPlanDraft.vue`：在范围步骤下展示只读的2B草稿，列出块的来源、关系待核查、任务与当前／后续批次；明确标记“待追问／待确认／不可执行”。刷新后从服务端读取；示例项目的浏览器预览不得冒充真实保存。
6. `platform/tests/{contracts,scenarios}/test_m1_1.py`及`platform/frontend/test/`：验证下方验收矩阵。仅针对这次新增的跨层行为写测试，不复制纯实现细节。

## Data and API contract

| 对象 | 本阶段必需字段与不变量 |
|---|---|
| SearchPlan | `id, plan_id, project_id, version=1, status=draft, applicability, scope_id/version/fingerprint, concept_id/version/fingerprint, template_id/version/hash, input_snapshot, content_fingerprint, revision, created_by/at`；`(plan_id,version)`唯一，草稿内容不可就地覆盖 |
| SearchBlock | `plan_id/version, block_key, facet_type, label, source_spans, term_refs, relation_hypotheses`；块键在同版唯一，term_refs区分用户词、已接受词、授权词表建议及模型推测（本阶段后者为空），同义／上下位／相关关系不混用 |
| SearchPlanTask | `plan_id/version, task_key, purpose, required_blocks, optional_variant_refs, logical_ast, filters, exclusions, output_partition, prerequisites, expansion_conditions`；任务引用必须存在，块内OR与块间AND显式保存；可选块只作独立变体，不隐性AND |
| SearchPlanBatch | `plan_id/version, batch_key, task_refs, prerequisites, activation_conditions, status=planned`；它是方案执行批次，不是上传文件的ImportBatch；本阶段任何批次均不能变为active |

入口：`POST /api/v1/projects/:id/search-plans`，带`Idempotency-Key`、`expected_revision=0`、确认范围与概念版本引用、可选`research_title`。201返回草稿ID、固定版本、块、任务、批次及未决项；同键同输入重放原201，异输入409。`GET /api/v1/search-plans/:id`仅向有项目读取权者返回同一固定草稿；未授权统一404。服务器在项目行锁下再次核对范围、词表与项目权限；上游版本变化返回409和恢复动作。新表只存来源引用与受限元数据，不复制私人图谱正文或受保护Gold。

所有跨引用须同项目、同方案版本；任务依赖无环；逻辑树节点、块引用、分区与模板字段按schema校验。计划固定来源指纹与模板哈希，以便后续M1.2在新版本上修订；前台提交的`confirmed`、`approved`、`active`等字段一律无写入口。

## PSMB5 fixed fixture

输入题目：“PSMB5通过LSD1-PRMT5抑制铁死亡介导食管鳞癌放疗抵抗的研究”。最少识别A PSMB5、B LSD1/KDM1A、C PRMT5、D食管鳞癌、E铁死亡、F放疗／照射、G放疗反应七块；G保留抵抗与敏感性两个不同子类。`LSD1-PRMT5`保存两个实体及未核查关系，不能标成已证实复合体；“通过／抑制／介导”只进入关系疑点，不作为默认必选词。

首批只把Q01=`D AND E AND (F OR G)`、Q02=`A AND D`、Q11=`A AND B AND C AND D AND E AND (F OR G)`列为`planned`；Q11标注高度重合线索目的。后续机制配对任务为条件批次，跨疾病材料标记补充集，不进入目标疾病主集。首轮无默认NOT、年份、语言、物种限制。此夹具仅验证方案结构，不验证PubMed／WoS语法或实际命中。

## Acceptance criteria

| 场景 | Given / When / Then |
|---|---|
| 草稿生成 | Given已确认且可读的范围与正式词表，When研究者创建方案草稿，Then返回固定输入与模板版本、来源片段、检索块、任务矩阵及planned批次；刷新后内容一致，未显示检索已执行或方案已批准 |
| PSMB5规则 | Given上述题目，When运行生命科学模板，Then产生A—G块、Q01/Q02/Q11首批、关系待核查和主／补充集边界，且不添加默认NOT／时间／语言过滤 |
| 冲突与不确定 | Given标题和关键词对研究对象有冲突或未知缩写，When生成草稿，Then保留两侧原文与来源并列为未决，不能自行丢弃词项或宣称机制成立 |
| 通用性 | Given另一个无PSMB5的生命科学题目，When生成草稿，Then按同一模板得到可解释块或明确的人工待定项，不输出硬编码PSMB5任务 |
| 权限与版本 | Given跨项目ID、未确认／已替换范围或错误概念版，When创建／读取，Then分别拒绝越权或返回版本阻断；旧草稿历史可读但不宣称当前适用 |
| 幂等与结构 | Given同键并发、改载荷重放、无效块引用或依赖环，When提交，Then同输入只一份完整草稿及事件，异输入409，非法结构不留下半成品 |

**Spec checkpoint:** 范围与词表只读契约、四对象字段、API守卫、生命科学模板和上述验收样例均可逐文件实施；本文件达到`ready-for-dev`。**Done checkpoint:** Django迁移与完整后端／前端相关测试通过，PSMB5及第二题目回归通过，实际页面可读取服务端草稿，权限和版本负例通过；记录代码版本、测试结果与尚未启用的M1.2/M1.4能力。当前实现与技术验收已完成，待用户试用。


## Review Triage Log

| ID | Verdict / route | Evidence and resolution |
|---|---|---|
| Blind-1 | medium / patch | Unicode 边界漏中文相邻 XYZ；改 ASCII 边界，标题覆盖测试验证。 |
| Blind-2 | medium / patch | 241 字符缩写超 PostgreSQL label 长度；截断显示标签，完整来源保留，真实 PostgreSQL 测试通过。 |
| Blind-3 | medium / patch | 未知词去重丢后续接受词来源；合并来源与 term_refs，回归覆盖。 |
| Blind-4 | medium / patch | 原始输入中的拒绝/替换词重新成为任务操作数；DTO 透传既有决定，相关块暂不分配任务并明确冲突，不删除原文。 |
| Blind-5 | medium / patch | 额外块没有任务用途说明；新增逐块待分配未决项，自噬样例覆盖。 |
| Blind-6 | medium / patch | 通用单实体任务误标疾病主集；疾病以外的单块任务标为补充集，API 和页面均核验。 |
| Blind-7 | medium / patch | 缺字段触发 Python 异常；校验字段结构并统一可恢复 INVALID_SEARCH_PLAN，注入缺字段测试覆盖。 |
| Blind-8 | medium / patch | 批次先决条件可自阻塞或依赖后批；校验唯一归属、已完成前批依赖和批内拓扑次序。 |
| Edge-1 | medium / patch | 独立复现中文相邻缩写缺失；同 Blind-1 修复。 |
| Edge-2 | medium / patch | 独立复现来源丢失；同 Blind-3 修复。 |
| Edge-3 | medium / patch | 独立复现长标签持久化失败；同 Blind-2 修复。 |
| Verification-1 | medium / patch | 原测试未固定 Q01/Q02/Q11 的逻辑；新增创建与详情读取的精确 AST 断言，包含 F OR G。 |
| Verification-2 | medium / patch | 仅测试覆盖标题的幂等冲突，未测试成功覆盖；新增成功保存标题、title_source 及来源片段的回归。 |

## Verification

2026-09-23 PostgreSQL 全套 61/61 通过，无跳过；前端 28/28 和构建通过；迁移一致性通过。实际页面完成两题目生成、项目隔离、刷新恢复、范围新版使旧草稿失效与阻断。详见 `platform/docs/acceptance/M1.1-2026-09-23.md`。未启用 M1.2 追问/批准、M1.4 编译及 M2 正式质量验收；无本任务缺陷延期。
