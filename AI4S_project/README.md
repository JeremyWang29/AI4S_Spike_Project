# AI4S 项目文档

这里集中存放平台设计、研发计划、评审及专题研究交付物。`outputs/` 保留迁移前的子目录结构，以保持产品、技术和开发计划之间的相对链接。**现行版本从下表进入**；`history/`、`reviews/`中的历史快照和检查记录用于追溯，不自动代表当前实现或验收状态。

| 类别 | 现行入口 | 用途 |
| --- | --- | --- |
| 产品设计 | [产品设计方案](./outputs/research-platform-design-20260907/产品设计方案.md) | 用户旅程、业务规则与产品模块 |
| 技术设计 | [技术方案](./outputs/architecture/architecture-ai4s-2026-09-09/技术方案.md) | 模块所有权、数据契约、任务和部署 |
| 开发阶段 | [分阶段开发计划](./outputs/development-plan/ai4s-staged-development-20260911/分阶段开发计划.md) | M0—M6顺序、依赖及放行证据 |
| 架构约束 | [ARCHITECTURE-SPINE](./outputs/architecture/architecture-ai4s-2026-09-09/ARCHITECTURE-SPINE.md) | 跨模块稳定决策 |
| 验收目录 | [验收目录](./outputs/architecture/architecture-ai4s-2026-09-09/验收目录.md) | 产品／技术场景与阶段验收映射 |
| 评审记录 | [产品技术评审](./outputs/reviews/product-tech-20260929/评审报告.md) | 特定版本的评审意见与修订证据 |
| 专题研究 | [文献专利检索材料](./outputs/literature-patent-search/) | 专题检索相关交付物；逐项核对适用范围 |

代码、运行手册和测试证据继续放在[`platform/`](../platform/README.md)附近；开发过程遵循[研发代码质量与交付规范](../platform/docs/DEVELOPMENT_STANDARDS.md)。迭代中的任务规格保留在[`_bmad-output/implementation-artifacts/`](../_bmad-output/implementation-artifacts/)供研发工具使用。它们在此建立入口，不复制第二份正式内容。

大型原始数据、实验输出及可重算中间结果保留在仓库现有的`数据集/`、`codex-data/`与`codex-output/`，不随设计文档搬迁；目录索引不意味着这些数据已获发布许可。

本目录由原仓库根目录的 `outputs/` 整体迁入。后续新增设计交付物放入本目录相应类别；修改现行规则时同步更新所属产品模块、技术模块、验收项和开发计划。迁移前的绝对文件路径需改用这里的新位置，旧 `outputs/README.md` 只保留定位提示。
