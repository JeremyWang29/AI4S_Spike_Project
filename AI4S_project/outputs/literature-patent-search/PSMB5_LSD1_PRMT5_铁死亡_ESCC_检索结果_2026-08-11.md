# PSMB5 通过 LSD1–PRMT5 抑制铁死亡介导食管鳞癌放疗抵抗：文献与专利检索结果

检索日期：2026-08-11（Asia/Shanghai）<br>
数据源：OpenAlex、Semantic Scholar Academic Graph、PatSnap D009<br>
专利计数口径：请求参数 `collapse_type=DOCDB`（简单专利族）；结果中仍观察到同题名、不同公开文本，故另行标记残余家族重复。<br>
总体状态：`not demonstrated`。本轮完成发现性和机制边检索，但尚未建立独立、双人判读的 held-out 验证集，不能宣称查全率或查准率达到 80%。

## 1. 范围与暂定标准

- 核心问题：是否存在证据支持 `PSMB5 → LSD1/PRMT5 → 抑制铁死亡 → 食管鳞癌放疗抵抗`，以及各相邻机制边和可转化干预是否已有文献或专利布局。
- 时间：2012-01-01 至 2026-08-11（铁死亡概念形成以后）；PatSnap 未额外限定年份。
- 语言：英文为主；PatSnap 详情翻译语言为英文。
- 文献纳入：原始研究或高质量综述，至少直接支持一条机制边；跨癌种证据必须标注为外推证据。
- 专利纳入：题名、摘要、权利要求或说明书直接覆盖相关靶点、铁死亡、食管癌或放疗用途之一；仅在长基因表中偶然出现术语不作为直接相关。
- 文献去重：DOI 优先，其次稳定数据库 ID，再次规范化题名。
- 学术分组：严格按 `(学者 AND 机构)` 的同一署名关联计数，`pair_work_count > 10`，取前 5 组。
- 专利申请人分组：应按申请人/受让人聚合，`result_count > 50`，取前 3 组；本轮未达到可验证条件，见第 7 节。

## 2. 分层检索式

### 2.1 Semantic Scholar 可执行布尔式

| 查询 ID | 层级 | 检索式 |
|---|---|---|
| L1 | 完整链 | `PSMB5 AND (LSD1 OR KDM1A) AND PRMT5 AND ferroptosis AND ("esophageal squamous cell carcinoma" OR ESCC) AND (radioresistance OR radiotherapy)` |
| L2-A | PSMB5–铁死亡 | `PSMB5 AND ferroptosis` |
| L2-B | 表观遗传–铁死亡 | `(LSD1 OR KDM1A) AND PRMT5 AND ferroptosis` |
| L2-C | ESCC–放疗–铁死亡 | `ferroptosis AND ("esophageal squamous cell carcinoma" OR ESCC) AND (radiotherapy OR radioresistance OR radiosensitivity)` |
| L2-D | 靶点–ESCC–放疗 | `(PSMB5 OR LSD1 OR KDM1A OR PRMT5) AND ("esophageal squamous cell carcinoma" OR ESCC) AND (radiotherapy OR radioresistance)` |
| L3 | 领域扩展 | `ferroptosis AND cancer AND (radiotherapy OR radioresistance)` |
| E1 | 相邻边 | `PSMB5 AND (LSD1 OR KDM1A)` |
| E2 | 相邻边 | `PSMB5 AND PRMT5` |
| E3 | 相邻边 | `(LSD1 OR KDM1A) AND PRMT5` |
| E4 | 相邻边 | `(LSD1 OR KDM1A) AND ferroptosis` |
| E5 | 相邻边 | `PRMT5 AND ferroptosis` |
| E6 | 相邻边 | `PSMB5 AND (esophageal OR oesophageal OR ESCC) AND (radiotherapy OR radioresistance OR radiosensitivity)` |

