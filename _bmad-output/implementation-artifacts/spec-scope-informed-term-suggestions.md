---
title: '基于已保存研究范围的图谱与模型候选词审核'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '10ae751bfe47f66700dc57b50207bea1c8a04e2c'
context: []
---

<frozen-after-approval reason="用户已逐项接受 grill-me Q1—Q18，并确认落实到平台与规格">

## Intent

**Problem:** 当前范围草稿载入时即尝试获取建议，模型只读取项目基本信息和上一版答案；用户刚填写的五项研究内容没有成为候选词依据，知识图谱也尚无受控术语查询。候选平铺且来源、歧义、冲突和过期复核不足。

**Approach:** 用户保存五项研究字段后主动生成候选。服务端先查项目可用的只读图谱术语，再在明确许可下调用模型补充语义候选；按原关键词分组展示，每个派生词由用户逐条确认，形成不可变概念词表版本。

## Boundaries & Constraints

**Always:** 五项均须有明确状态；只将已回答内容纳入建议输入，不适用/探索中保留为待追问。模型上下文限当前项目题名、方向、关键词及已保存五项；图谱内容仅在许可允许时外发。平台已授权图谱首次可用，私有图谱随后可更新；无覆盖/无模型时人工路径可用。每项保留概念标识、定义、图谱版本、来源、许可、关系、歧义及决定；同形异义不自动合并，图谱与模型冲突标待核查，机制关系不当同义。接受同义词只成同块 OR 候选，上下位/相关词只成变体或补充任务。原始关键词修改走范围草稿。范围、关键词、图谱版本或权限变化使受影响选择待复核，不覆写历史。外部调用需授权、限额、缓存及过期保护。

**Never:** 不凭模型生成伪造图谱事实；不将受限图谱/全文/Gold发往外部；不一键接受全部或自动进入正式检索式；不把诊断样本当 Gold；不宣称未配置的模型或图谱具有真实质量。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 首次生成 | 五项状态已保存、项目可查图谱、可选模型授权 | 明确点击后按原词展示至多5个优先项，余项可展开；显示来源与关系 | 无图谱/模型逐源说明并可人工继续 |
| 脏草稿 | 五项编辑尚未保存 | 不生成或外发；先保存 | 显示保存提示，保留输入 |
| 冲突/歧义 | 同形异义、图谱和模型关系不同 | 独立保留来源并要求人工定关系 | 未解决项不进已确认词表 |
| 版本变化 | 回答、关键词、图谱或权限变化 | 旧决定保留，受影响项待复核 | 迟到返回不得应用 |

</frozen-after-approval>

## Code Map

- `platform/backend/modules/projects/suggestions.py`: 现有 HTTPS 供应商、调用收据、缓存/配额与模型来源防伪；须改输入与图谱合成。
- `platform/backend/modules/projects/{guided,services}.py`: 五字段校验、保存/确认、新版、候选决定与词表冻结；扩展来源、复核和原词保护。
- `platform/backend/modules/knowledge/{models,services}.py`: 目前只有不可变 ConceptVersion；新增只读图谱术语存储、权限/许可/版本查询，不假装已有图谱资产。
- `platform/frontend/src/{components/ScopePanel.vue,m0Controllers.js,api.js}`: 取消载入/授权后自动调用；展示来源分组、冲突、未覆盖及逐条决定。
- `platform/tests/scenarios/test_guided_feedback.py` 与 `platform/frontend/test/m0Controllers.test.js`: 保留已有回归，增加新边界测试。

## Tasks & Acceptance

**Execution:**
- [x] `modules/knowledge` 新增受控、可导入且可查询的图谱术语记录与许可/版本；不向无权项目泄露。
- [x] `modules/projects/suggestions.py` 用保存的五项内容生成固定指纹；图谱先查、模型只补合法内容；输出来源、冲突、限量与过期状态。
- [x] `modules/projects/{guided,services}.py` 扩展候选完整性、逐项审核、原词变更和失效复核，冻结词表只收可用的确认项。
- [x] `ScopePanel.vue`/控制器/API 改为保存后主动生成，按原词分组展示不超过5个优先候选及更多项，清晰区分图谱/模型/人工来源和缺失状态。
- [x] 产品设计、技术方案、阶段计划及提供方说明同步 Q1—Q18 和真实部署条件。
- [x] 后端/前端回归及隔离浏览器验收；只提交本功能文件并同步 GitHub，保留无关工作区改动。

