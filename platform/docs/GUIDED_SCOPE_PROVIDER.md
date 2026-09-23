# 引导式范围建议服务配置（V0.13）

当前仓库未配置模型服务或知识图谱。未配置、调用失败、额度耗尽或项目未授权时，页面允许人工填写并继续第一轮检索。页面上的“允许外部模型处理”只授权当前项目的基本信息与既有确认答案；项目负责人可以撤回。请仅在完成服务端部署审批后设置以下环境变量，密钥只保存在服务器，不能写进前端或 Git。

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `AI4S_SCOPE_PROVIDER_URL` | 服务端 HTTPS JSON 接口 | 空（不可调用） |
| `AI4S_SCOPE_PROVIDER_MODEL` | 模型标识 | 空 |
| `AI4S_SCOPE_PROVIDER_KEY` | Bearer 凭据 | 空 |
| `AI4S_SCOPE_PROVIDER_TIMEOUT` | 单次超时秒数，运行时限制 1–60 | `20` |
| `AI4S_SCOPE_PROVIDER_MAX_BYTES` | 响应上限，运行时最多 262144 字节 | `65536` |
| `AI4S_SCOPE_PROVIDER_QUOTA` | 每项目累计请求尝试上限 | `20` |

平台向接口 `POST` JSON：`{model,input,schema:"ai4s-guided-scope-v1",mechanisms_are_hypotheses:true}`。`input` 仅包含本项目题名、研究方向、核心关键词、既有确认的范围答案。接口返回 JSON 顶层恰好含 `fields` 与 `terms`。`fields` 必须覆盖 `object/mechanism/method/outcome/context`，每项为 `{options,question}`：信息足够时 `options` 为 3–5 个不同的 `{text,reason}` 且 `question` 为空；信息不足时 `options` 为空且 `question` 为明确追问。`terms` 至多 100 条，每条为 `{term,parent_keyword,relation,reason}`，`parent_keyword` 必须是当前项目关键词，`relation` 仅可为 `original/synonym/broader/narrower/related`。

平台严格验证结构与长度，拒绝跳转，服务端保存输入指纹和可复用结果；同输入重复打开页面不会再次付费。显式重新生成才形成新尝试。响应与当前项目版本、授权、输入不一致时标记过期，不能保存选择。正式上线前必须使用获准提供方、质量基线与真实课题样本验证建议质量；当前自动化测试只验证协议、权限和失效保护，不能证明科学建议正确。

回传诊断支持单次最多 200 条 CSV/JSON 记录和项目最多 2000 条独立题录；CSV 列为 `title,abstract,doi,pmid,patent_number,publication_date,application_date`。日期只收完整 `YYYY-MM-DD` 或空白，不能据此补造未知精度。抽样 20 条只用于调整纳排，不能作为正式 Gold 或查全查准率验收。