Semantic Scholar 使用 `GET /graph/v1/paper/search/bulk`；请求字段包括 `paperId,title,abstract,year,authors,venue,externalIds,url,citationCount,publicationDate`。部分请求遇到 HTTP 429，按退避规则重试；E2 最终仍受限。

### 2.2 OpenAlex 查询

OpenAlex 使用 `GET /works` 的 `search` 参数和 `from_publication_date:2012-01-01` 过滤。OpenAlex `search` 返回相关性候选，不把它的总数解释为严格布尔命中数。查询概念与上表一致，但不声称支持未核实的布尔或邻近语法。

### 2.3 PatSnap D009 可执行式

统一请求：`POST https://connect.zhihuiya.com/search/patent/query-search-patent-detail`；认证为环境变量中的 Bearer 凭据；`offset=0`、`collapse_type=DOCDB`、`stemming=1`、`lang=en`、`replace_by_related=0`。

| 查询 ID | 检索式 |
|---|---|
| P1 | `PSMB5 AND (LSD1 OR KDM1A) AND PRMT5 AND ferroptosis AND (esophageal OR oesophageal) AND (radiotherapy OR radiation)` |
| P2 | `PSMB5 AND ferroptosis` |
| P3 | `(LSD1 OR KDM1A) AND PRMT5 AND ferroptosis` |
| P4 | `ferroptosis AND (esophageal OR oesophageal) AND (radiotherapy OR radiation)` |
| P5 | `(PSMB5 OR LSD1 OR KDM1A OR PRMT5) AND (esophageal OR oesophageal) AND (radiotherapy OR radiation)` |

## 3. API 结果计数

### 3.1 文献

| 查询 | OpenAlex 候选总数 | Semantic Scholar 布尔总数 | 解释 |
|---|---:|---:|---|
| L1 完整链 | 0 | 0 | 未检出完整链记录 |
| L2-A PSMB5–铁死亡 | 135 | 1 | S2 唯一记录经题名筛查不相关；OpenAlex 为相关性候选，不能视为 135 条直接证据 |
| L2-B LSD1/PRMT5–铁死亡 | 31 | 0 | 三者同时出现的严格结果稀少；需拆成 E3、E4、E5 |
| L2-C ESCC–放疗–铁死亡 | 3,193 | 6 | S2 命中直接机制论文；OpenAlex 候选集宽，含综述和跨癌种记录 |
| L2-D 靶点–ESCC–放疗 | 0 | 0 | 未检出 PSMB5/LSD1/PRMT5 与 ESCC 放疗共同出现的严格集合 |
| L3 铁死亡–肿瘤–放疗 | 14,268 | 98 | 领域扩展集合 |
| E1 PSMB5–LSD1 | 14 | 0 | OpenAlex 顶部主要为骨髓瘤/蛋白酶体抑制剂耐药的间接证据 |
| E2 PSMB5–PRMT5 | 44 | 429 未完成 | OpenAlex 顶部高噪声，未发现直接机制 |
| E3 LSD1–PRMT5 | 311 | 1 | OpenAlex 命中直接 PRMT5–LSD1 复合体/轴研究；S2 单条结果不代表完整覆盖 |
| E4 LSD1–铁死亡 | 170 | 2 | 至少两篇肺癌原始研究直接支持 |
| E5 PRMT5–铁死亡 | 842 | 20 | 多篇跨癌种研究直接支持，含 GPX4、KEAP1 等机制 |
| E6 PSMB5–ESCC–放疗 | 0 | 0 | 本轮未检出直接记录 |

### 3.2 专利

| 查询 | PatSnap 报告总数 | 本轮详情筛查 |
|---|---:|---:|
| P1 完整链 | 0 | 0 |
| P2 PSMB5–铁死亡 | 13 | 13 条题名/摘要全量筛查 |
| P3 LSD1/PRMT5–铁死亡 | 79 | 相关性排序前 5 条 |
| P4 ESCC–放疗–铁死亡 | 1,081 | 相关性排序前 5 条 |
| P5 靶点–ESCC–放疗 | 7,895 | 仅计数；结果过宽，未批量取详情 |

