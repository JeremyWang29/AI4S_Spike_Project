---
title: '前台主流程交互预览与真实建项入口'
type: 'feature'
created: '2026-09-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'eede881651ab3858e482bb0bb3f50785ff617ad4'
context:
  - 'outputs/research-platform-design-20260907/产品设计方案.md'
  - 'outputs/architecture/architecture-ai4s-2026-09-09/ARCHITECTURE-SPINE.md'
  - 'outputs/architecture/architecture-ai4s-2026-09-09/验收与实施映射.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前Vue前台只有静态模块概览，既不能登录、列出或新建真实项目，也不能验证科研人员能否理解产品V0.11主流程。

**Approach:** 接通真实会话、项目列表和原子建项；其余能力实现明确标记的可点击交互预览。规范八步为：项目信息、范围与概念、检索平台、探索检索、种子与知识构建、Gold与正式检索（含停止决定）、语料确认、统计与引文分析。

## Boundaries & Constraints

**Always:** 首次进入显示登录或空项目列表；真实建项只收名称、方向和至少一个规范化关键词，并在同一事务创建Project、ResearchConstraint v1草稿、初始依赖、WorkflowProjection和幂等记录，成功后进入范围页。测试账号由初始化命令创建，不写死密码。后续草稿按项目写入版本化`sessionStorage`，刷新恢复、关标签失效，可清除；项目切换不串状态。示例流程须主动加载、独立命名空间、始终带来源标签。

范围访谈分对象与机制、方法与结局、场景与文献边界、纳排与资源条件四组；必填完整、矛盾清零并经用户确认后才形成新范围版本。知识图谱／AI候选使用确定性示例，保存接受、修改或拒绝决定。前序改变后，受影响的查询、评估、停止、语料和分析转“需重新验证”，历史只读保留。

21个平台均按领域和规则核实状态展示；CNKI、Web of Science、PubMed、智慧芽提供完整示例。平台目标显示子库、入口、字段、过滤、合并方式和规则版本。检索式可编辑，修改立即使检查和执行失效。检查分平台规则、语法能力、语义一致、实际执行、回传完整性、Gold／查准质量；未核实平台只输出逻辑草稿。文件选择只读取名称、大小和类型，不上传、不解析；示例回传展示实际执行式、时间、命中／导出数、过滤、排序、截断、解析和去重状态。

有效Gold总量≥50且含正负例；正例衡量查全，负例单列误检回归，实际结果全量标注或冻结分层样本衡量查准。调优和独立验收两阶段均须原始指标≥0.85、unknown=0且六类检查通过；84.96%不放行。20篇反馈只作可复现调优诊断。独立包一旦用于调优即整体失去独立资格。`validated`由规则计算；其他停止类型要求原因并保存实际指标、限制和下一动作。停止决定不自动冻结DatasetSnapshot；分析逐能力显示模拟准入与服务连接状态，状态为可用、阻断或仅探索。

**Never:** 不把示例或浏览器草稿表述为服务器事实、真实检索、AI／图谱调用、文件解析、分析结果或正式验收；不自动回退为本地真实项目；不把关键词当正式范围、生成式当执行式、Gold负例当查准分母或停止当语料冻结；本次不实现后续领域对象、模型调用、真实平台连接或生产部署。

## I/O & Edge-Case Matrix

| 场景 | 输入／动作 | 产物和守卫 | 失败与恢复 |
|---|---|---|---|
| 登录与建项 | 真实账号；名称／方向／关键词 | 真实项目＋范围草稿＋投影；用户隔离、幂等、原子 | 403引导登录；409刷新；422定位字段；网络失败保留表单 |
| 范围与切换 | 四组答案、候选决定、项目切换 | 每项目预览草稿；确认后范围新版；下游失效 | 空白／矛盾阻断；损坏或旧schema安全重置 |
| 平台与探索 | 多选目标、编辑表达式、示例回传或本地文件元数据 | 每平台表达式、六类检查、执行与导入摘要 | 规则未知、部分／重复／解析失败分别显示恢复动作 |
| 种子与知识 | 高被引前10、一区最新10示例 | 去重双标签、缺额说明、词表和基础关系预览 | 无来源或缺额不伪造补齐 |
| 评估与停止 | Gold 49／50、零分母、unknown、84.96%、两阶段结果 | 指标分开可复算；只有完整合格才validated | 未达标继续迭代或选择带理由的非通过停止 |
| 语料与分析 | 纳排／去重确认、字段／引文边／PDF许可差异 | 独立快照预览；逐能力准入和连接状态 | 不完整总体、撤权或缺字段阻断，有限条件仅探索 |

</frozen-after-approval>

## Layout Contract

