#!/usr/bin/env python3
"""Merge FerrDb, STRING, Reactome, PubTator3 and ChEMBL around FerrDb genes.

The script uses HGNC approved symbols as gene node keys.  HTTP responses are
cached as JSON so interrupted runs can be resumed without repeating requests.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "数据集"
WORK = ROOT / "codex-data" / "graph_merge"
RAW = WORK / "raw"
CACHE = WORK / "cache"
OUT = ROOT / "codex-output" / "graph_merge"
HGNC = RAW / "hgnc_complete_set.txt"
PUBTATOR = DATA / "relation2pubtator3.gz"
FERRDB = DATA / "ferrdb"
UA = "ferroptosis-kg-merge/1.0 (research; API clients)"


def split_multi(value: str):
    return [x.strip() for x in re.split(r"[|,]", value or "") if x.strip()]


def clean(value):
    value = "" if value is None else str(value)
    return "" if value in {"_NA_", "NA", "None", "null"} else value.strip()


class HgncMap:
    def __init__(self, path: Path):
        self.rows = {}
        self.lookup = {}
        self.ambiguous = set()
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if row["status"] != "Approved":
                    continue
                symbol = row["symbol"]
                self.rows[symbol] = row
                keys = [
                    row["hgnc_id"], symbol, row["entrez_id"],
                    row["ensembl_gene_id"], *split_multi(row["uniprot_ids"]),
                    *split_multi(row["alias_symbol"]), *split_multi(row["prev_symbol"]),
                ]
                for key in filter(None, keys):
                    for k in {key, key.upper(), key.split(".")[0]}:
                        old = self.lookup.get(k)
                        if old and old != symbol:
                            self.ambiguous.add(k)
                        else:
                            self.lookup[k] = symbol

    def symbol(self, identifier: str):
        key = clean(identifier)
        if not key:
            return None
        for candidate in (key, key.upper(), key.split(".")[0]):
            if candidate not in self.ambiguous and candidate in self.lookup:
                return self.lookup[candidate]
        return None


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def request_json(url, cache_group, retries=5):
    cache_dir = CACHE / cache_group
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as response:
                obj = json.load(response)
            path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            return obj
        except Exception:
            if attempt + 1 == retries:
                raise
            time.sleep(min(2 ** attempt, 20))


def load_ferrdb(hgnc):
    nodes, edges, seed_roles, provenance, unmapped = {}, [], defaultdict(set), [], []
    for category in ("driver", "suppressor", "marker"):
        path = FERRDB / f"ferrdb_{category}.csv"
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for i, row in enumerate(csv.DictReader(fh), 2):
                symbol = hgnc.symbol(row.get("HGNC_ID")) or hgnc.symbol(row.get("Symbol"))
                if not symbol:
                    unmapped.append({"source": "FerrDb", "file": path.name, "row": i,
                                     "identifier": clean(row.get("Symbol")), "reason": "not_in_HGNC"})
                    continue
                hr = hgnc.rows[symbol]
                nodes[("gene", symbol)] = {
                    "node_id": f"gene:{symbol}", "node_type": "gene", "name": symbol,
                    "hgnc_id": hr["hgnc_id"], "entrez_id": hr["entrez_id"],
                    "ensembl_gene_id": hr["ensembl_gene_id"],
                    "uniprot_ids": hr["uniprot_ids"], "source": "HGNC;FerrDb",
                }
                seed_roles[symbol].add(category)
                evidence_id = f"ferrdb:{category}:{i}"
                nodes[("evidence", evidence_id)] = {
                    "node_id": evidence_id, "node_type": "evidence", "name": evidence_id,
                    "source": "FerrDb",
                }
                edges.append({
                    "source_id": f"gene:{symbol}", "target_id": evidence_id,
                    "relation": f"ferroptosis_{category}", "database": "FerrDb",
                    "score": "", "pmid": clean(row.get("PMID")),
                    "evidence": clean(row.get("Evidence")), "attributes": "",
                })
                provenance.append({"evidence_id": evidence_id, "file": path.name, "row": i})
    # Disease effects are parsed as Ferroptosis <operator> Disease.
    path = FERRDB / "ferrdb_disease.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh), 2):
            effect = clean(row.get("Effect"))
            parts = re.split(r"\s+([:+-]+)\s+", effect, maxsplit=1)
            disease = parts[-1].strip() if len(parts) == 3 else effect
            did = "disease:FerrDb:" + re.sub(r"\W+", "_", disease).strip("_")
            nodes[("disease", did)] = {"node_id": did, "node_type": "disease",
                                       "name": disease, "source": "FerrDb"}
            edges.append({"source_id": "process:ferroptosis", "target_id": did,
                          "relation": "disease_association", "database": "FerrDb",
                          "score": "", "pmid": clean(row.get("PMID")),
                          "evidence": effect, "attributes": ""})
    nodes[("process", "process:ferroptosis")] = {
        "node_id": "process:ferroptosis", "node_type": "process",
        "name": "ferroptosis", "source": "FerrDb",
    }
    return nodes, edges, seed_roles, provenance, unmapped


def add_string(hgnc, seeds, nodes, edges, limit, required_score, workers):
    symbols = sorted(seeds)
    batches = [symbols[i:i + 50] for i in range(0, len(symbols), 50)]
    def fetch(batch):
        params = urllib.parse.urlencode({
            "identifiers": "\r".join(batch), "species": 9606, "limit": limit,
            "required_score": required_score, "network_type": "functional",
            "caller_identity": "ferroptosis_kg_merge",
        })
        return request_json("https://string-db.org/api/json/interaction_partners?" + params, "string")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, b) for b in batches]
        for future in as_completed(futures):
            results.extend(future.result())
    seen = set()
    for row in results:
        a = hgnc.symbol(row.get("preferredName_A"))
        b = hgnc.symbol(row.get("preferredName_B"))
        if not a or not b or (a not in seeds and b not in seeds):
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        for symbol in key:
            hr = hgnc.rows[symbol]
            nodes[("gene", symbol)] = {
                "node_id": f"gene:{symbol}", "node_type": "gene", "name": symbol,
                "hgnc_id": hr["hgnc_id"], "entrez_id": hr["entrez_id"],
                "ensembl_gene_id": hr["ensembl_gene_id"],
                "uniprot_ids": hr["uniprot_ids"], "source": "HGNC;STRING",
            }
        scores = {k: row.get(k, "") for k in
                  ("nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore")}
        edges.append({"source_id": f"gene:{key[0]}", "target_id": f"gene:{key[1]}",
                      "relation": "protein_interaction", "database": "STRING",
                      "score": row.get("score", ""), "pmid": "", "evidence": "",
                      "attributes": json.dumps(scores, separators=(",", ":"))})


def add_reactome(hgnc, seeds, nodes, edges, workers):
    jobs = []
    for symbol in sorted(seeds):
        for acc in split_multi(hgnc.rows[symbol]["uniprot_ids"]):
            jobs.append((symbol, acc))
    def fetch(job):
        symbol, acc = job
        url = f"https://reactome.org/ContentService/data/mapping/UniProt/{urllib.parse.quote(acc)}/pathways"
        return symbol, acc, request_json(url, "reactome")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, j) for j in jobs]
        for future in as_completed(futures):
            symbol, acc, pathways = future.result()
            for p in pathways:
                if p.get("speciesName") != "Homo sapiens":
                    continue
                stid = p.get("stId")
                if not stid:
                    continue
                pid = f"pathway:{stid}"
                nodes[("pathway", stid)] = {"node_id": pid, "node_type": "pathway",
                                            "name": p.get("displayName", stid),
                                            "source": "Reactome"}
                edges.append({"source_id": f"gene:{symbol}", "target_id": pid,
                              "relation": "participates_in", "database": "Reactome",
                              "score": "", "pmid": "", "evidence": "",
                              "attributes": json.dumps({"uniprot": acc}, separators=(",", ":"))})


def paged_chembl(url, object_key):
    result = []
    while url:
        obj = request_json(url, "chembl")
        result.extend(obj.get(object_key, []))
        nxt = obj.get("page_meta", {}).get("next")
        url = urllib.parse.urljoin("https://www.ebi.ac.uk", nxt) if nxt else None
    return result


def add_chembl(hgnc, seeds, nodes, edges):
    acc_to_symbol = {}
    for symbol in seeds:
        for acc in split_multi(hgnc.rows[symbol]["uniprot_ids"]):
            acc_to_symbol[acc] = symbol
    target_to_symbols = defaultdict(set)
    accessions = sorted(acc_to_symbol)
    for i in range(0, len(accessions), 30):
        vals = ",".join(accessions[i:i + 30])
        url = "https://www.ebi.ac.uk/chembl/api/data/target.json?" + urllib.parse.urlencode({
            "target_components__accession__in": vals, "limit": 1000,
        })
        for target in paged_chembl(url, "targets"):
            tid = target["target_chembl_id"]
            for comp in target.get("target_components", []):
                if comp.get("accession") in acc_to_symbol:
                    target_to_symbols[tid].add(acc_to_symbol[comp["accession"]])
    target_ids = sorted(target_to_symbols)
    for i in range(0, len(target_ids), 40):
        vals = ",".join(target_ids[i:i + 40])
        url = "https://www.ebi.ac.uk/chembl/api/data/mechanism.json?" + urllib.parse.urlencode({
            "target_chembl_id__in": vals, "limit": 1000,
        })
        for m in paged_chembl(url, "mechanisms"):
            mol = m.get("molecule_chembl_id")
            tid = m.get("target_chembl_id")
            if not mol or not tid:
                continue
            did = f"drug:{mol}"
            nodes[("drug", mol)] = {"node_id": did, "node_type": "drug",
                                    "name": mol, "source": "ChEMBL"}
            attrs = {k: m.get(k) for k in
                     ("action_type", "mechanism_of_action", "direct_interaction",
                      "binding_site_name", "variant_sequence") if m.get(k) is not None}
            for symbol in target_to_symbols[tid]:
                edges.append({"source_id": did, "target_id": f"gene:{symbol}",
                              "relation": clean(m.get("action_type")) or "targets",
                              "database": "ChEMBL", "score": "", "pmid": "",
                              "evidence": clean(m.get("mechanism_of_action")),
                              "attributes": json.dumps(attrs, ensure_ascii=False, separators=(",", ":"))})


def add_pubtator(hgnc, seeds, nodes, edges):
    entrez_to_symbol = {hgnc.rows[s]["entrez_id"]: s for s in seeds if hgnc.rows[s]["entrez_id"]}
    seen = set()
    with gzip.open(PUBTATOR, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            pmid, relation, left, right = parts
            entities = []
            hit = False
            for entity in (left, right):
                etype, _, eid = entity.partition("|")
                symbol = entrez_to_symbol.get(eid) if etype == "Gene" else None
                if symbol:
                    node_id, name, ntype = f"gene:{symbol}", symbol, "gene"
                    hit = True
                else:
                    node_id, name, ntype = f"{etype.lower()}:{eid}", eid, etype.lower()
                entities.append((node_id, name, ntype))
            if not hit:
                continue
            key = (pmid, relation, entities[0][0], entities[1][0])
            if key in seen:
                continue
            seen.add(key)
            for node_id, name, ntype in entities:
                if ntype != "gene":
                    nodes[(ntype, node_id)] = {"node_id": node_id, "node_type": ntype,
                                               "name": name, "source": "PubTator3"}
            edges.append({"source_id": entities[0][0], "target_id": entities[1][0],
                          "relation": relation, "database": "PubTator3", "score": "",
                          "pmid": pmid, "evidence": "", "attributes": ""})


def deduplicate_edges(edges):
    merged = {}
    for e in edges:
        key = (e["source_id"], e["target_id"], e["relation"], e["database"],
               e.get("pmid", ""), e.get("attributes", ""))
        merged[key] = e
    return list(merged.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-network", action="store_true")
    ap.add_argument("--string-limit", type=int, default=20)
    ap.add_argument("--string-score", type=int, default=700)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    for p in (RAW, CACHE, OUT):
        p.mkdir(parents=True, exist_ok=True)
    if not HGNC.exists():
        sys.exit(f"Missing HGNC file: {HGNC}")
    hgnc = HgncMap(HGNC)
    nodes, edges, seed_roles, provenance, unmapped = load_ferrdb(hgnc)
    seeds = set(seed_roles)
    if not args.skip_network:
        add_string(hgnc, seeds, nodes, edges, args.string_limit, args.string_score, args.workers)
        add_reactome(hgnc, seeds, nodes, edges, args.workers)
        add_chembl(hgnc, seeds, nodes, edges)
    add_pubtator(hgnc, seeds, nodes, edges)
    edges = deduplicate_edges(edges)
    node_rows = list(nodes.values())
    node_fields = ["node_id", "node_type", "name", "hgnc_id", "entrez_id",
                   "ensembl_gene_id", "uniprot_ids", "source"]
    edge_fields = ["source_id", "target_id", "relation", "database", "score",
                   "pmid", "evidence", "attributes"]
    write_csv(OUT / "nodes.csv", node_rows, node_fields)
    write_csv(OUT / "edges.csv", edges, edge_fields)
    mapping = []
    for symbol in sorted(seeds):
        r = hgnc.rows[symbol]
        mapping.append({"approved_symbol": symbol, "hgnc_id": r["hgnc_id"],
                        "entrez_id": r["entrez_id"], "ensembl_gene_id": r["ensembl_gene_id"],
                        "uniprot_ids": r["uniprot_ids"],
                        "ferrdb_roles": "|".join(sorted(seed_roles[symbol]))})
    write_csv(OUT / "id_mapping.csv", mapping,
              ["approved_symbol", "hgnc_id", "entrez_id", "ensembl_gene_id",
               "uniprot_ids", "ferrdb_roles"])
    write_csv(OUT / "unmapped.csv", unmapped,
              ["source", "file", "row", "identifier", "reason"])
    report = {
        "parameters": {"string_limit": args.string_limit,
                       "string_required_score": args.string_score,
                       "skip_network": args.skip_network},
        "hgnc_release_file": str(HGNC.relative_to(ROOT)),
        "seed_genes": len(seeds),
        "seed_roles": dict(Counter(role for roles in seed_roles.values() for role in roles)),
        "nodes": len(node_rows),
        "nodes_by_type": dict(Counter(r["node_type"] for r in node_rows)),
        "edges": len(edges),
        "edges_by_database": dict(Counter(r["database"] for r in edges)),
        "unmapped_ferrdb_rows": len(unmapped),
    }
    (OUT / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
