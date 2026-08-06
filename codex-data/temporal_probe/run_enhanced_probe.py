"""Rerun the temporal probe on normalized historical features."""
from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "codex-output" / "temporal_probe"
GRAPH = BASE / "normalized_graph"
OUT = BASE / "enhanced_results"
RELATIONS = ("PROMOTES_FERROPTOSIS", "SUPPRESSES_FERROPTOSIS")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalization_map():
    result = {}
    for row in read_csv(GRAPH / "normalization_decisions.csv"):
        if row["normalization_status"] == "accepted":
            result[row["original_symbol"]] = row["canonical_symbol"]
        else:
            result[row["original_symbol"]] = None
    return result


def prepare():
    decisions = normalization_map()
    nodes = read_csv(GRAPH / "nodes.csv")
    valid_ids = {
        row["node_id"]: row for row in nodes
        if row["node_type"] in {
            "Gene", "RNA", "lncRNA", "miRNA", "CircRNA",
            "Gene_or_other_locus", "RNA_or_other",
        }
    }
    feature_path = (
        GRAPH / "advanced_gene_features.csv"
        if (GRAPH / "advanced_gene_features.csv").exists()
        else GRAPH / "gene_features.csv"
    )
    features = {row["gene"]: row for row in read_csv(feature_path)}
    candidates = sorted({
        node["name"] for node_id, node in valid_ids.items()
        if node["name"] in features
    })
    strict_edges = read_csv(GRAPH / "strict_historical_edges.csv")
    train = defaultdict(set)
    for edge in strict_edges:
        if edge["source"] == "FerrDb" and edge["relation"] in RELATIONS:
            symbol = edge["source_id"].split(":", 1)[1]
            train[edge["relation"]].add(symbol)
    heldout, excluded = [], []
    for row in read_csv(BASE / "heldout_edges.csv"):
        canonical = decisions.get(row["symbol"], row["symbol"])
        if canonical is None or canonical not in candidates:
            excluded.append({**row, "reason": "nonhuman_ambiguous_or_no_model_features"})
            continue
        heldout.append({
            **row, "original_symbol": row["symbol"], "symbol": canonical,
        })
    # Deduplicate after alias normalization.
    unique = {}
    for row in heldout:
        unique[(row["symbol"], row["relation"])] = row
    return candidates, features, train, list(unique.values()), excluded, strict_edges


STRICT_FEATURES = [
    "pubtator_core_edge_count", "pubtator_core_pmid_count",
    "pubtator_unique_core_neighbours", "pubtator_associate_edge_count",
    "pubtator_positive_correlate_edge_count", "pubtator_negative_correlate_edge_count",
    "pubtator_interact_edge_count", "pubtator_pre2021_pmid_count",
    "pubtator_2021_2022_pmid_count", "pubtator_first_year", "pubtator_last_year",
]
REACTOME_FEATURES = ["reactome_pre2023_pathway_count", "reactome_relevant_pathway_count"]
STRING_FEATURES = ["string_v12_degree", "string_v12_core_neighbours", "string_v12_mean_score"]
ADVANCED_STRICT_FEATURES = [
    "strict_unique_neighbour_count", "strict_unique_pmid_count",
    "strict_temporal_evidence_weight", "strict_recent_edge_count",
    "strict_old_edge_count", "strict_relation_entropy", "strict_evidence_per_edge",
    "strict_promoter_neighbour_count", "strict_suppressor_neighbour_count",
    "strict_promoter_neighbour_weight", "strict_suppressor_neighbour_weight",
    "strict_associate_promoter_weight", "strict_associate_suppressor_weight",
    "strict_positive_correlate_promoter_weight",
    "strict_positive_correlate_suppressor_weight",
    "strict_negative_correlate_promoter_weight",
    "strict_negative_correlate_suppressor_weight",
    "strict_interact_promoter_weight", "strict_interact_suppressor_weight",
]
ADVANCED_REACTOME_FEATURES = [
    "reactome_promoter_context_count", "reactome_suppressor_context_count",
    "reactome_promoter_context_weight", "reactome_suppressor_context_weight",
]
ADVANCED_STRING_FEATURES = [
    "string_promoter_context_count", "string_suppressor_context_count",
    "string_promoter_context_weight", "string_suppressor_context_weight",
]


