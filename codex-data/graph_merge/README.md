# Ferroptosis knowledge-graph merge

`merge_knowledge_graph.py` constructs a seed-centred graph using HGNC approved
symbols as the only gene key.

Defaults:

- FerrDb seeds: all HGNC-resolvable driver, suppressor and marker records.
- STRING: human (`9606`), functional network, score >= 700, 20 partners/seed.
- Reactome: human pathway mappings returned by Content Service for seed UniProt IDs.
- ChEMBL: curated drug-mechanism records for targets containing seed UniProt IDs.
- PubTator3: relations where at least one endpoint is a seed gene (NCBI Gene ID).

Run from the repository root:

```powershell
python codex-data\graph_merge\merge_knowledge_graph.py
```

HTTP responses are cached under `codex-data/graph_merge/cache`. Outputs are in
`codex-output/graph_merge`: `nodes.csv`, `edges.csv`, `id_mapping.csv`,
`unmapped.csv`, and `quality_report.json`.