**Acceptance Criteria:**
- Given 已保存五字段与可查询许可图谱，when 用户点击生成，then 建议绑定本次范围、图谱版本及来源且人工可逐条确认。
- Given 模型未授权或图谱无覆盖，when 生成，then 不外发受限信息、来源缺失可见且人工路径仍可完成。
- Given 两来源冲突或同名不同义，when 确认词表，then 未解候选不能成为同义词。
- Given 范围或图谱权限变化，when 重开草稿，then 历史保留且受影响选择显式待复核。

## Implementation Notes

服务端新增图谱术语表及管理员导入命令，按平台或项目范围查询；仅可外发的片段进入已授权模型上下文。建议输入取自已保存五项状态与回答，并记录模型调用尝试、缓存和失效依据。界面仅在用户保存并主动点击时生成，显示来源、关系、冲突与待复核信息。范围确认冻结经逐条决定的词表；当前项目关键词须保留为已接受原词，移除时先修改草稿并明确拒绝旧词。

当前每个访问范围只激活一个完整图谱发布版；受限共享资产需按项目导入，尚无逐资产授权服务。无匹配 `parent_keyword` 的输入如实显示无覆盖，不推断未核查的上下位关系。

人工验收见 `platform/docs/acceptance/SCOPE-TERMS-2026-09-24.md`。生产模型和图谱质量需后续在真实课题上专家验证。

## Spec Change Log

## Review Triage Log

| 层 / 发现 | 结论与证据 | 处理 |
| --- | --- | --- |
| blind / 平台图谱全项目可见 | medium：原导入端未明确区分公共与受限资产，可能越权分发。 | patch：平台级导入要求管理员明确确认覆盖全部试点项目；受限资产只按项目导入。 |
| blind / 图谱来源定位缺省 | medium：概念 ID 被当成来源位置，不能证明关系出处。 | patch：导入必须填写可核查 `source_position`。 |
| blind / 同版重导入更换身份 | medium：未变的图谱会使候选失效并可能触发重复模型费用。 | patch：内容相同则保留行身份，增加回归。 |
| blind / 模型额度阻断本地图谱 | medium：原分支提前返回，丢失可用图谱候选。 | patch：额度用尽时生成图谱专用收据并保留候选。 |
| blind / 关键词仅精确映射 | false：当前受控术语接口明确用 `parent_keyword` 记录已审核的词与原词关系；未审核的新拼写无合法关系可供安全反推，页面如实报告无覆盖。 | 不从同形词臆造图谱关系；生产覆盖率另行专家验收。 |
| blind / 人工词可冒充原词 | medium：旧界面默认 `original`，可绕过原词草稿。 | patch：人工默认相关词，服务端拒绝新增人工 `original`。 |
| blind / 模型来源只含序号 | medium：多次生成无法定位具体模型响应。 | patch：来源位置嵌入收据 ID，收据保留模型标识。 |
| blind / 跨轮冲突未标记 | medium：旧决定与新来源可冲突而不触发关系复核。 | patch：合并草稿候选重新计算冲突，界面同步标记。 |
| blind / 前五项无排序依据 | low：字母顺序会被误认为优先级。 | patch：按明确的术语关系类型排序，并说明不代表相关性评分。 |
| blind / 单词候选无上限 | medium：一次导入可能让用户审核海量候选。 | patch：同一原词最多导入 100 个，超出由管理员先筛选。 |
| verification / 已回答字段未测入模 | medium：缺测试会让输入退回只有项目基本信息。 | patch：新增混合回答状态的模型请求断言。 |
| verification / 返回词未测加入草稿 | medium：界面若丢失返回词，现有测试仍可能通过。 | patch：新增控制器成功建议测试。 |
| edge / 旧待处理词未复核 | medium：答案变化后待处理词可被接受却未复核。 | patch：所有图谱和模型词在受影响时标待复核，新增测试。 |
| edge / 图谱旧版仍活跃 | medium：新版本导入后旧候选仍可被误认作当前。 | patch：按访问范围停用旧发布版，新增跨项目隔离测试。 |

## Verification

**Commands:** 最终 SQLite 全套 77 项（5 项条件跳过）；PostgreSQL 全套 69 项及最终定向 16 项；最终前端 32 项与构建；迁移检查；隔离浏览器往返。