## 4. 机制证据地图

| 机制边 | 证据等级 | 判定 |
|---|---|---|
| PSMB5 → LSD1 | `indirect` | 多发性骨髓瘤研究提示 LSD1 抑制可增强蛋白酶体抑制剂反应，但不等于 PSMB5 直接调控 LSD1 |
| PSMB5 → PRMT5 | `not found` | 本轮未检出直接机制研究 |
| LSD1 ↔ PRMT5 | `supported` | 乳腺癌研究通过质谱、共免疫沉淀和结构域实验支持 Slug–PRMT5–LSD1 复合体；另有 PRMT5 依赖的 LSD1 稳定性研究 |
| LSD1 ⊣ 铁死亡 | `supported` | 肺癌研究显示 KDM1A/LSD1 通过 c-Myc 或 ATF4–xCT–GSH 轴抑制铁死亡；属于跨癌种直接证据 |
| PRMT5 ⊣ 铁死亡 | `established`（跨癌种）/`supported`（ESCC） | PRMT5 可通过 KEAP1、GPX4 等底物抑制铁死亡；ESCC 中 STC2 激活 PRMT5 并通过 DNA 损伤修复和铁死亡通路促进放疗抵抗 |
| 铁死亡抑制 → ESCC 放疗抵抗 | `established` | NRF2–SLC7A11、STC2–PRMT5、ACAT2 和 SNORA58/JNK1 等多条独立机制支持 |
| PSMB5 → LSD1–PRMT5 → 铁死亡 → ESCC 放疗抵抗完整链 | `not found` | 两个默认文献源和 PatSnap 完整链检索均为 0；仅能把该链视作待验证假说 |

## 5. 建议纳入的文献 gold 候选

这些记录均至少直接支持一条机制边，但尚未完成双人判读、tuning/held-out 拆分，故称“gold 候选”而不是已冻结 gold dataset。