def matrix(candidates, features, columns, relation):
    rows = []
    opposite = (
        "ferrdb_suppressor_pre2023"
        if relation == "PROMOTES_FERROPTOSIS"
        else "ferrdb_promoter_pre2023"
    )
    for symbol in candidates:
        row = features[symbol]
        values = [float(row.get(col, 0) or 0) for col in columns]
        values.append(float(row.get(opposite, 0) or 0))
        # Missingness is informative for cold-start handling.
        values += [
            float(any(float(row.get(col, 0) or 0) > 0 for col in STRICT_FEATURES)),
            float(row["node_type"] != "Gene"),
        ]
        rows.append(values)
    x = np.asarray(rows, dtype=np.float32)
    # log1p counts, preserve years by converting them to recency.
    for j, col in enumerate(columns):
        if col in {"pubtator_first_year", "pubtator_last_year"}:
            value = x[:, j]
            x[:, j] = np.where(value > 0, 2022 - value, 50)
        elif col != "string_v12_mean_score":
            x[:, j] = np.log1p(np.maximum(x[:, j], 0))
    mean, std = x.mean(0), x.std(0)
    std[std < 1e-6] = 1
    return (x - mean) / std


def fit_ranker(x, candidates, positives, heldout_symbols, seed):
    """PU-style logistic ranker with future positives filtered from negatives."""
    rng = np.random.default_rng(seed)
    index = {g: i for i, g in enumerate(candidates)}
    pos_idx = np.asarray([index[g] for g in positives if g in index], dtype=int)
    pool = np.asarray([
        i for i, g in enumerate(candidates)
        if g not in positives and g not in heldout_symbols
    ], dtype=int)
    # Three unlabeled examples per positive; repeated seeds quantify sampling variance.
    neg_idx = rng.choice(pool, size=min(len(pool), 3 * len(pos_idx)), replace=False)
    selected = np.concatenate([pos_idx, neg_idx])
    y = np.concatenate([np.ones(len(pos_idx)), np.zeros(len(neg_idx))]).astype(np.float32)
    xt = torch.tensor(x[selected])
    yt = torch.tensor(y)
    torch.manual_seed(seed)
    model = torch.nn.Linear(x.shape[1], 1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.03, weight_decay=0.02)
    positive_weight = torch.tensor([len(neg_idx) / max(len(pos_idx), 1)])
    for _ in range(350):
        logits = model(xt).squeeze(1)
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            logits, yt, pos_weight=positive_weight
        )
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        return model(torch.tensor(x)).squeeze(1).numpy()


def feature_scores(candidates, features, train, heldout, columns, seeds=range(10)):
    result = {}
    for relation in RELATIONS:
        x = matrix(candidates, features, columns, relation)
        future = {r["symbol"] for r in heldout if r["relation"] == relation}
        runs = [
            fit_ranker(x, candidates, train[relation], future, 20260731 + seed)
            for seed in seeds
        ]
        result[relation] = dict(zip(candidates, np.mean(runs, axis=0).tolist()))
    return result


def ppr_scores(candidates, train, edge_files):
    adjacency = defaultdict(set)
    for filename in edge_files:
        for edge in read_csv(GRAPH / filename):
            if edge["source"] == "FerrDb":
                continue
            left, right = edge["source_id"], edge["target_id"]
            adjacency[left].add(right)
            adjacency[right].add(left)
    nodes = set(adjacency)
    result = {}
    for relation in RELATIONS:
        seeds = {f"gene:{g}" for g in train[relation] if f"gene:{g}" in nodes}
        if not seeds:
            result[relation] = {g: 0.0 for g in candidates}
            continue
        p = {node: (1 / len(seeds) if node in seeds else 0.0) for node in nodes}
        restart = dict(p)
        for _ in range(80):
            updated = {node: 0.15 * restart[node] for node in nodes}
            dangling = sum(p[node] for node in nodes if not adjacency[node])
            for node in nodes:
                updated[node] += 0.85 * dangling * restart[node]
            for source in nodes:
                if adjacency[source]:
                    share = 0.85 * p[source] / len(adjacency[source])
                    for target in adjacency[source]:
                        updated[target] += share
            if sum(abs(updated[n] - p[n]) for n in nodes) < 1e-11:
                p = updated
                break
            p = updated
        result[relation] = {g: p.get(f"gene:{g}", 0.0) for g in candidates}
    return result


def metrics(ranks):
    values = np.asarray(ranks, dtype=float)
    return {
        "n": len(ranks), "MRR": float(np.mean(1 / values)),
        "median_rank": float(np.median(values)),
        "mean_percentile_rank": float(np.mean(1 - (values - 1) / np.asarray(
            [n for _, n in ranks.context] if hasattr(ranks, "context") else [1] * len(ranks)
        ))) if False else None,
        "Hits@10": float(np.mean(values <= 10)),
        "Hits@50": float(np.mean(values <= 50)),
        "Hits@100": float(np.mean(values <= 100)),
    }


