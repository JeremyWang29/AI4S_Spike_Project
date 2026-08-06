"""Extend the temporal probe with leakage-labelled historical neighbourhoods.

Strict layer:
  * FerrDb role edges with earliest PMID year <= 2022
  * PubTator gene-gene relations with PMID year <= 2022 (weak evidence)

Historical-proxy layer:
  * Reactome memberships whose pathway releaseDate is <= 2022.  This does not
    prove that the gene membership itself existed by 2022, so it is labelled
    proxy rather than strict.

Ablation-only layer:
  * STRING v12 cached topology. Current combined scores are retained for audit
    but must not be used by the main temporal model.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

from run_probe import CACHE as YEAR_CACHE, OUT as PROBE_OUT, fetch_years


ROOT = Path(__file__).resolve().parents[2]
MERGE = ROOT / "codex-data" / "graph_merge"
MERGE_OUT = ROOT / "codex-output" / "graph_merge"
OUT = ROOT / "codex-output" / "temporal_probe" / "extended_graph"
HGNC = MERGE / "raw" / "hgnc_complete_set.txt"
CACHE = MERGE / "cache"
CORE_GENES = {
    "GPX4", "SLC7A11", "ACSL4", "TFRC", "AIFM2", "GCLC", "GCLM",
    "NFE2L2", "KEAP1", "TP53", "SAT1", "ALOX15", "LPCAT3", "FTH1",
    "NCOA4", "HMOX1", "CDKN1A", "VDAC2", "VDAC3", "DHODH", "GCH1",
    "PRMT5", "ALKBH5", "STC2",
}
PATHWAY_TERMS = (
    "ferropt", "glutathione", "lipid peroxid", "iron", "reactive oxygen",
    "oxidative stress", "dna damage", "hypoxia",
)


def split_multi(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[|,]", value or "") if x.strip()]


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_hgnc():
    rows, by_symbol = [], {}
    with HGNC.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["status"] == "Approved":
                rows.append(row)
                by_symbol[row["symbol"]] = row
    return rows, by_symbol


def load_seed_symbols() -> set[str]:
    with (MERGE_OUT / "id_mapping.csv").open(encoding="utf-8-sig", newline="") as handle:
        return {row["approved_symbol"] for row in csv.DictReader(handle)}


def load_historical_ferrdb():
    path = PROBE_OUT / "historical_edges.csv"
    edges, features = [], defaultdict(Counter)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = row["symbol"]
            relation = row["relation"]
            edges.append({
                "source_id": f"gene:{symbol}", "target_id": "pathway:ferroptosis",
                "relation": relation, "source": "FerrDb", "pmid": ";".join(
                    re.findall(r"\d+", row.get("pmids", ""))
                ), "year": row["earliest_year"], "evidence_tier": "strict_historical",
                "weak_evidence": "false", "version": "FerrDb V3 filtered by PMID year",
                "score": "",
            })
            features[symbol]["ferrdb_historical_role_count"] += 1
            if relation == "PROMOTES_FERROPTOSIS":
                features[symbol]["ferrdb_promoter_pre2023"] = 1
            if relation == "SUPPRESSES_FERROPTOSIS":
                features[symbol]["ferrdb_suppressor_pre2023"] = 1
    return edges, features


def select_pubtator_core_edges(seeds: set[str]):
    selected, pmids = [], set()
    with (MERGE_OUT / "edges.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["database"] != "PubTator3":
                continue
            if not row["source_id"].startswith("gene:") or not row["target_id"].startswith("gene:"):
                continue
            left, right = row["source_id"][5:], row["target_id"][5:]
            if left not in seeds or right not in seeds:
                continue
            if left not in CORE_GENES and right not in CORE_GENES:
                continue
            selected.append((left, row["relation"], right, row["pmid"]))
            pmids.add(row["pmid"])
    return selected, pmids


def historical_pubtator(selected, years):
    grouped = {}
    for left, relation, right, pmid in selected:
        year = years.get(pmid)
        if not year or year > 2022:
            continue
        key = left, relation, right
        item = grouped.setdefault(key, {"pmids": set(), "years": []})
        item["pmids"].add(pmid)
        item["years"].append(year)
    edges, features = [], defaultdict(Counter)
    neighbours = defaultdict(set)
    for (left, relation, right), evidence in grouped.items():
        pmids = sorted(evidence["pmids"], key=int)
        earliest, latest = min(evidence["years"]), max(evidence["years"])
        edges.append({
            "source_id": f"gene:{left}", "target_id": f"gene:{right}",
            "relation": relation.upper(), "source": "PubTator3",
            "pmid": ";".join(pmids), "year": earliest,
            "evidence_tier": "weak_historical", "weak_evidence": "true",
            "version": "relation2pubtator3 filtered by PMID year",
            "score": len(pmids),
        })
        for symbol, other in ((left, right), (right, left)):
            features[symbol]["pubtator_core_edge_count"] += 1
            features[symbol]["pubtator_core_pmid_count"] += len(pmids)
            features[symbol][f"pubtator_{relation}_edge_count"] += 1
            features[symbol]["pubtator_2021_2022_pmid_count"] += sum(y >= 2021 for y in evidence["years"])
            features[symbol]["pubtator_pre2021_pmid_count"] += sum(y < 2021 for y in evidence["years"])
            neighbours[symbol].add(other)
            old = features[symbol].get("pubtator_first_year", 0)
            features[symbol]["pubtator_first_year"] = earliest if not old else min(old, earliest)
            features[symbol]["pubtator_last_year"] = max(
                features[symbol].get("pubtator_last_year", 0), latest
            )
    for symbol, values in neighbours.items():
        features[symbol]["pubtator_unique_core_neighbours"] = len(values & CORE_GENES)
    return edges, features


def cached_json(url: str, group: str):
    path = CACHE / group / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_reactome_proxy(seeds: set[str], hgnc_by_symbol: dict):
    edges, features, nodes = [], defaultdict(Counter), {}
    for symbol in sorted(seeds):
        row = hgnc_by_symbol.get(symbol)
        if not row:
            continue
        seen = set()
        for accession in split_multi(row.get("uniprot_ids", "")):
            url = f"https://reactome.org/ContentService/data/mapping/UniProt/{urllib.parse.quote(accession)}/pathways"
            pathways = cached_json(url, "reactome")
            if not pathways:
                continue
            for pathway in pathways:
                if pathway.get("speciesName") != "Homo sapiens":
                    continue
                release = pathway.get("releaseDate", "")
                match = re.match(r"(\d{4})", release)
                if not match or int(match.group()) > 2022:
                    continue
                stid = pathway.get("stId")
                if not stid or stid in seen:
                    continue
                seen.add(stid)
                name = pathway.get("displayName", stid)
                nodes[stid] = name
                edges.append({
                    "source_id": f"gene:{symbol}", "target_id": f"pathway:{stid}",
                    "relation": "PARTICIPATES_IN", "source": "Reactome",
                    "pmid": "", "year": int(match.group()),
                    "evidence_tier": "historical_proxy", "weak_evidence": "false",
                    "version": pathway.get("stIdVersion", ""),
                    "score": "",
                })
                features[symbol]["reactome_pre2023_pathway_count"] += 1
                if any(term in name.lower() for term in PATHWAY_TERMS):
                    features[symbol]["reactome_relevant_pathway_count"] += 1
    return edges, features, nodes


def load_string_ablation(seeds: set[str], hgnc_by_symbol: dict):
    symbols = sorted(seeds)
    seen, edges, features = set(), [], defaultdict(Counter)
    for start in range(0, len(symbols), 50):
        batch = symbols[start : start + 50]
        params = urllib.parse.urlencode({
            "identifiers": "\r".join(batch), "species": 9606, "limit": 20,
            "required_score": 700, "network_type": "functional",
            "caller_identity": "ferroptosis_kg_merge",
        })
        rows = cached_json("https://string-db.org/api/json/interaction_partners?" + params, "string")
        if not rows:
            continue
        for row in rows:
            left, right = row.get("preferredName_A"), row.get("preferredName_B")
            if left not in seeds or right not in seeds or left == right:
                continue
            key = tuple(sorted((left, right)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "source_id": f"gene:{key[0]}", "target_id": f"gene:{key[1]}",
                "relation": "INTERACTS_WITH", "source": "STRING",
                "pmid": "", "year": "", "evidence_tier": "current_static_ablation",
                "weak_evidence": "false", "version": "v12 current API cache",
                "score": row.get("score", ""),
            })
            for symbol, other in ((left, right), (right, left)):
                features[symbol]["string_v12_degree"] += 1
                features[symbol]["string_v12_core_neighbours"] += int(other in CORE_GENES)
                features[symbol]["string_v12_score_sum"] += float(row.get("score", 0))
    return edges, features


def merge_feature_maps(*maps):
    result = defaultdict(Counter)
    for feature_map in maps:
        for symbol, values in feature_map.items():
            result[symbol].update(values)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    hgnc_rows, hgnc_by_symbol = load_hgnc()
    seeds = load_seed_symbols()
    ferrdb_edges, ferrdb_features = load_historical_ferrdb()
    heldout_symbols = set()
    heldout_path = PROBE_OUT / "heldout_edges.csv"
    if heldout_path.exists():
        with heldout_path.open(encoding="utf-8-sig", newline="") as handle:
            heldout_symbols = {row["symbol"] for row in csv.DictReader(handle)}
    ferrdb_symbols = {edge["source_id"][5:] for edge in ferrdb_edges}
    all_symbols = seeds | ferrdb_symbols | heldout_symbols
    selected, pmids = select_pubtator_core_edges(seeds)
    year_path = YEAR_CACHE / "pubmed_years.json"
    years = json.loads(year_path.read_text(encoding="utf-8")) if year_path.exists() else {}
    if not args.offline:
        years = fetch_years(set(pmids), args.email)
    missing = set(pmids) - set(years)
    pub_edges, pub_features = historical_pubtator(selected, years)
    reactome_edges, reactome_features, pathway_nodes = load_reactome_proxy(seeds, hgnc_by_symbol)
    string_edges, string_features = load_string_ablation(seeds, hgnc_by_symbol)
    feature_map = merge_feature_maps(
        ferrdb_features, pub_features, reactome_features, string_features
    )
    nodes = [{
        "node_id": f"gene:{symbol}", "node_type": (
            "Gene" if hgnc_by_symbol[symbol].get("locus_group") == "protein-coding gene" else "RNA_or_other"
        ), "name": symbol, "hgnc_id": hgnc_by_symbol[symbol]["hgnc_id"],
        "entrez_id": hgnc_by_symbol[symbol]["entrez_id"],
        "locus_group": hgnc_by_symbol[symbol].get("locus_group", ""),
        "candidate_source": "current_FerrDb_HGNC_resolved",
    } for symbol in sorted(all_symbols) if symbol in hgnc_by_symbol]
    nodes.extend({
        "node_id": f"gene:{symbol}", "node_type": "unresolved_or_non_gene",
        "name": symbol, "hgnc_id": "", "entrez_id": "", "locus_group": "",
        "candidate_source": "FerrDb_unresolved_symbol",
    } for symbol in sorted(all_symbols) if symbol not in hgnc_by_symbol)
    nodes.append({
        "node_id": "pathway:ferroptosis", "node_type": "Pathway", "name": "Ferroptosis",
        "hgnc_id": "", "entrez_id": "", "locus_group": "", "candidate_source": "FerrDb",
    })
    nodes.extend({
        "node_id": f"pathway:{stid}", "node_type": "Pathway", "name": name,
        "hgnc_id": "", "entrez_id": "", "locus_group": "", "candidate_source": "Reactome",
    } for stid, name in sorted(pathway_nodes.items()))
    feature_fields = [
        "gene", "node_type", "ferrdb_historical_role_count", "ferrdb_promoter_pre2023",
        "ferrdb_suppressor_pre2023", "pubtator_core_edge_count",
        "pubtator_core_pmid_count", "pubtator_unique_core_neighbours",
        "pubtator_associate_edge_count", "pubtator_positive_correlate_edge_count",
        "pubtator_negative_correlate_edge_count", "pubtator_interact_edge_count",
        "pubtator_pre2021_pmid_count", "pubtator_2021_2022_pmid_count",
        "pubtator_first_year", "pubtator_last_year",
        "reactome_pre2023_pathway_count", "reactome_relevant_pathway_count",
        "string_v12_degree", "string_v12_core_neighbours", "string_v12_mean_score",
    ]
    feature_rows = []
    node_type_lookup = {
        node["node_id"][5:]: node["node_type"]
        for node in nodes if node["node_id"].startswith("gene:")
    }
    for symbol in sorted(all_symbols):
        values = feature_map[symbol]
        row = {field: 0 for field in feature_fields}
        row["gene"] = symbol
        row["node_type"] = node_type_lookup.get(symbol, "unresolved_or_non_gene")
        for key, value in values.items():
            if key in row:
                row[key] = value
        degree = values.get("string_v12_degree", 0)
        row["string_v12_mean_score"] = values.get("string_v12_score_sum", 0) / degree if degree else 0
        feature_rows.append(row)
    feature_by_gene = {row["gene"]: row for row in feature_rows}
    heldout_coverage = []
    if heldout_path.exists():
        with heldout_path.open(encoding="utf-8-sig", newline="") as handle:
            for item in csv.DictReader(handle):
                values = feature_by_gene.get(item["symbol"], {})
                heldout_coverage.append({
                    "gene": item["symbol"], "relation": item["relation"],
                    "earliest_year": item["earliest_year"],
                    "node_type": values.get("node_type", "unresolved_or_non_gene"),
                    "strict_pubtator_context": int(float(values.get("pubtator_core_edge_count", 0)) > 0),
                    "reactome_proxy_context": int(float(values.get("reactome_pre2023_pathway_count", 0)) > 0),
                    "string_v12_ablation_context": int(float(values.get("string_v12_degree", 0)) > 0),
                })
    strict_edges = ferrdb_edges + pub_edges
    proxy_edges = reactome_edges
    ablation_edges = string_edges
    edge_fields = [
        "source_id", "target_id", "relation", "source", "pmid", "year",
        "evidence_tier", "weak_evidence", "version", "score",
    ]
    node_fields = [
        "node_id", "node_type", "name", "hgnc_id", "entrez_id",
        "locus_group", "candidate_source",
    ]
    write_csv(OUT / "nodes.csv", nodes, node_fields)
    write_csv(OUT / "strict_historical_edges.csv", strict_edges, edge_fields)
    write_csv(OUT / "reactome_historical_proxy_edges.csv", proxy_edges, edge_fields)
    write_csv(OUT / "string_v12_ablation_edges.csv", ablation_edges, edge_fields)
    write_csv(OUT / "gene_features.csv", feature_rows, feature_fields)
    write_csv(
        OUT / "heldout_feature_coverage.csv", heldout_coverage,
        ["gene", "relation", "earliest_year", "node_type", "strict_pubtator_context",
         "reactome_proxy_context", "string_v12_ablation_context"],
    )
    report = {
        "cutoff": 2022,
        "candidate_entities": len(all_symbols),
        "hgnc_resolved_candidate_genes": len(all_symbols & set(hgnc_by_symbol)),
        "unresolved_or_non_gene_candidates": len(all_symbols - set(hgnc_by_symbol)),
        "core_genes_preregistered": sorted(CORE_GENES),
        "pubtator_prefilter_edges": len(selected),
        "pubtator_prefilter_pmids": len(pmids),
        "pubtator_unresolved_pmids": len(missing),
        "strict_edges": len(strict_edges),
        "strict_edges_by_source": dict(Counter(e["source"] for e in strict_edges)),
        "reactome_proxy_edges": len(proxy_edges),
        "string_ablation_edges": len(ablation_edges),
        "genes_with_historical_pubtator_core_context": sum(
            bool(r["pubtator_core_edge_count"]) for r in feature_rows
        ),
        "genes_with_historical_reactome_proxy": sum(
            bool(r["reactome_pre2023_pathway_count"]) for r in feature_rows
        ),
        "genes_with_string_v12_ablation_context": sum(
            bool(r["string_v12_degree"]) for r in feature_rows
        ),
        "heldout_feature_coverage": {
            "n": len(heldout_coverage),
            "strict_pubtator": sum(r["strict_pubtator_context"] for r in heldout_coverage),
            "reactome_proxy": sum(r["reactome_proxy_context"] for r in heldout_coverage),
            "string_v12_ablation": sum(r["string_v12_ablation_context"] for r in heldout_coverage),
            "any_context": sum(
                bool(r["strict_pubtator_context"] or r["reactome_proxy_context"]
                     or r["string_v12_ablation_context"])
                for r in heldout_coverage
            ),
        },
        "leakage_labels": {
            "strict_historical": "PMID publication year <= 2022",
            "weak_historical": "PubTator automatic extraction; PMID year <= 2022",
            "historical_proxy": "pathway releaseDate <= 2022; membership history not proven",
            "current_static_ablation": "current STRING v12 topology; never a main historical feature",
        },
        "known_limitations": [
            "Candidate membership is HGNC-resolved current FerrDb and therefore not a frozen 2022 candidate universe.",
            "Reactome pathway release date does not prove the gene membership date.",
            "PubTator relations are weak evidence and relation direction may be unreliable.",
            "STRING combined_score is current and excluded from the strict layer.",
        ],
    }
    (OUT / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
