"""Build the full candidate-to-candidate PubTator historical neighbourhood."""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
MERGED = ROOT / "codex-output" / "graph_merge" / "edges.csv"
GRAPH = ROOT / "codex-output" / "temporal_probe" / "normalized_graph"
CACHE = ROOT / "codex-data" / "temporal_probe" / "cache"
DB = CACHE / "pubmed_years.sqlite"
OUT_EDGES = GRAPH / "full_pubtator_historical_edges.csv"
OUT_FEATURES = GRAPH / "full_neighborhood_features.csv"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def init_db():
    CACHE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS years (pmid TEXT PRIMARY KEY, year INTEGER)")
    old = CACHE / "pubmed_years.json"
    if old.exists() and not db.execute("SELECT 1 FROM years LIMIT 1").fetchone():
        values = json.loads(old.read_text(encoding="utf-8"))
        db.executemany("INSERT OR IGNORE INTO years VALUES (?,?)", values.items())
        db.commit()
    return db


def fetch_missing(db, pmids, email=""):
    known = {row[0] for row in db.execute("SELECT pmid FROM years")}
    missing = sorted(set(pmids) - known, key=int)
    batches = [missing[start:start + 500] for start in range(0, len(missing), 500)]

    def fetch_batch(batch):
        session = requests.Session()
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
        if email:
            params["email"] = email
        for attempt in range(5):
            try:
                response = session.post(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                    data=params, timeout=60,
                )
                response.raise_for_status()
                payload = response.json()["result"]
                records = []
                for pmid in batch:
                    item = payload.get(pmid, {})
                    match = re.search(
                        r"(19|20)\d{2}",
                        item.get("pubdate", "") or item.get("sortpubdate", ""),
                    )
                    records.append((pmid, int(match.group()) if match else None))
                return records
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        return []

    completed = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = []
        for batch in batches:
            futures.append(pool.submit(fetch_batch, batch))
            # NCBI permits at most three requests/second without an API key.
            time.sleep(0.34)
        for future in as_completed(futures):
            records = future.result()
            db.executemany("INSERT OR REPLACE INTO years VALUES (?,?)", records)
            db.commit()
            completed += len(records)
            if completed and completed % 10000 == 0:
                print(f"years: {completed}/{len(missing)}", flush=True)
    return len(missing)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    nodes = read_csv(GRAPH / "nodes.csv")
    candidate_ids = {
        row["node_id"] for row in nodes
        if row["node_type"] in {
            "Gene", "RNA", "RNA_or_other", "lncRNA", "miRNA", "CircRNA",
            "Gene_or_other_locus",
        }
    }
    # The merged graph uses gene:SYMBOL IDs. Normalized aliases are recovered
    # from source_symbols in the feature table.
    source_to_canonical = {}
    for row in read_csv(GRAPH / "gene_features.csv"):
        for source in row.get("source_symbols", row["gene"]).split("|"):
            source_to_canonical[f"gene:{source}"] = row["gene"]
    selected, pmids = [], set()
    with MERGED.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["database"] != "PubTator3":
                continue
            left = source_to_canonical.get(row["source_id"])
            right = source_to_canonical.get(row["target_id"])
            if not left or not right or left == right:
                continue
            selected.append((left, row["relation"].upper(), right, row["pmid"]))
            pmids.add(row["pmid"])
    db = init_db()
    fetched = 0 if args.offline else fetch_missing(db, pmids, args.email)
    years = dict(db.execute(
        f"SELECT pmid,year FROM years WHERE pmid IN ({','.join('?' * len(pmids))})",
        tuple(pmids),
    )) if len(pmids) < 900 else {
        pmid: year for pmid, year in db.execute("SELECT pmid,year FROM years")
        if pmid in pmids
    }
    grouped = {}
    for left, relation, right, pmid in selected:
        year = years.get(pmid)
        if not year or year > 2022:
            continue
        key = left, relation, right
        value = grouped.setdefault(key, {"pmids": set(), "years": []})
        value["pmids"].add(pmid)
        value["years"].append(year)
    role_edges = read_csv(GRAPH / "strict_historical_edges.csv")
    promoters = {
        row["source_id"].split(":", 1)[1] for row in role_edges
        if row["source"] == "FerrDb" and row["relation"] == "PROMOTES_FERROPTOSIS"
    }
    suppressors = {
        row["source_id"].split(":", 1)[1] for row in role_edges
        if row["source"] == "FerrDb" and row["relation"] == "SUPPRESSES_FERROPTOSIS"
    }
    edges = []
    features = defaultdict(Counter)
    neighbours, relations = defaultdict(set), defaultdict(Counter)
    for (left, relation, right), evidence in grouped.items():
        pmid_values = sorted(evidence["pmids"], key=int)
        first, last = min(evidence["years"]), max(evidence["years"])
        weight = math.log1p(len(pmid_values)) * math.exp(-(2022 - last) / 5)
        edges.append({
            "source": left, "target": right, "relation": relation,
            "first_year": first, "last_year": last,
            "pmid_count": len(pmid_values), "pmids": ";".join(pmid_values),
            "weak_evidence": "true",
        })
        for symbol, other in ((left, right), (right, left)):
            neighbours[symbol].add(other)
            relations[symbol][relation] += 1
            features[symbol]["full_pub_edge_count"] += 1
            features[symbol]["full_pub_pmid_count"] += len(pmid_values)
            features[symbol]["full_pub_temporal_weight"] += weight
            features[symbol]["full_pub_recent_edge_count"] += int(last >= 2020)
            features[symbol][f"full_pub_{relation.lower()}_count"] += 1
            if other in promoters:
                features[symbol]["full_pub_promoter_neighbour_count"] += 1
                features[symbol]["full_pub_promoter_neighbour_weight"] += weight
                features[symbol][f"full_pub_{relation.lower()}_promoter_weight"] += weight
            if other in suppressors:
                features[symbol]["full_pub_suppressor_neighbour_count"] += 1
                features[symbol]["full_pub_suppressor_neighbour_weight"] += weight
                features[symbol][f"full_pub_{relation.lower()}_suppressor_weight"] += weight
    feature_fields = [
        "gene", "full_pub_edge_count", "full_pub_pmid_count",
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
    feature_rows = []
    all_genes = {row["gene"] for row in read_csv(GRAPH / "gene_features.csv")}
    for gene in sorted(all_genes):
        item = {field: 0 for field in feature_fields}
        item["gene"] = gene
        for key, value in features[gene].items():
            if key in item:
                item[key] = value
        item["full_pub_unique_neighbour_count"] = len(neighbours[gene])
        total = sum(relations[gene].values())
        item["full_pub_relation_entropy"] = -sum(
            (v / total) * math.log(v / total) for v in relations[gene].values()
        ) if total else 0
        feature_rows.append(item)
    edge_fields = [
        "source", "target", "relation", "first_year", "last_year",
        "pmid_count", "pmids", "weak_evidence",
    ]
    write_csv(OUT_EDGES, edges, edge_fields)
    write_csv(OUT_FEATURES, feature_rows, feature_fields)
    report = {
        "candidate_entities": len(all_genes),
        "prefilter_edges": len(selected),
        "unique_pmids": len(pmids),
        "newly_fetched_pmids": fetched,
        "unresolved_pmids": sum(years.get(p) is None for p in pmids),
        "historical_aggregated_edges": len(edges),
        "entities_with_full_historical_neighbourhood": sum(
            bool(row["full_pub_edge_count"]) for row in feature_rows
        ),
        "relations": dict(Counter(row["relation"] for row in edges)),
    }
    (GRAPH / "full_neighborhood_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
