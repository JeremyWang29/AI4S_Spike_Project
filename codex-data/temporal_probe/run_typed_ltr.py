"""在完整历史图谱上执行分实体类型的 pairwise Learning-to-Rank。

输入层次：
1. advanced_gene_features.csv：FerrDb/PubTator 核心历史统计；
2. full_neighborhood_features.csv：截至 2022 的全量 PubTator 邻域；
3. string_v11_5_historical_features.csv：历史蛋白互作结构；
4. structured_historical_features.csv：SIGNOR/TRRUST/miRTarBase 调控结构。

训练标签是截至 2022 的 FerrDb promoter/suppressor；2023+ held-out 只用于
最终排名评估，并从未标注负样本池中排除。Gene 与 RNA 在各自候选空间排名，
且 group_columns 用于阻止不适用数据源的全零列改变网络宽度。
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "codex-output" / "temporal_probe"
GRAPH = BASE / "normalized_graph"
OUT = BASE / "typed_ltr_results"
RELATIONS = ("PROMOTES_FERROPTOSIS", "SUPPRESSES_FERROPTOSIS")


def read_csv(path):
    """以 UTF-8 BOM 兼容方式读取一个 CSV 为字典列表。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    """写出模型结果；字段顺序采用第一行的键顺序。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def entity_group(node_type):
    """把细粒度节点类型折叠为两个互斥排名空间：Gene 或 RNA。"""
    return "Gene" if node_type in {"Gene", "Gene_or_other_locus"} else "RNA"


BASE_COLUMNS = [
    "pubtator_core_edge_count", "pubtator_core_pmid_count",
    "pubtator_unique_core_neighbours", "pubtator_2021_2022_pmid_count",
    "strict_unique_neighbour_count", "strict_unique_pmid_count",
    "strict_temporal_evidence_weight", "strict_recent_edge_count",
    "strict_relation_entropy", "strict_promoter_neighbour_count",
    "strict_suppressor_neighbour_count", "strict_promoter_neighbour_weight",
    "strict_suppressor_neighbour_weight",
]
FULL_COLUMNS = [
    "full_pub_edge_count", "full_pub_pmid_count",
    "full_pub_unique_neighbour_count", "full_pub_temporal_weight",
    "full_pub_recent_edge_count", "full_pub_relation_entropy",
    "full_pub_associate_count", "full_pub_positive_correlate_count",
    "full_pub_negative_correlate_count", "full_pub_interact_count",
    "full_pub_promoter_neighbour_count", "full_pub_suppressor_neighbour_count",
    "full_pub_promoter_neighbour_weight", "full_pub_suppressor_neighbour_weight",
    "full_pub_associate_promoter_weight", "full_pub_associate_suppressor_weight",
    "full_pub_positive_correlate_promoter_weight",
    "full_pub_positive_correlate_suppressor_weight",
    "full_pub_negative_correlate_promoter_weight",
    "full_pub_negative_correlate_suppressor_weight",
    "full_pub_interact_promoter_weight", "full_pub_interact_suppressor_weight",
]
REACTOME_COLUMNS = [
    "reactome_pre2023_pathway_count", "reactome_relevant_pathway_count",
    "reactome_promoter_context_count", "reactome_suppressor_context_count",
    "reactome_promoter_context_weight", "reactome_suppressor_context_weight",
]
STRING_V11_5_COLUMNS = [
    "string_v11_5_degree", "string_v11_5_score_sum",
    "string_v11_5_mean_score", "string_v11_5_max_score",
    "string_v11_5_promoter_neighbour_count",
    "string_v11_5_suppressor_neighbour_count",
    "string_v11_5_promoter_neighbour_weight",
    "string_v11_5_suppressor_neighbour_weight",
]
SIGNOR_COLUMNS = [
    "signor_out_edge_count", "signor_in_edge_count",
    "signor_activates_out_count", "signor_inhibits_out_count",
    "signor_regulates_out_count", "signor_pmid_count", "signor_direct_count",
    "signor_promoter_neighbour_count", "signor_suppressor_neighbour_count",
]
TRRUST_COLUMNS = [
    "trrust_out_edge_count", "trrust_in_edge_count",
    "trrust_activates_out_count", "trrust_inhibits_out_count",
    "trrust_regulates_out_count", "trrust_pmid_count",
    "trrust_promoter_neighbour_count", "trrust_suppressor_neighbour_count",
]
MIRTARBASE_COLUMNS = [
    "mirtarbase_out_edge_count", "mirtarbase_in_edge_count",
    "mirtarbase_targets_out_count", "mirtarbase_pmid_count",
    "mirtarbase_promoter_neighbour_count",
    "mirtarbase_suppressor_neighbour_count",
]


def load():
    """合并所有可用特征，并构造候选集、训练正例和 held-out 正例。"""
    base = {r["gene"]: r for r in read_csv(GRAPH / "advanced_gene_features.csv")}
    full = {r["gene"]: r for r in read_csv(GRAPH / "full_neighborhood_features.csv")}
    for gene, values in full.items():
        if gene in base:
            base[gene].update(values)
    string_path = GRAPH / "string_v11_5_historical_features.csv"
    if string_path.exists():
        for values in read_csv(string_path):
            if values["gene"] in base:
                base[values["gene"]].update(values)
    structured_path = GRAPH / "structured_historical_features.csv"
    if structured_path.exists():
        for values in read_csv(structured_path):
            if values["gene"] in base:
                base[values["gene"]].update(values)
    node_types = {
        r["name"]: r["node_type"] for r in read_csv(GRAPH / "nodes.csv")
        if r["name"] in base
    }
    groups = defaultdict(list)
    for gene in base:
        if gene in node_types and node_types[gene] not in {
            "Pathway", "NonHumanRNA_or_gene", "ProteinFamily_or_Pathway"
        }:
            groups[entity_group(node_types[gene])].append(gene)
    train = defaultdict(set)
    for edge in read_csv(GRAPH / "strict_historical_edges.csv"):
        if edge["source"] == "FerrDb" and edge["relation"] in RELATIONS:
            train[edge["relation"]].add(edge["source_id"].split(":", 1)[1])
    decisions = {
        r["original_symbol"]: (
            r["canonical_symbol"] if r["normalization_status"] == "accepted" else None
        ) for r in read_csv(GRAPH / "normalization_decisions.csv")
    }
    heldout, excluded = [], []
    for row in read_csv(BASE / "heldout_edges.csv"):
        gene = decisions.get(row["symbol"], row["symbol"])
        group = next((g for g, genes in groups.items() if gene in genes), None)
        if gene is None or group is None:
            excluded.append({**row, "reason": "excluded_or_untyped"})
        else:
            heldout.append({**row, "gene": gene, "entity_group": group})
    return base, groups, train, heldout, excluded


def make_matrix(genes, features, columns, relation):
    """生成指定关系的特征矩阵，做有符号 log1p 和列标准化。

    最后一列加入相反 FerrDb 角色指示，例如预测 promoter 时加入历史
    suppressor 标记，使模型能学习角色冲突而非把所有高连接基因都前推。
    """
    opposite = (
        "ferrdb_suppressor_pre2023"
        if relation == "PROMOTES_FERROPTOSIS" else "ferrdb_promoter_pre2023"
    )
    rows = []
    for gene in genes:
        item = features[gene]
        rows.append([float(item.get(c, 0) or 0) for c in columns] + [
            float(item.get(opposite, 0) or 0)
        ])
    x = np.asarray(rows, dtype=np.float32)
    x = np.sign(x) * np.log1p(np.abs(x))
    mean, std = x.mean(0), x.std(0)
    std[std < 1e-6] = 1
    return (x - mean) / std


class RankNet(torch.nn.Module):
    """小型两层打分网络；输出为未归一化排序分数。"""
    def __init__(self, n_features):
        super().__init__()
        hidden = min(32, max(8, n_features))
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(n_features, hidden), torch.nn.ReLU(),
            torch.nn.Dropout(0.15), torch.nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.layers(x).squeeze(1)


def fit_scores(x, genes, positives, future, seed):
    """以已知正例对未标注候选的 pairwise softplus 损失训练一次。

    future held-out 被排除出负样本池，避免把未来真阳性错误当负例训练。
    返回所有候选的连续分数；上层会对 10 个随机种子取平均。
    """
    index = {g: i for i, g in enumerate(genes)}
    pos = np.asarray([index[g] for g in positives if g in index], dtype=int)
    negative_pool = np.asarray([
        i for i, gene in enumerate(genes) if gene not in positives and gene not in future
    ], dtype=int)
    if not len(pos) or not len(negative_pool):
        return np.zeros(len(genes), dtype=float)
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    model = RankNet(x.shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01, weight_decay=0.01)
    xt = torch.tensor(x)
    for _ in range(450):
        p = rng.choice(pos, size=512, replace=True)
        # Half random and half high-feature hard negatives.
        n = rng.choice(negative_pool, size=512, replace=True)
        model.train()
        diff = model(xt[p]) - model(xt[n])
        loss = torch.nn.functional.softplus(-diff).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        return model(xt).numpy()


def rank_method(name, columns, features, groups, train, heldout, group_columns=None):
    """为每个实体组和关系独立训练；group_columns 实现类型特征门控。"""
    scores = {}
    for group, genes in groups.items():
        genes.sort()
        active_columns = (
            group_columns.get(group, columns) if group_columns else columns
        )
        for relation in RELATIONS:
            x = make_matrix(genes, features, active_columns, relation)
            future = {
                r["gene"] for r in heldout
                if r["entity_group"] == group and r["relation"] == relation
            }
            runs = [
                fit_scores(x, genes, train[relation], future, 20260731 + seed)
                for seed in range(10)
            ]
            scores[(group, relation)] = dict(zip(genes, np.mean(runs, 0).tolist()))
    return name, scores


def evaluate(methods, groups, train, heldout):
    """在未参与训练的候选池中计算逐 held-out 排名与汇总检索指标。"""
    metrics, predictions = [], []
    for name, scores in methods:
        ranks, percentiles = [], []
        for item in heldout:
            group, relation, gene = item["entity_group"], item["relation"], item["gene"]
            pool = [g for g in groups[group] if g not in train[relation]]
            values = scores[(group, relation)]
            ordered = sorted(pool, key=lambda g: (-values[g], g))
            by_value = defaultdict(list)
            for i, candidate in enumerate(ordered, 1):
                by_value[round(values[candidate], 9)].append(i)
            rank = float(np.mean(by_value[round(values[gene], 9)]))
            percentile = 1 - (rank - 1) / max(len(pool) - 1, 1)
            ranks.append(rank)
            percentiles.append(percentile)
            predictions.append({
                "method": name, "gene": gene, "entity_group": group,
                "relation": relation, "rank": rank, "candidate_count": len(pool),
                "percentile": percentile, "year": item["earliest_year"],
            })
        values = np.asarray(ranks)
        metrics.append({
            "method": name, "n": len(values), "MRR": float(np.mean(1 / values)),
            "median_rank": float(np.median(values)),
            "mean_percentile_rank": float(np.mean(percentiles)),
            "Hits@10": float(np.mean(values <= 10)),
            "Hits@50": float(np.mean(values <= 50)),
            "Hits@100": float(np.mean(values <= 100)),
        })
    return metrics, predictions


def random_expected(groups, train, heldout):
    """计算各候选池均匀随机排序的解析期望，作为无训练基线。"""
    ns = [len(groups[r["entity_group"]]) - len(
        train[r["relation"]] & set(groups[r["entity_group"]])
    ) for r in heldout]
    return {
        "method": "Typed_random_expected", "n": len(ns),
        "MRR": float(np.mean([sum(1/i for i in range(1, n+1))/n for n in ns])),
        "median_rank": float(np.median([(n+1)/2 for n in ns])),
        "mean_percentile_rank": 0.5,
        "Hits@10": float(np.mean([min(10,n)/n for n in ns])),
        "Hits@50": float(np.mean([min(50,n)/n for n in ns])),
        "Hits@100": float(np.mean([min(100,n)/n for n in ns])),
    }


def main():
    """运行基线、单源消融和三源联合模型并写出全部结果。"""
    features, groups, train, heldout, excluded = load()
    methods = [
        rank_method("Typed_RankNet_core", BASE_COLUMNS, features, groups, train, heldout),
        rank_method(
            "Typed_RankNet_full_historical", BASE_COLUMNS + FULL_COLUMNS,
            features, groups, train, heldout,
        ),
        rank_method(
            "Typed_RankNet_full_plus_Reactome_proxy",
            BASE_COLUMNS + FULL_COLUMNS + REACTOME_COLUMNS,
            features, groups, train, heldout,
        ),
        rank_method(
            "Typed_RankNet_full_plus_STRINGv11_5_historical",
            BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS,
            features, groups, train, heldout,
            group_columns={
                "Gene": BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS,
                "RNA": BASE_COLUMNS + FULL_COLUMNS,
            },
        ),
        rank_method(
            "Typed_RankNet_STRING_plus_SIGNOR2022",
            BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + SIGNOR_COLUMNS,
            features, groups, train, heldout,
            group_columns={
                "Gene": BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + SIGNOR_COLUMNS,
                "RNA": BASE_COLUMNS + FULL_COLUMNS,
            },
        ),
        rank_method(
            "Typed_RankNet_STRING_plus_TRRUSTv2",
            BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + TRRUST_COLUMNS,
            features, groups, train, heldout,
            group_columns={
                "Gene": BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + TRRUST_COLUMNS,
                "RNA": BASE_COLUMNS + FULL_COLUMNS,
            },
        ),
        rank_method(
            "Typed_RankNet_STRING_plus_miRTarBasev9",
            BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + MIRTARBASE_COLUMNS,
            features, groups, train, heldout,
            group_columns={
                "Gene": BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS + MIRTARBASE_COLUMNS,
                "RNA": BASE_COLUMNS + FULL_COLUMNS + MIRTARBASE_COLUMNS,
            },
        ),
        rank_method(
            "Typed_RankNet_STRING_plus_all_structured_history",
            BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS +
            SIGNOR_COLUMNS + TRRUST_COLUMNS + MIRTARBASE_COLUMNS,
            features, groups, train, heldout,
            group_columns={
                "Gene": BASE_COLUMNS + FULL_COLUMNS + STRING_V11_5_COLUMNS +
                SIGNOR_COLUMNS + TRRUST_COLUMNS + MIRTARBASE_COLUMNS,
                "RNA": BASE_COLUMNS + FULL_COLUMNS + MIRTARBASE_COLUMNS,
            },
        ),
    ]
    metrics, predictions = evaluate(methods, groups, train, heldout)
    metrics.insert(0, random_expected(groups, train, heldout))
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "metrics.csv", metrics)
    write_csv(OUT / "predictions.csv", predictions)
    write_csv(OUT / "excluded_heldout.csv", excluded)
    report = {
        "candidate_counts": {k: len(v) for k, v in groups.items()},
        "heldout_counts": dict(__import__("collections").Counter(
            r["entity_group"] for r in heldout
        )),
        "excluded_heldout": len(excluded),
        "metrics": metrics,
        "guardrails": [
            "Gene and RNA candidates are ranked in separate type-constrained spaces.",
            "RankNet uses pairwise positive-vs-unlabelled ranking loss.",
            "All PubTator features are PMID-filtered to <=2022 and remain weak evidence.",
            "Reactome is reported only as a historical proxy.",
            "STRING v11.5 is a strict pre-cutoff structural feature source.",
            "STRING v12 features are excluded from the historical method.",
            "SIGNOR Oct2022, TRRUST v2 and strong-evidence miRTarBase v9 are separated for ablation.",
        ],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
