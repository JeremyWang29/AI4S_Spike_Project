"""Leakage-aware temporal probe for FerrDb gene/ferroptosis-role links.

This is deliberately a narrow, auditable probe. FerrDb driver/suppressor rows
are NOT converted into gene-regulates-gene edges.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import requests
import torch


ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = next(p for p in ROOT.iterdir() if (p / "ferrdb").exists())
FERRDB = DATASET_DIR / "ferrdb"
OUT = ROOT / "codex-output" / "temporal_probe"
CACHE = ROOT / "codex-data" / "temporal_probe" / "cache"
ROLES = {
    "driver": "PROMOTES_FERROPTOSIS",
    "suppressor": "SUPPRESSES_FERROPTOSIS",
}


def split_pmids(value: str) -> list[str]:
    return [x for x in re.findall(r"\d+", value or "") if len(x) >= 6]


def read_role_rows(path: Path, category: str) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("RCD") != "Ferroptosis":
                continue
            symbol = (row.get("Symbol") or row.get("Symbol_or_reported_abbr") or "").strip().upper()
            if not symbol:
                continue
            pmids = split_pmids(row.get("PMID", ""))
            rows.append(
                {
                    "head": f"gene:{symbol}",
                    "relation": ROLES[category],
                    "tail": "pathway:ferroptosis",
                    "symbol": symbol,
                    "category": category,
                    "pmids": pmids,
                    "evidence": row.get("Evidence", ""),
                    "confidence": row.get("Confidence", ""),
                    "source_file": path.name,
                }
            )
    return rows


def fetch_years(pmids: set[str], email: str = "") -> dict[str, int]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / "pubmed_years.json"
    years = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    missing = sorted(pmids - years.keys(), key=int)
    session = requests.Session()
    for start in range(0, len(missing), 200):
        batch = missing[start : start + 200]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
        if email:
            params["email"] = email
        response = session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()["result"]
        for pmid in batch:
            rec = payload.get(pmid, {})
            match = re.search(r"(19|20)\d{2}", rec.get("pubdate", "") or rec.get("sortpubdate", ""))
            if match:
                years[pmid] = int(match.group())
        cache_path.write_text(json.dumps(years, indent=2, sort_keys=True), encoding="utf-8")
        time.sleep(0.35)
    return {k: int(v) for k, v in years.items()}


def earliest_year(row: dict, years: dict[str, int]) -> int | None:
    values = [years[p] for p in row["pmids"] if p in years]
    return min(values) if values else None


def aggregate(rows: list[dict], years: dict[str, int]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = row["head"], row["relation"], row["tail"]
        if key not in grouped:
            grouped[key] = {**row, "pmids": [], "evidence_records": 0}
        grouped[key]["pmids"].extend(row["pmids"])
        grouped[key]["evidence_records"] += 1
    for row in grouped.values():
        row["pmids"] = sorted(set(row["pmids"]), key=lambda x: int(x))
        row["earliest_year"] = earliest_year(row, years)
    return list(grouped.values())


def candidate_sets(train: list[dict], test: list[dict], universe: set[str]):
    known = {(r["head"], r["relation"]) for r in train}
    by_relation = defaultdict(list)
    for row in test:
        if (row["head"], row["relation"]) not in known:
            by_relation[row["relation"]].append(row)
    candidates = {
        rel: sorted(universe - {h for h, r in known if r == rel})
        for rel in by_relation
    }
    return by_relation, candidates


def ranks_to_metrics(ranks: list[int]) -> dict:
    a = np.asarray(ranks, dtype=float)
    return {
        "n": len(ranks),
        "MRR": float(np.mean(1.0 / a)),
        "median_rank": float(np.median(a)),
        "Hits@10": float(np.mean(a <= 10)),
        "Hits@50": float(np.mean(a <= 50)),
        "Hits@100": float(np.mean(a <= 100)),
    }


def classical_scores(train: list[dict], universe: set[str], seed: int):
    rng = random.Random(seed)
    degree = Counter(r["head"] for r in train)
    adjacency = defaultdict(set)
    for row in train:
        role_node = "role:" + row["relation"]
        adjacency[row["head"]].add(role_node)
        adjacency[role_node].add(row["head"])
        adjacency[role_node].add(row["tail"])
        adjacency[row["tail"]].add(role_node)
    nodes = sorted(set(universe) | set(adjacency))
    n = len(nodes)
    pagerank = {node: 1.0 / n for node in nodes}
    for _ in range(100):
        updated = {node: (1.0 - 0.85) / n for node in nodes}
        dangling = sum(pagerank[node] for node in nodes if not adjacency[node])
        for node in nodes:
            updated[node] += 0.85 * dangling / n
        for source in nodes:
            if adjacency[source]:
                share = 0.85 * pagerank[source] / len(adjacency[source])
                for target in adjacency[source]:
                    updated[target] += share
        if sum(abs(updated[x] - pagerank[x]) for x in nodes) < 1e-12:
            pagerank = updated
            break
        pagerank = updated
    return {
        "Random": {g: rng.random() for g in universe},
        "Degree": {g: float(degree[g]) for g in universe},
        "PageRank": {g: float(pagerank.get(g, 0.0)) for g in universe},
    }


def train_kge(train: list[dict], universe: set[str], model: str, seed: int, epochs: int = 250):
    torch.manual_seed(seed)
    entities = sorted(universe | {"pathway:ferroptosis"})
    relations = sorted(set(ROLES.values()))
    ei = {x: i for i, x in enumerate(entities)}
    ri = {x: i for i, x in enumerate(relations)}
    triples = torch.tensor([[ei[r["head"]], ri[r["relation"]], ei[r["tail"]]] for r in train])
    dim = 48
    ent = torch.nn.Embedding(len(entities), dim)
    rel = torch.nn.Embedding(len(relations), dim)
    torch.nn.init.uniform_(ent.weight, -0.1, 0.1)
    torch.nn.init.uniform_(rel.weight, -0.1, 0.1)
    opt = torch.optim.Adam([*ent.parameters(), *rel.parameters()], lr=0.02)
    n = len(triples)
    for _ in range(epochs):
        order = torch.randperm(n)
        for ix in order.split(256):
            pos = triples[ix]
            neg = pos.clone()
            neg[:, 0] = torch.randint(0, len(universe), (len(ix),))
            def score(x):
                h, r, t = ent(x[:, 0]), rel(x[:, 1]), ent(x[:, 2])
                if model == "RotatE":
                    half = dim // 2
                    hr, hi = h[:, :half], h[:, half:]
                    phase = r[:, :half]
                    rr, ii = torch.cos(phase), torch.sin(phase)
                    tr, ti = t[:, :half], t[:, half:]
                    return -torch.linalg.vector_norm(
                        torch.cat([hr * rr - hi * ii - tr, hr * ii + hi * rr - ti], 1), dim=1
                    )
                # ComplEx: Re(<h,r,conj(t)>)
                half = dim // 2
                hr, hi, rr, ii, tr, ti = (
                    h[:, :half], h[:, half:], r[:, :half], r[:, half:], t[:, :half], t[:, half:]
                )
                return (hr * rr * tr + hi * rr * ti + hr * ii * ti - hi * ii * tr).sum(1)
            loss = -torch.nn.functional.logsigmoid(score(pos)).mean()
            loss -= torch.nn.functional.logsigmoid(-score(neg)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    scores = {}
    with torch.no_grad():
        genes = sorted(universe)
        for relation in relations:
            x = torch.tensor([[ei[g], ri[relation], ei["pathway:ferroptosis"]] for g in genes])
            h, r, t = ent(x[:, 0]), rel(x[:, 1]), ent(x[:, 2])
            if model == "RotatE":
                half = dim // 2
                z = torch.cat([
                    h[:, :half] * torch.cos(r[:, :half]) - h[:, half:] * torch.sin(r[:, :half]) - t[:, :half],
                    h[:, :half] * torch.sin(r[:, :half]) + h[:, half:] * torch.cos(r[:, :half]) - t[:, half:],
                ], 1)
                value = -torch.linalg.vector_norm(z, dim=1)
            else:
                half = dim // 2
                value = (
                    h[:, :half] * r[:, :half] * t[:, :half]
                    + h[:, half:] * r[:, :half] * t[:, half:]
                    + h[:, :half] * r[:, half:] * t[:, half:]
                    - h[:, half:] * r[:, half:] * t[:, :half]
                ).sum(1)
            scores[relation] = dict(zip(genes, value.tolist()))
    return scores


def evaluate(by_relation, candidates, score_sets):
    results, predictions = [], []
    for method, rel_scores in score_sets.items():
        ranks = []
        for relation, positives in by_relation.items():
            scores = rel_scores[relation] if relation in rel_scores else rel_scores
            ordered = sorted(candidates[relation], key=lambda g: (-scores.get(g, -math.inf), g))
            rank = {g: i + 1 for i, g in enumerate(ordered)}
            for row in positives:
                ranks.append(rank[row["head"]])
                predictions.append({
                    "method": method, "relation": relation, "gene": row["symbol"],
                    "rank": rank[row["head"]], "candidate_count": len(ordered),
                    "earliest_year": row["earliest_year"], "pmids": ";".join(row["pmids"]),
                })
        results.append({"method": method, **ranks_to_metrics(ranks)})
    return results, predictions


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="")
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--max-test", type=int, default=50)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    early_dir = next(FERRDB.glob("*early*/*early*"))
    old, current = [], []
    for category in ROLES:
        old += read_role_rows(early_dir / f"{category}.csv", category)
        current += read_role_rows(FERRDB / f"ferrdb_{category}.csv", category)
    pmids = {p for r in current + old for p in r["pmids"]}
    if args.offline:
        years = json.loads((CACHE / "pubmed_years.json").read_text(encoding="utf-8"))
    else:
        years = fetch_years(pmids, args.email)
    old, current = aggregate(old, years), aggregate(current, years)
    train = [r for r in current if r["earliest_year"] and r["earliest_year"] <= 2022]
    post = [r for r in current if r["earliest_year"] and 2023 <= r["earliest_year"] <= 2026]
    old_keys = {(r["head"], r["relation"]) for r in old}
    heldout = [r for r in post if (r["head"], r["relation"]) not in old_keys]
    heldout.sort(key=lambda r: (r["earliest_year"], r["relation"], r["symbol"]))
    rng = random.Random(args.seed)
    rng.shuffle(heldout)
    heldout = heldout[: args.max_test]
    universe = {r["head"] for r in current}
    by_relation, candidates = candidate_sets(train, heldout, universe)
    classical = classical_scores(train, universe, args.seed)
    score_sets = {name: scores for name, scores in classical.items()}
    for model in ("ComplEx", "RotatE"):
        score_sets[model] = train_kge(train, universe, model, args.seed)
    results, predictions = evaluate(by_relation, candidates, score_sets)
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "historical_edges.csv", train)
    write_csv(OUT / "heldout_edges.csv", heldout)
    write_csv(OUT / "predictions.csv", predictions)
    write_csv(OUT / "metrics.csv", results)
    report = {
        "cutoff": "2022-12-31",
        "scope": "FerrDb gene-to-ferroptosis-role links only",
        "historical_edges": len(train),
        "post_2022_edges": len(post),
        "heldout_edges": len(heldout),
        "unresolved_pmid_count": len(pmids - years.keys()),
        "candidate_counts": {k: len(v) for k, v in candidates.items()},
        "models": [r["method"] for r in results],
        "leakage_controls": [
            "earliest PubMed year <= 2022 only in training",
            "FerrDb role semantics preserved; no gene-regulates-gene conversion",
            "FerrDb early-release membership used as a second held-out novelty check",
            "STRING v12, current Reactome and current ChEMBL excluded from main probe",
        ],
        "not_implemented_as_model": [
            "GraphRAG requires a frozen <=2022 text/graph corpus and is not approximated by an LLM over current knowledge"
        ],
    }
    (OUT / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({**report, "metrics": results}, indent=2))


if __name__ == "__main__":
    main()
