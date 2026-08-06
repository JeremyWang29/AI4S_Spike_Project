"""Generate relation-aware features from the normalized graph."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "codex-output" / "temporal_probe" / "normalized_graph"
OUT = GRAPH / "advanced_gene_features.csv"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def entropy(counter):
    total = sum(counter.values())
    if not total:
        return 0.0
    return -sum((v / total) * math.log(v / total) for v in counter.values())


def main():
    base = read_csv(GRAPH / "gene_features.csv")
    by_gene = {row["gene"]: row for row in base}
    nodes = read_csv(GRAPH / "nodes.csv")
    id_to_name = {row["node_id"]: row["name"] for row in nodes}
    strict = read_csv(GRAPH / "strict_historical_edges.csv")
    promote, suppress = set(), set()
    for edge in strict:
        if edge["source"] != "FerrDb":
            continue
        symbol = id_to_name.get(edge["source_id"], edge["source_id"].split(":", 1)[-1])
        if edge["relation"] == "PROMOTES_FERROPTOSIS":
            promote.add(symbol)
        elif edge["relation"] == "SUPPRESSES_FERROPTOSIS":
            suppress.add(symbol)

    values = defaultdict(Counter)
    neighbours = defaultdict(set)
    relation_counts = defaultdict(Counter)
    pmid_sets = defaultdict(set)
    for edge in strict:
        if edge["source"] != "PubTator3":
            continue
        left, right = id_to_name.get(edge["source_id"]), id_to_name.get(edge["target_id"])
        if not left or not right or left == right:
            continue
        year = int(edge["year"])
        pmids = {p for p in edge["pmid"].split(";") if p}
        evidence = max(len(pmids), 1)
        decay = math.exp(-(2022 - year) / 5)
        weight = math.log1p(evidence) * decay
        relation = edge["relation"].lower()
        for symbol, other in ((left, right), (right, left)):
            neighbours[symbol].add(other)
            relation_counts[symbol][relation] += 1
            pmid_sets[symbol].update(pmids)
            values[symbol]["strict_temporal_evidence_weight"] += weight
            values[symbol]["strict_recent_edge_count"] += int(year >= 2020)
            values[symbol]["strict_old_edge_count"] += int(year < 2020)
            if other in promote:
                values[symbol]["strict_promoter_neighbour_count"] += 1
                values[symbol]["strict_promoter_neighbour_weight"] += weight
                values[symbol][f"strict_{relation}_promoter_weight"] += weight
            if other in suppress:
                values[symbol]["strict_suppressor_neighbour_count"] += 1
                values[symbol]["strict_suppressor_neighbour_weight"] += weight
                values[symbol][f"strict_{relation}_suppressor_weight"] += weight
    for symbol in by_gene:
        values[symbol]["strict_unique_neighbour_count"] = len(neighbours[symbol])
        values[symbol]["strict_unique_pmid_count"] = len(pmid_sets[symbol])
        values[symbol]["strict_relation_entropy"] = entropy(relation_counts[symbol])
        edge_count = sum(relation_counts[symbol].values())
        values[symbol]["strict_evidence_per_edge"] = (
            len(pmid_sets[symbol]) / edge_count if edge_count else 0
        )

    def membership_features(filename, prefix):
        edges = read_csv(GRAPH / filename)
        memberships = defaultdict(set)
        members = defaultdict(set)
        for edge in edges:
            left = id_to_name.get(edge["source_id"])
            if not left:
                continue
            target = edge["target_id"] if prefix == "reactome" else id_to_name.get(edge["target_id"])
            if not target:
                continue
            memberships[left].add(target)
            members[target].add(left)
            if prefix == "string":
                memberships[target].add(left)
                members[left].add(target)
        for symbol, groups in memberships.items():
            for group in groups:
                group_members = members[group]
                p = len(group_members & promote)
                s = len(group_members & suppress)
                denom = math.log2(len(group_members) + 2)
                values[symbol][f"{prefix}_promoter_context_count"] += p
                values[symbol][f"{prefix}_suppressor_context_count"] += s
                values[symbol][f"{prefix}_promoter_context_weight"] += p / denom
                values[symbol][f"{prefix}_suppressor_context_weight"] += s / denom

    membership_features("reactome_historical_proxy_edges.csv", "reactome")
    membership_features("string_v12_ablation_edges.csv", "string")

    advanced_fields = [
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
        "reactome_promoter_context_count", "reactome_suppressor_context_count",
        "reactome_promoter_context_weight", "reactome_suppressor_context_weight",
        "string_promoter_context_count", "string_suppressor_context_count",
        "string_promoter_context_weight", "string_suppressor_context_weight",
    ]
    fields = list(base[0]) + advanced_fields
    rows = []
    for row in base:
        item = dict(row)
        for field in advanced_fields:
            item[field] = values[row["gene"]].get(field, 0)
        rows.append(item)
    write_csv(OUT, rows, fields)
    report = {
        "entities": len(rows),
        "historical_promoters": len(promote),
        "historical_suppressors": len(suppress),
        "entities_with_strict_role_neighbours": sum(
            bool(values[g]["strict_promoter_neighbour_count"]
                 or values[g]["strict_suppressor_neighbour_count"])
            for g in by_gene
        ),
        "entities_with_reactome_role_context": sum(
            bool(values[g]["reactome_promoter_context_count"]
                 or values[g]["reactome_suppressor_context_count"])
            for g in by_gene
        ),
        "entities_with_string_role_context": sum(
            bool(values[g]["string_promoter_context_count"]
                 or values[g]["string_suppressor_context_count"])
            for g in by_gene
        ),
        "feature_count_added": len(advanced_fields),
    }
    (GRAPH / "advanced_feature_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