def evaluate(methods, candidates, train, heldout):
    result_rows, prediction_rows = [], []
    for method, scores_by_relation in methods.items():
        ranks, percentiles = [], []
        for relation in RELATIONS:
            known = train[relation]
            pool = [g for g in candidates if g not in known]
            scores = scores_by_relation[relation]
            ordered = sorted(pool, key=lambda g: (-scores.get(g, -math.inf), g))
            # Average tie rank, avoiding alphabetical artefacts.
            by_score = defaultdict(list)
            for i, gene in enumerate(ordered, 1):
                by_score[round(float(scores.get(gene, -math.inf)), 10)].append(i)
            rank = {
                gene: float(np.mean(by_score[round(float(scores.get(gene, -math.inf)), 10)]))
                for gene in pool
            }
            for row in heldout:
                if row["relation"] != relation:
                    continue
                value = rank[row["symbol"]]
                ranks.append(value)
                percentiles.append(1 - (value - 1) / max(len(pool) - 1, 1))
                prediction_rows.append({
                    "method": method, "gene": row["symbol"],
                    "original_symbol": row["original_symbol"], "relation": relation,
                    "rank": value, "candidate_count": len(pool),
                    "percentile": percentiles[-1], "earliest_year": row["earliest_year"],
                })
        row = {"method": method, **metrics(ranks)}
        row["mean_percentile_rank"] = float(np.mean(percentiles))
        result_rows.append(row)
    return result_rows, prediction_rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main():
    candidates, features, train, heldout, excluded, strict_edges = prepare()
    methods = {
        "PPR_strict": ppr_scores(candidates, train, ["strict_historical_edges.csv"]),
        "FeatureRanker_strict": feature_scores(
            candidates, features, train, heldout, STRICT_FEATURES
        ),
        "FeatureRanker_plus_Reactome_proxy": feature_scores(
            candidates, features, train, heldout, STRICT_FEATURES + REACTOME_FEATURES
        ),
        "FeatureRanker_plus_STRINGv12_ablation": feature_scores(
            candidates, features, train, heldout,
            STRICT_FEATURES + REACTOME_FEATURES + STRING_FEATURES
        ),
        "AdvancedFeatureRanker_strict": feature_scores(
            candidates, features, train, heldout,
            STRICT_FEATURES + ADVANCED_STRICT_FEATURES
        ),
        "AdvancedFeatureRanker_plus_Reactome_proxy": feature_scores(
            candidates, features, train, heldout,
            STRICT_FEATURES + ADVANCED_STRICT_FEATURES
            + REACTOME_FEATURES + ADVANCED_REACTOME_FEATURES
        ),
        "AdvancedFeatureRanker_plus_STRINGv12_ablation": feature_scores(
            candidates, features, train, heldout,
            STRICT_FEATURES + ADVANCED_STRICT_FEATURES
            + REACTOME_FEATURES + ADVANCED_REACTOME_FEATURES
            + STRING_FEATURES + ADVANCED_STRING_FEATURES
        ),
    }
    metrics_rows, predictions = evaluate(methods, candidates, train, heldout)
    random_components = []
    for item in heldout:
        n = len(candidates) - len(train[item["relation"]])
        harmonic = sum(1 / rank for rank in range(1, n + 1))
        random_components.append({
            "mrr": harmonic / n, "n": n,
            "h10": min(10, n) / n, "h50": min(50, n) / n,
            "h100": min(100, n) / n,
        })
    random_expected = {
        "method": "Random_expected",
        "n": len(heldout),
        "MRR": float(np.mean([r["mrr"] for r in random_components])),
        "median_rank": float(np.median([(r["n"] + 1) / 2 for r in random_components])),
        "mean_percentile_rank": 0.5,
        "Hits@10": float(np.mean([r["h10"] for r in random_components])),
        "Hits@50": float(np.mean([r["h50"] for r in random_components])),
        "Hits@100": float(np.mean([r["h100"] for r in random_components])),
    }
    metrics_rows.insert(0, random_expected)
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "metrics.csv", metrics_rows)
    write_csv(OUT / "predictions.csv", predictions)
    write_csv(OUT / "excluded_heldout.csv", excluded)
    report = {
        "candidate_entities": len(candidates),
        "evaluated_heldout": len(heldout),
        "excluded_heldout": len(excluded),
        "train_positives": {k: len(v) for k, v in train.items()},
        "methods": ["Random_expected", *methods],
        "metrics": metrics_rows,
        "interpretation_guardrails": [
            "Feature rankers use filtered PU negative sampling; future positives are not sampled as negatives.",
            "PubTator is weak evidence but PMID-filtered to <=2022.",
            "Reactome is a historical proxy and must be reported separately.",
            "STRING v12 is current knowledge and is an ablation result only.",
            "Tie ranks are averaged rather than broken alphabetically.",
        ],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
