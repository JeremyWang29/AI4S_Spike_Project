# Deferred work

- source_spec: `D:/research/2025/AI4S_生命科学/_bmad-output/implementation-artifacts/spec-frontend-main-workflow-preview.md`
  summary: 硬化旧Gold、检索、人工执行、导入和导航API的输入与来源校验。
  evidence: 当前可接受负数或错类型评估计数、无效AST/kind、blocked或平台不一致执行、异常导入数量，且导航未核验冻结DatasetSnapshot。
- source_spec: `D:/research/2025/AI4S_生命科学/_bmad-output/implementation-artifacts/spec-frontend-main-workflow-preview.md`
  summary: 建立候选课题、决策包和图谱贡献奖励的服务端信任边界。
  evidence: 当前端点信任请求端布尔值、证据/scope/snapshot IDs、审核人和许可声明，可伪造eligible、decision-ready或奖励。
- source_spec: `D:/research/2025/AI4S_生命科学/_bmad-output/implementation-artifacts/spec-frontend-main-workflow-preview.md`
  summary: 在容器首次启动流程中显式执行并校验数据库迁移。
  evidence: `compose.yaml`的API和worker在新PostgreSQL卷上直接启动，没有建表步骤。
- source_spec: `D:/research/2025/AI4S_生命科学/_bmad-output/implementation-artifacts/spec-frontend-main-workflow-preview.md`
  summary: 非开发模式在缺少AI4S_SECRET_KEY时应拒绝启动。
  evidence: `settings.py`当前在DEBUG为false时仍使用公开的development-only回退密钥。