保留绿色科研工作台：左侧项目／模块导航、顶部规范八步、中央当前任务、右侧证据与阻断摘要。后续步骤可查看，依赖型命令禁用并解释原因；复杂规则默认折叠。桌面优先，移动端改为顶部项目选择和横向步骤导航。

## Code Map

- `platform/backend/modules/projects/models.py`、`migrations/0002_*.py` — 新增ResearchConstraint、WorkflowProjection和用户域CreateRequest；保留现有WorkflowState。
- `platform/backend/modules/projects/views.py`、`config/urls.py` — 会话状态、用户项目列表和原子创建API；复用BusinessError。
- `platform/frontend/src/api.js` — CSRF会话、登录、项目列表／创建和错误映射。
- `platform/frontend/src/workflow.js` — 导出`normalizeKeywords`、`validateProject`、`evaluateGate`、`invalidateAfter`、`load/save/clearPreview`。
- `platform/frontend/src/state.js` — 保留现有`stages/workAreas`，另导出`workflowSteps`、21个平台、四个完整示例、示例项目和状态枚举。
- `platform/frontend/src/components/LoginPanel.vue`、`ProjectForm.vue`、`WorkflowStepper.vue`、`PreviewBadge.vue` — 明确入口、表单、步骤和来源边界。
- `platform/frontend/src/App.vue`、`style.css` — 组合项目列表、八步工作台、详情折叠、阻断摘要和响应式布局。
- `platform/tests/scenarios/test_project_flow.py`、`platform/frontend/test/*.test.js`、`platform/docs/openapi.yaml` — 接口契约、边界规则和预览真实性。

## Tasks & Acceptance

**Execution:**
- [x] 实现真实会话、项目列表、原子建项、迁移、OpenAPI及后端测试。
- [x] 实现前端API层、会话预览状态和确定性业务规则测试。
- [x] 实现入口组件、规范八步和各步交互工作台。
- [x] 完成自动测试、生产构建及桌面／移动人工走查。

**Acceptance Criteria:**
- Given合法受邀账号，when登录并重复提交同一项目，then仅创建一个完整且仅该用户可见的项目；失败不留半成品。
- Given空项目或主动加载示例，when走完八步，then每步均显示输入、版本、产物、状态、阻断、恢复动作和来源；未满足依赖只能查看。
- Given范围或检索式被修改，when返回后续步骤，then相关现行状态均为需重新验证，旧记录不被覆盖。
- Given任一评估边界或泄漏条件，when计算停止资格，then只有两阶段双指标、unknown和检查全部合格才显示validated。
- Given模拟卡片被复制、截图或窄屏显示，when脱离全局标题查看，then卡片自身仍含“交互预览／未连接真实服务”说明。

## Implementation Notes

- 2026-09-11：规格按对抗性、边界、结构和文字评审修订；用户确认Q1—Q25均采用建议。
- 2026-09-11：完成真实会话、用户隔离的原子建项、幂等回放、初始范围与流程投影，并补充本地测试账号命令。
- 2026-09-11：完成八步交互预览、21个平台目录、四个平台表达式示例、Gold与停止守卫、语料和分析准入；锁定步骤可见但不可操作。
- 2026-09-11：修复开发模式CSRF来源、真实项目误带演示范围、Vue响应式对象无法structuredClone、旧阻断在后续步骤残留等走查问题。
- 2026-09-11：后端31项测试、Django系统检查、前端16项测试和Vite生产构建通过；390×844与1440×1000走查无水平溢出，并验证刷新恢复、清除重置、来源标签及锁定步骤。
- 2026-09-11：BMAD三层评审完成；本故事内问题均已修复并复验，旧领域API、生产迁移和密钥硬化记入`deferred-work.md`。

## Spec Change Log

- 2026-09-11：恢复规范八步，补真实建项边界、预览持久化、六类检查、回传、独立评估、停止／语料／准入分离和可执行验证。

## Review Triage Log

- 采纳流程错位、状态歧义、平台／回传不足、评估隔离、预览真实性和测试缺口；驳回“Gold正例≥50”，保持“有效Gold总量≥50且含正负例”。

