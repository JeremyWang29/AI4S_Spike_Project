"""构建受控规模的 STRING v11.5 历史特征，供 typed Learning-to-Rank 使用。

数据血缘：
    STRING v11.5 原始 gzip
      -> protein.info 将 STRING protein id 映射为 preferred gene symbol
      -> 仅保留当前候选 Gene 两端均命中的高置信互作
      -> string_v11_5_historical_edges.csv（可审计历史边）
      -> string_v11_5_historical_features.csv（模型节点特征）

时间控制：v11.5 发布于 2021 年，早于 2022-12-31 截止线，因此该版本的
combined_score 可以作为历史特征；当前 v12 分值不得进入主实验。

规模控制：只读取人类 9606，且要求 combined_score >= MIN_SCORE；不下载
跨物种文件，也不把候选集之外的蛋白扩张进模型。
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "codex-output" / "temporal_probe" / "normalized_graph"
RAW = ROOT / "codex-data" / "temporal_probe" / "raw" / "string_v11_5"
INFO = RAW / "9606.protein.info.v11.5.txt.gz"
LINKS = RAW / "9606.protein.links.v11.5.txt.gz"
# 700 对应 STRING 的 high-confidence 常用阈值；后续阈值消融只需修改此处。
MIN_SCORE = 700
VERSION = "STRING v11.5"


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_mapping(candidate_genes):
    """返回 STRING protein id -> 候选基因符号映射。

    仅保留已经出现在规范化候选集中的 preferred_name，避免别名误配和
    网络规模无限扩张。若要增加外部一跳邻居，应在这里显式增加白名单，
    而不是直接放开所有蛋白。
    """
    mapping = {}
    with gzip.open(INFO, "rt", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            protein_id = row.get("#string_protein_id") or row.get("string_protein_id")
            name = row["preferred_name"]
            if name in candidate_genes:
                mapping[protein_id] = name
    return mapping


def main():
    """执行映射、流式边过滤、节点特征生成和质量报告输出。"""
    nodes = read_csv(GRAPH / "nodes.csv")
    candidate_genes = {
        row["name"] for row in nodes
        if row["node_type"] in {"Gene", "Gene_or_other_locus"}
    }
    mapping = load_mapping(candidate_genes)

    roles = defaultdict(set)
    for edge in read_csv(GRAPH / "strict_historical_edges.csv"):
        if edge["source"] != "FerrDb":
            continue
        if edge["relation"] == "PROMOTES_FERROPTOSIS":
            roles["promoter"].add(edge["source_id"].split(":", 1)[-1])
        elif edge["relation"] == "SUPPRESSES_FERROPTOSIS":
            roles["suppressor"].add(edge["source_id"].split(":", 1)[-1])

    # 邻接表保存最高 combined_score；若同一无向边重复，只留最高分。
    neighbours = defaultdict(dict)
    raw_links = retained = 0
    # 逐行解压，内存中只保存候选子图，不载入约 1194 万行完整人类网络。
    with gzip.open(LINKS, "rt", encoding="utf-8") as handle:
        header = handle.readline().strip().split()
        p1_i, p2_i, score_i = (
            header.index("protein1"), header.index("protein2"),
            header.index("combined_score"),
        )
        for line in handle:
            raw_links += 1
            parts = line.split()
            score = int(parts[score_i])
            if score < MIN_SCORE:
                continue
            a, b = mapping.get(parts[p1_i]), mapping.get(parts[p2_i])
            if not a or not b or a == b:
                continue
            previous = neighbours[a].get(b, 0)
            if score > previous:
                neighbours[a][b] = score
                neighbours[b][a] = score
                if not previous:
                    retained += 1

    edge_rows = []
    for a in sorted(neighbours):
        for b, score in sorted(neighbours[a].items()):
            if a < b:
                edge_rows.append({
                    "source_id": f"protein:{a}",
                    "target_id": f"protein:{b}",
                    "relation": "INTERACTS_WITH",
                    "source": "STRING",
                    "pmid": "",
                    "year": 2021,
                    "evidence_tier": "strict_historical_database_release",
                    "weak_evidence": "false",
                    "version": VERSION,
                    "score": score,
                })

    # STRING 本身只表示功能关联，不解释促进/抑制铁死亡。角色特征通过
    # “候选节点连接了多少个历史 FerrDb promoter/suppressor”间接构造。
    feature_rows = []
    for gene in sorted(candidate_genes):
        nb = neighbours.get(gene, {})
        scores = list(nb.values())
        promoter = [(n, s) for n, s in nb.items() if n in roles["promoter"]]
        suppressor = [(n, s) for n, s in nb.items() if n in roles["suppressor"]]
        feature_rows.append({
            "gene": gene,
            "string_v11_5_degree": len(nb),
            "string_v11_5_score_sum": sum(scores) / 1000,
            "string_v11_5_mean_score": (sum(scores) / len(scores) / 1000) if scores else 0,
            "string_v11_5_max_score": (max(scores) / 1000) if scores else 0,
            "string_v11_5_promoter_neighbour_count": len(promoter),
            "string_v11_5_suppressor_neighbour_count": len(suppressor),
            "string_v11_5_promoter_neighbour_weight": sum(s for _, s in promoter) / 1000,
            "string_v11_5_suppressor_neighbour_weight": sum(s for _, s in suppressor) / 1000,
        })

    edge_fields = [
        "source_id", "target_id", "relation", "source", "pmid", "year",
        "evidence_tier", "weak_evidence", "version", "score",
    ]
    feature_fields = list(feature_rows[0])
    write_csv(GRAPH / "string_v11_5_historical_edges.csv", edge_rows, edge_fields)
    write_csv(
        GRAPH / "string_v11_5_historical_features.csv",
        feature_rows, feature_fields,
    )
    report = {
        "version": VERSION,
        "release_date": "2021-08-12",
        "cutoff": "2022-12-31",
        "species": 9606,
        "minimum_combined_score": MIN_SCORE,
        "candidate_gene_count": len(candidate_genes),
        "mapped_candidate_gene_count": len(set(mapping.values())),
        "raw_human_link_rows": raw_links,
        "retained_candidate_edges": retained,
        "covered_candidate_genes": sum(bool(neighbours.get(g)) for g in candidate_genes),
        "notes": [
            "combined_score is valid here because v11.5 predates the cutoff",
            "RNA candidates receive zero STRING features by entity-type design",
            "current STRING v12 data are not used in the historical method",
        ],
    }
    (GRAPH / "string_v11_5_historical_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
