"""Normalize unresolved FerrDb entities without collapsing RNAs into genes."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "codex-output" / "temporal_probe" / "extended_graph"
OUT = ROOT / "codex-output" / "temporal_probe" / "normalized_graph"
HGNC = ROOT / "codex-data" / "temporal_probe" / "cache" / "hgnc_complete_set_current.txt"
EDGE_FILES = [
    "strict_historical_edges.csv",
    "reactome_historical_proxy_edges.csv",
    "string_v12_ablation_edges.csv",
]
MANUAL_ALIASES = {
    "CAV-1": ("CAV1", "common protein alias"),
    "CB2R": ("CNR2", "cannabinoid receptor 2 alias"),
    "FER1HCH": ("FTH1", "legacy ferritin heavy-chain symbol"),
    "G6PDX": ("G6PD", "legacy glucose-6-phosphate dehydrogenase symbol"),
    "IMP2": ("IGF2BP2", "insulin-like growth factor 2 mRNA-binding protein 2 alias"),
    "PKM2": ("PKM", "protein isoform mapped to encoding gene"),
    "SHP-1": ("PTPN6", "protein alias mapped to encoding gene"),
    "STING": ("TMEM173", "protein alias mapped to encoding gene"),
}
NONHUMAN_ENTITIES = {
    "GM47283": ("mouse lncRNA", "Mice"),
    "LNCAABR07025387.1": ("rat lncRNA", "Rat"),
    "LNCRNA AABR07017145.1": ("rat lncRNA", "Rat"),
    "MMU_CIRCRNA_0000309": ("mouse circRNA", "Mice"),
    "MIR-706": ("mouse miRNA", "Mice"),
    "MIRN672": ("rat miRNA", "Rat"),
    "OSFER2": ("rice ferritin gene", "Oryza sativa"),
    "LIP": ("zebrafish experimental entity; HGNC alias match is spurious", "Zebrafish"),
    "TRF3-ILEAAT": ("mouse tRNA-derived fragment", "Mice"),
}
SPECIAL_RNA = {
    "UC.339": ("lncrna:UC.339", "lncRNA", "human ultraconserved lncRNA"),
}
GENERIC_OR_AMBIGUOUS = {
    "PI3K": "protein family/pathway label; do not force to PIK3CA",
}


def split_multi(value: str):
    return [x.strip() for x in (value or "").split("|") if x.strip()]


def load_hgnc():
    rows, exact, previous, aliases = {}, {}, defaultdict(set), defaultdict(set)
    with HGNC.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("status") != "Approved":
                continue
            symbol = row["symbol"]
            rows[symbol] = row
            exact[symbol.upper()] = symbol
            for value in split_multi(row.get("prev_symbol", "")):
                previous[value.upper()].add(symbol)
            for value in split_multi(row.get("alias_symbol", "")):
                aliases[value.upper()].add(symbol)
    return rows, exact, previous, aliases


def hgnc_type(row):
    group = row.get("locus_group", "")
    locus = row.get("locus_type", "")
    if group == "protein-coding gene":
        return "Gene"
    if "RNA" in group or "RNA" in locus or "non-coding" in group:
        return "RNA"
    return "Gene_or_other_locus"


def circ_id(symbol):
    cleaned = re.sub(r"^(HSA[_-])?", "", symbol.upper())
    cleaned = cleaned.replace("CIRCRNA", "CIRC").replace("CIRC-RNA", "CIRC")
    cleaned = re.sub(r"[^A-Z0-9]+", "_", cleaned).strip("_")
    return f"circrna:{cleaned}"


def mirna_id(symbol):
    cleaned = symbol.upper().replace("MIRN", "MIR")
    cleaned = re.sub(r"[^A-Z0-9]+", "-", cleaned).strip("-")
    return f"mirna:{cleaned}"


def normalize_one(symbol, rows, exact, previous, aliases):
    key = symbol.upper().strip()
    if key in NONHUMAN_ENTITIES:
        note, organism = NONHUMAN_ENTITIES[key]
        return {
            "original_symbol": symbol, "canonical_id": "", "canonical_symbol": symbol,
            "entity_type": "NonHumanRNA_or_gene", "normalization_status": "exclude_nonhuman",
            "mapping_method": "FerrDb_organism_audit", "hgnc_id": "", "entrez_id": "",
            "locus_group": "", "review_note": f"{note}; organism={organism}",
        }
    if key in SPECIAL_RNA:
        canonical_id, entity_type, note = SPECIAL_RNA[key]
        return {
            "original_symbol": symbol, "canonical_id": canonical_id,
            "canonical_symbol": symbol, "entity_type": entity_type,
            "normalization_status": "accepted", "mapping_method": "FerrDb_entity_type_audit",
            "hgnc_id": "", "entrez_id": "", "locus_group": "non-coding RNA",
            "review_note": note,
        }
    if key in GENERIC_OR_AMBIGUOUS:
        return {
            "original_symbol": symbol, "canonical_id": "", "canonical_symbol": symbol,
            "entity_type": "ProteinFamily_or_Pathway", "normalization_status": "manual_review",
            "mapping_method": "generic_biological_label", "hgnc_id": "", "entrez_id": "",
            "locus_group": "", "review_note": GENERIC_OR_AMBIGUOUS[key],
        }
    candidates, method = set(), ""
    if key in exact:
        candidates, method = {exact[key]}, "HGNC_approved_exact"
    elif len(previous.get(key, set())) == 1:
        candidates, method = previous[key], "HGNC_previous_symbol"
    elif len(aliases.get(key, set())) == 1:
        candidates, method = aliases[key], "HGNC_alias_symbol"
    elif symbol in MANUAL_ALIASES:
        target, note = MANUAL_ALIASES[symbol]
        if target in rows:
            candidates, method = {target}, "curated_alias:" + note
    if len(candidates) == 1:
        canonical = next(iter(candidates))
        row = rows[canonical]
        entity_type = hgnc_type(row)
        return {
            "original_symbol": symbol, "canonical_id": f"{entity_type.lower()}:{canonical}",
            "canonical_symbol": canonical, "entity_type": entity_type,
            "normalization_status": "accepted", "mapping_method": method,
            "hgnc_id": row.get("hgnc_id", ""), "entrez_id": row.get("entrez_id", ""),
            "locus_group": row.get("locus_group", ""), "review_note": "",
        }
    if len(previous.get(key, set()) | aliases.get(key, set())) > 1:
        values = sorted(previous.get(key, set()) | aliases.get(key, set()))
        return {
            "original_symbol": symbol, "canonical_id": "", "canonical_symbol": "",
            "entity_type": "Ambiguous", "normalization_status": "manual_review",
            "mapping_method": "ambiguous_HGNC_alias", "hgnc_id": "", "entrez_id": "",
            "locus_group": "", "review_note": "|".join(values),
        }
    if "CIRC" in key:
        nonhuman = key.startswith("MMU_")
        return {
            "original_symbol": symbol, "canonical_id": circ_id(symbol),
            "canonical_symbol": symbol, "entity_type": "CircRNA",
            "normalization_status": "exclude_nonhuman" if nonhuman else "accepted",
            "mapping_method": "RNA_name_pattern", "hgnc_id": "", "entrez_id": "",
            "locus_group": "circular RNA",
            "review_note": "mouse prefix" if nonhuman else "host gene is not substituted for circRNA",
        }
    if re.match(r"^(MIR|MIRN|LET-)", key):
        return {
            "original_symbol": symbol, "canonical_id": mirna_id(symbol),
            "canonical_symbol": symbol, "entity_type": "miRNA",
            "normalization_status": "accepted", "mapping_method": "RNA_name_pattern",
            "hgnc_id": "", "entrez_id": "", "locus_group": "microRNA",
            "review_note": "mature miRNA name retained; species requires source-level verification",
        }
    if re.search(r"AABR|^GM\d+", key):
        return {
            "original_symbol": symbol, "canonical_id": "", "canonical_symbol": symbol,
            "entity_type": "NonHumanRNA_or_gene", "normalization_status": "exclude_nonhuman",
            "mapping_method": "species_specific_name_pattern", "hgnc_id": "", "entrez_id": "",
            "locus_group": "", "review_note": "rat/mouse-style identifier",
        }
    return {
        "original_symbol": symbol, "canonical_id": "", "canonical_symbol": symbol,
        "entity_type": "Unresolved", "normalization_status": "manual_review",
        "mapping_method": "no_unique_mapping", "hgnc_id": "", "entrez_id": "",
        "locus_group": "", "review_note": "do not coerce to Gene",
    }


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows, exact, previous, aliases = load_hgnc()
    nodes = list(csv.DictReader((SOURCE / "nodes.csv").open(encoding="utf-8-sig", newline="")))
    unresolved = [n for n in nodes if n["node_type"] == "unresolved_or_non_gene"]
    decisions = [normalize_one(n["name"], rows, exact, previous, aliases) for n in unresolved]
    by_original = {d["original_symbol"]: d for d in decisions}
    id_map = {}
    normalized_nodes = {}
    for node in nodes:
        if node["node_type"] != "unresolved_or_non_gene":
            normalized_nodes[node["node_id"]] = node
            continue
        decision = by_original[node["name"]]
        if decision["normalization_status"] != "accepted":
            continue
        new_id = decision["canonical_id"]
        id_map[node["node_id"]] = new_id
        normalized_nodes[new_id] = {
            "node_id": new_id, "node_type": decision["entity_type"],
            "name": decision["canonical_symbol"], "hgnc_id": decision["hgnc_id"],
            "entrez_id": decision["entrez_id"], "locus_group": decision["locus_group"],
            "candidate_source": node["candidate_source"] + ";" + decision["mapping_method"],
        }
    quarantined = []
    edge_counts = {}
    for filename in EDGE_FILES:
        accepted_edges = []
        with (SOURCE / filename).open(encoding="utf-8-sig", newline="") as handle:
            for edge in csv.DictReader(handle):
                reject = []
                for side in ("source_id", "target_id"):
                    if edge[side] in id_map:
                        edge[side] = id_map[edge[side]]
                    elif edge[side].startswith("gene:") and edge[side] not in normalized_nodes:
                        reject.append(edge[side][5:])
                if reject:
                    quarantined.append({
                        "edge_file": filename, "source_id": edge["source_id"],
                        "target_id": edge["target_id"], "relation": edge["relation"],
                        "reason": "unresolved_or_excluded_endpoint:" + "|".join(reject),
                    })
                else:
                    accepted_edges.append(edge)
        write_csv(OUT / filename, accepted_edges)
        edge_counts[filename] = len(accepted_edges)
    feature_path = SOURCE / "gene_features.csv"
    normalized_features = {}
    if feature_path.exists():
        with feature_path.open(encoding="utf-8-sig", newline="") as handle:
            for feature in csv.DictReader(handle):
                original = feature["gene"]
                decision = by_original.get(original)
                if decision and decision["normalization_status"] != "accepted":
                    continue
                canonical = decision["canonical_symbol"] if decision else original
                entity_type = decision["entity_type"] if decision else feature["node_type"]
                target = normalized_features.setdefault(
                    canonical, {"gene": canonical, "node_type": entity_type,
                                "source_symbols": set()}
                )
                target["source_symbols"].add(original)
                for key, value in feature.items():
                    if key in {"gene", "node_type"} or value in {"", None}:
                        continue
                    try:
                        number = float(value)
                    except ValueError:
                        continue
                    if key == "pubtator_first_year" and number > 0:
                        old = target.get(key, 0)
                        target[key] = number if not old else min(old, number)
                    elif key == "pubtator_last_year":
                        target[key] = max(target.get(key, 0), number)
                    elif key.endswith("_pre2023"):
                        target[key] = max(target.get(key, 0), number)
                    else:
                        target[key] = target.get(key, 0) + number
        feature_fields = list(csv.DictReader(feature_path.open(
            encoding="utf-8-sig", newline=""
        )).fieldnames or [])
        feature_fields.insert(2, "source_symbols")
        feature_rows = []
        for feature in normalized_features.values():
            feature["source_symbols"] = "|".join(sorted(feature["source_symbols"]))
            feature_rows.append(feature)
        write_csv(OUT / "gene_features.csv", feature_rows, feature_fields)
    write_csv(OUT / "nodes.csv", list(normalized_nodes.values()))
    write_csv(OUT / "normalization_decisions.csv", decisions)
    write_csv(OUT / "quarantined_edges.csv", quarantined)
    status_counts = defaultdict(int)
    type_counts = defaultdict(int)
    method_counts = defaultdict(int)
    for item in decisions:
        status_counts[item["normalization_status"]] += 1
        type_counts[item["entity_type"]] += 1
        method_counts[item["mapping_method"]] += 1
    report = {
        "input_unresolved_or_non_gene": len(unresolved),
        "normalization_status": dict(sorted(status_counts.items())),
        "normalized_entity_types": dict(sorted(type_counts.items())),
        "mapping_methods": dict(sorted(method_counts.items())),
        "normalized_nodes": len(normalized_nodes),
        "accepted_edges": edge_counts,
        "quarantined_edges": len(quarantined),
        "normalized_feature_entities": len(normalized_features),
        "policy": [
            "Only unique HGNC approved/previous/alias mappings are automatically accepted.",
            "CircRNA and mature miRNA remain RNA nodes and are never collapsed into host genes.",
            "Ambiguous, non-human and unresolved endpoints are quarantined.",
            "The official current HGNC file is used for nomenclature only, not as a historical graph feature.",
        ],
    }
    (OUT / "normalization_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