| DOI | 年份 | 证据边 | 结论摘要 |
|---|---:|---|---|
| [10.1016/j.redox.2023.102626](https://doi.org/10.1016/j.redox.2023.102626) | 2023 | PRMT5–铁死亡–ESCC 放疗抵抗 | STC2 与 PRMT5 相互作用并激活 PRMT5，经 DNA 损伤修复与铁死亡通路促进 ESCC 放疗抵抗 |
| [10.1186/s12967-021-03042-7](https://doi.org/10.1186/s12967-021-03042-7) | 2021 | 铁死亡–ESCC 放疗抵抗 | NRF2 上调 SLC7A11、抑制放疗诱导铁死亡并降低放疗敏感性 |
| [10.1016/j.ijrobp.2023.05.031](https://doi.org/10.1016/j.ijrobp.2023.05.031) | 2023 | 铁死亡–ESCC 放疗抵抗 | ACAT2 抑制铁死亡并赋予 ESCC 放疗抵抗 |
| [10.1002/advs.202508515](https://doi.org/10.1002/advs.202508515) | 2025 | 铁死亡–ESCC 放疗抵抗 | SNORA58 抑制 JNK1 介导的铁死亡并促进 ESCC 放疗抵抗 |
| [10.1038/s41556-025-01610-3](https://doi.org/10.1038/s41556-025-01610-3) | 2025 | PRMT5–铁死亡 | PRMT5 对 GPX4 进行精氨酸甲基化并稳定 GPX4，抑制肿瘤铁死亡 |
| [10.1136/jitc-2023-006890](https://doi.org/10.1136/jitc-2023-006890) | 2023 | PRMT5–铁死亡 | PRMT5 甲基化并稳定 KEAP1，调节 NRF2/HMOX1 并促进 TNBC 铁死亡/免疫治疗耐受 |
| [10.1038/s41419-023-06238-5](https://doi.org/10.1038/s41419-023-06238-5) | 2023 | LSD1–铁死亡 | LSD1 抑制使 H3K9me2 增加、ATF4–xCT–GSH 下降并诱导 NSCLC 铁死亡 |
| [10.1038/s41598-022-23699-4](https://doi.org/10.1038/s41598-022-23699-4) | 2022 | LSD1–铁死亡 | KDM1A 通过上调 c-Myc 抑制肺癌细胞铁死亡 |
| [10.1186/s13046-022-02400-7](https://doi.org/10.1186/s13046-022-02400-7) | 2022 | LSD1–PRMT5 | 质谱和共免疫沉淀支持 Slug–PRMT5–LSD1 复合体，并显示双靶点抑制协同 |
| [10.15252/embr.201948597](https://doi.org/10.15252/embr.201948597) | 2019 | PRMT5–LSD1 | PRMT5 依赖的精氨酸甲基化稳定 LSD1，促进乳腺癌侵袭和转移 |
| [10.1186/s40164-023-00434-x](https://doi.org/10.1186/s40164-023-00434-x) | 2023 | PSMB5/蛋白酶体–LSD1（间接） | LSD1 抑制增强蛋白酶体抑制剂反应并克服骨髓瘤耐药；不能据此推断 PSMB5 直接调控 LSD1 |

## 6. 学者 AND 机构联合抽取（5 组）

抽取母集：OpenAlex `search=ferroptosis cancer`，2012 年以后；报告总数 82,495，本轮按游标读取相关性排序前 2,000 条。每篇作品只在作者署名明确链接到该机构时计入。

| 排名 | 学者 | OpenAlex 作者 ID | 机构 | OpenAlex 机构 ID | 联合成果数（已读取 2,000 条内） |
|---:|---|---|---|---|---:|
| 1 | Daolin Tang | A5055468442 | The University of Texas Southwestern Medical Center | I867280407 | 50 |
| 2 | Daolin Tang | A5055468442 | Southwestern Medical Center | I4210096815 | 45 |
| 3 | Rui Kang | A5091664811 | The University of Texas Southwestern Medical Center | I867280407 | 44 |
| 4 | Brent R. Stockwell | A5030207693 | Columbia University | I78577930 | 41 |
| 5 | Daolin Tang | A5055468442 | Southwestern Medical Center | I4388891891 | 38 |

注意：排名 2 和 5 的机构显示名相同但 OpenAlex 稳定 ID 不同，可能是机构实体重复或历史/层级实体。本轮遵循协议，不仅凭名称相似擅自合并。以上是截取前 2,000 条后的下限计数，不代表完整 82,495 条中的最终排名。

## 7. 专利代表结果与申请人抽取

### 7.1 P2：PSMB5–铁死亡（13 条全量题名/摘要筛查）

结果主要包括：

- `WO2024155901A2/A3/A8`、`EP4651864A2`、`US20260176333A1`：E3 ligase family functions and interactions；申请人为 Genentech、Broad Institute 等。题名/摘要不直接覆盖本课题链，并存在残余家族重复。
- `US20180353445A1`：Methods and compositions relating to proteasome inhibitor resistance；与蛋白酶体抑制剂耐药相关，但题名/摘要未直接涉及铁死亡或 ESCC 放疗。
- `US20250025478A1`：RNF213 signaling pathway；可能在说明书中同时出现检索词，但题名/摘要不直接支持目标机制。
- 其余为狼疮分子通路、微生物表达检测等明显非目标结果。

按题名/摘要判读，13 条中没有可直接纳入完整机制链的专利。由于尚未逐条审查全部权利要求和说明书，不能把该结果解释为绝对不存在相关专利。

### 7.2 P3：LSD1/PRMT5–铁死亡（前 5 条）

前 5 条均为 Revolution Medicines 的 RAS(ON) 抑制剂组合治疗或不良反应管理申请，且包含多个国家/地区公开文本。题名/摘要未直接限定 LSD1–PRMT5–铁死亡机制，显示无字段宽检索存在明显噪声。

### 7.3 P4：ESCC–放疗–铁死亡（前 5 条）

| 公开号 | 题名 | 申请人/受让人 | 初筛 |
|---|---|---|---|
| US20240285543A1 / WO2022271619A1 | Nanoparticle-mediated enhancement of immunotherapy to promote ferroptosis-induced cytotoxicity and antitumor immune responses | Memorial Sloan Kettering、Cornell 等 | 与铁死亡和外照射联合相关；未限定 ESCC |
| WO2026060174A1 | Method of using copper-loaded copper ionophores to overcome radioresistance | Board of Regents, University of Texas System | 直接涉及放疗耐受，但机制为 cuproptosis，不是 ferroptosis |
| US20240148757A1 | Use of DHODH inhibitors to target ferroptosis in cancer therapy | University of Texas System、Kadmon | 直接涉及肿瘤铁死亡干预；未限定 ESCC 或放疗 |
| US20200138829A1 | Methods of cancer treatment | Ferro Therapeutics | 铁死亡诱导剂联合肿瘤治疗；未限定 ESCC 或放疗 |

### 7.4 申请人阈值结果

本轮没有可验证的 `result_count > 50` 申请人组，因此不能输出合格的 3 组：

1. D009 列表只返回 `pn` 和 `patent_id`，申请人仅在每次调用返回的单条 `patent_detail` 中出现。
2. 用户提供的 D009 规则未给出可验证的 PatSnap Analytics 申请人字段码，不能擅自构造申请人限定式。
3. 对 P4 的 1,081 条记录逐条取详情会产生大量计费调用；本轮为控制成本仅抽取前 5 条。
4. P3 前 5 条虽然均显示 Revolution Medicines，但属于重复/相关专利公开文本，不能据此推断其在去重后有超过 50 个在范围内的成果。

因此，专利申请人抽取结果为 `0/3 verified`，不是“没有高产申请人”，而是“当前证据不足以验证阈值”。

## 8. 查全率、查准率与停止判断

- 文献：已形成多条机制边的 gold 候选，但尚未冻结独立 held-out 集，且部分 Semantic Scholar 查询受 429 限流；查全率和查准率均未正式计算。
- 专利：P2 的 13 条仅完成题名/摘要筛查；P3/P4 只抽取前 5 条，且申请人分组未完成；查全率未定义，整体查准率不能据小样本外推。
- 80% 停止标准：`未达到可证明条件`。原因不是某一已计算指标低于 80%，而是缺少满足协议的独立标注集和 held-out 验证。
- 当前决定：`iterate`。下一轮优先验证 PatSnap 申请人字段语法、进行专利家族二次规范化、扩大 ESCC 专利详情筛查，并对文献 gold 候选做双人判读与 tuning/held-out 拆分。

## 9. 核心结论

1. 完整的 `PSMB5 → LSD1–PRMT5 → 抑制铁死亡 → ESCC 放疗抵抗` 链在本轮两个文献 API 和 PatSnap D009 中均未直接检出。
2. 假说的下游部分证据较强：PRMT5 抑制铁死亡、铁死亡抑制促进 ESCC 放疗抵抗，且 STC2–PRMT5 已在 ESCC 中形成直接桥接。
3. LSD1 与 PRMT5 的复合/轴关系、LSD1 抑制铁死亡均有跨癌种直接证据，但把这些证据外推到 ESCC 仍需实验验证。
4. 最大证据缺口是 PSMB5：尚无直接记录把 PSMB5 与 LSD1/PRMT5、铁死亡及 ESCC 放疗抵抗串联起来。这一缺口构成课题的新颖性来源，也意味着课题设计必须优先验证 PSMB5 对 LSD1/PRMT5 的方向性调控和救援关系。
5. 专利层面，宽检索结果很多但噪声高；聚焦的 PSMB5–铁死亡集合在题名/摘要层面未出现直接相关专利，仍需权利要求/说明书全文判读后才能作稳健的新颖性判断。