| ID | 裁决／路由 | 核验证据 |
|---|---|---|
| BH-01 | medium · patch | 原范围守卫只检查非空文本，pending候选和矛盾确认可被跳过；已加入候选全处理与人工无矛盾守卫。 |
| BH-02 | medium · patch | 原失效逻辑保留现行执行、种子、评估和语料数值；已将旧产物归档为只读历史并重置现行轮次。 |
| BH-03 | medium · patch | `recordExploration` 原无执行式、时间、数量和文件守卫；已加入可执行输入校验。 |
| BH-04 | medium · patch | 语料确认原为静态checked，冻结只看停止决定；已改为受控人工确认并纳入守卫。 |
| BH-05 | high · patch | `NaN`、负数、超界比率和正负例总数不一致确可绕过原比较；已校验整数、有限范围、合计及精确六键。 |
| BH-06 | medium · defer | 旧Gold领域对象只有5个`FORMAL_CHECKS`，与新前台六类表达未对齐；该旧端点不是本次会话／建项故事的修改对象。 |
| BH-07 | high · defer | 旧`GoldGroup`未校验非负整数，负数或字符串可产生错误指标或500；属旧评估API硬化。 |
| BH-08 | medium · defer | `_parse_ast`对非对象、缺键和空Bool可产生500或空编译结果；属旧检索API硬化。 |
| BH-09 | medium · defer | `GATES[kind]`对未知kind直接`KeyError`；属旧检索API硬化。 |
| BH-10 | high · defer | 旧人工执行API可登记blocked查询、不一致平台、负命中数和字符串布尔值；不是本次预览适配器改动。 |
| BH-11 | medium · defer | 旧导入API以`parsed_count >= total_hits`判完整，未拒绝解析错误和异常数量；属旧导入域硬化。 |
| BH-12 | high · defer | 旧导航API把任意导入当固定语料，未核验DatasetSnapshot；属后续真实分析故事。 |
| BH-13 | high · defer | 旧候选API信任请求端布尔值和任意evidence IDs，确可伪造eligible；属后续候选证据域硬化。 |
| BH-14 | high · defer | 旧决策API未验证scope/snapshot存在及与候选一致；属后续决策包故事。 |
| BH-15 | high · defer | 旧贡献API信任请求端审核人、许可和重合率，可伪造奖励；属资产后台的信任边界修复。 |
| BH-16 | high · defer | Compose首次启动未运行迁移确会缺表；本故事明确不实现生产部署。 |
| BH-17 | high · defer | 非DEBUG仍可使用可预测SECRET_KEY启动；属部署安全硬化，不是本故事范围。 |
| EC-01 | high · patch | 原每次提交都生成新幂等键，响应丢失后重试可重复建项；已按规范化请求指纹复用键。 |
| EC-02 | high · patch | 修改已确认范围时原`confirmed`仍为true；已在任一范围变更后撤销确认。 |
| EC-03 | medium · patch | pending候选可确认与BH-01同源；已由`scopeReady`阻断。 |
| EC-04 | medium · patch | 空执行登记与BH-03同源；已由`explorationReady`阻断。 |
| EC-05 | medium · patch | 未确认即冻结与BH-04同源；已由`snapshotReady`阻断。 |
| EC-06 | high · patch | 原只检查当前步是否locked，上游失效后远端`needs_revalidation`步仍可操作；已改为核验所有前置步的`operationBlocked`。 |
| EC-07 | high · patch | 缺失或非数值指标可误通过与BH-05同源；已加有限数校验。 |
| EC-08 | high · patch | 负unknown和超界比率可误通过；已限定unknown=0且比率在0至1。 |
| EC-09 | high · patch | 原任意6个true键可代替规定检查；已按固定键名逐一校验。 |
| EC-10 | medium · patch | 同schema缺字段对象原会直接返回并在渲染时失败；已校验完整形状并升级schema。 |
| EC-11 | medium · patch | sessionStorage禁用／满额原会抛未处理异常；已捕获并返回保存结果。 |
| EC-12 | medium · patch | 包含引号或布尔词的关键词可改变表达式结构；已将词项全部引用并转义内部引号。 |
| EC-13 | medium · patch | 范围草稿卡脱离全局标题时缺来源说明；已在每个范围卡加“浏览器草稿·未写服务器”。 |
| VG-01 | medium · patch | 预验证缺口：原自动测试不经过浏览器API适配器；已新增CSRF、表单登录、同域凭据和幂等建项请求测试。 |
| VG-02 | medium · patch | 预验证缺口：原测试只调helper，删除Vue事件绑定仍会绿；已加入模板绑定回归测试并以真浏览器走查状态传播。 |
| VG-03 | medium · patch | 预验证缺口：原只测旧schema，同schema损坏未测；已新增当前schema残缺对象安全重置测试。 |
| VG-04 | medium · patch | pending候选仍可确认与EC-03同源；已由范围守卫和回归测试覆盖。 |

## Verification

**Commands:**
- `uv run --project platform/backend python platform/backend/manage.py check && uv run --project platform/backend python platform/backend/manage.py test`
- `npm.cmd --prefix platform/frontend test && npm.cmd --prefix platform/frontend run build`

**Manual checks:**
- 桌面和移动端分别走通“首次登录建项”及“加载示例并修正阻断”两条路径；验证刷新恢复、切换隔离、清除、失效传播、四类停止、来源标签、键盘焦点和中文可读性。
