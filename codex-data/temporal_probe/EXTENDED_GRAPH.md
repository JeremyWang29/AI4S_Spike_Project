# Historical graph extension

Run from the workspace root:

```powershell
python codex-data\temporal_probe\extend_historical_graph.py
```

The outputs are intentionally split by leakage status:

- `strict_historical_edges.csv`: FerrDb and PubTator edges supported by PMID
  publication years no later than 2022.
- `reactome_historical_proxy_edges.csv`: current Reactome mappings restricted
  to pathways released by 2022. Membership history is not proven.
- `string_v12_ablation_edges.csv`: current v12 topology, for ablation only.
- `gene_features.csv`: model-ready historical features plus clearly named
  STRING v12 ablation columns.

Do not concatenate all three edge files for the main temporal experiment.
