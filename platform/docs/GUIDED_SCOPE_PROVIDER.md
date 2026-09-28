# 引导式范围建议服务配置（V0.13）

当前仓库未配置真实模型服务或生产知识图谱。未配置、调用失败、额度耗尽或项目未授权时，页面允许人工填写并继续第一轮检索。页面上的“允许外部模型处理”只授权当前项目的基本信息与本次已保存、状态为“已回答”的五项研究内容；项目负责人可以撤回。进入页面、保存草稿或切换授权均不触发付费请求；保存后仍须用户主动点击生成。请仅在完成服务端部署审批后设置以下环境变量，密钥只保存在服务器，不能写进前端或 Git。

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `AI4S_SCOPE_PROVIDER_URL` | 服务端 HTTPS JSON 接口 | 空（不可调用） |
| `AI4S_SCOPE_PROVIDER_MODEL` | 模型标识 | 空 |
| `AI4S_SCOPE_PROVIDER_KEY` | Bearer 凭据 | 空 |
| `AI4S_SCOPE_PROVIDER_TIMEOUT` | 单次超时秒数，运行时限制 1–60 | `20` |
| `AI4S_SCOPE_PROVIDER_MAX_BYTES` | 响应上限，运行时最多 262144 字节 | `65536` |
| `AI4S_SCOPE_PROVIDER_QUOTA` | 每项目累计请求尝试上限 | `20` |

平台向接口 `POST` JSON：`{model,input,schema:"ai4s-guided-scope-v1",mechanisms_are_hypotheses:true}`。`input` 仅包含本项目题名、研究方向、核心关键词、当前已保存且状态为已回答的五项内容，以及许可允许外发的最小图谱术语片段；不适用/探索中字段不作为已知事实。接口返回 JSON 顶层恰好含 `fields` 与 `terms`。`fields` 必须覆盖 `object/mechanism/method/outcome/context`，每项为 `{options,question}`：信息足够时 `options` 为 3–5 个不同的 `{text,reason}` 且 `question` 为空；信息不足时 `options` 为空且 `question` 为明确追问。`terms` 至多 100 条，每条为 `{term,parent_keyword,relation,reason}`，`parent_keyword` 必须是当前项目关键词，`relation` 仅可为 `synonym/broader/narrower/related`；原始关键词由范围草稿管理，不由模型产生。

平台严格验证结构与长度，拒绝跳转，服务端保存输入指纹和可复用结果；同输入重复打开页面不会再次付费。显式重新生成才形成新尝试。响应与当前项目版本、授权、输入不一致时标记过期，不能保存选择。正式上线前必须使用获准提供方、质量基线与真实课题样本验证建议质量；当前自动化测试只验证协议、权限和失效保护，不能证明科学建议正确。

只读图谱术语端口须逐条保存概念标识、定义、关系、来源定位、版本、访问范围及能否外发；项目私有或已授权平台术语仅对有权项目查询。图谱无覆盖与服务未配置均须明确显示。图谱中实体作用或机制关系不等同于名称同义；同形异义和模型/图谱关系冲突保留为待核查项。生产图谱数据导入及至少3个真实课题的专家质量验收在部署时单列记录；合成夹具不构成生产图谱。

管理员可在后端使用 `manage.py import_graph_terms <UTF-8 JSON 文件> --graph-version <版本> --license <许可> --project-id <项目 UUID>` 导入仅供该项目使用的术语。只有审核记录确认许可覆盖**全部试点项目**时，才能去掉项目 ID 并加 `--platform-wide-authorized`；受限共享资产的逐项目授权仍须后续建设，当前应按项目分别导入。JSON 为术语对象数组，每项须有 `concept_id`、`source_position`（可核查的来源定位）、`term`、`parent_keyword`、`relation`，可提供 `definition`。只有已核实许可允许外发时才能加 `--allow-external-sharing`。当前每个项目范围和平台范围各只激活一个完整图谱发布版；新版本会停用同范围旧版，旧候选进入待复核。相同版本的内容变化会替换该批术语，内容未变化时保留原候选身份。生产导入前应保存源文件和审核记录。

回传诊断支持单次最多 200 条 CSV/JSON 记录和项目最多 2000 条独立题录；CSV 列为 `title,abstract,doi,pmid,patent_number,publication_date,application_date`。日期只收完整 `YYYY-MM-DD` 或空白，不能据此补造未知精度。抽样 20 条只用于调整纳排，不能作为正式 Gold 或查全查准率验收。
