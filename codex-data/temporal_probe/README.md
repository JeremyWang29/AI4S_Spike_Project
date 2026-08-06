# FerrDb temporal probe

This probe tests whether models trained only on evidence published by the end
of 2022 rank post-2022 FerrDb gene/ferroptosis-role links highly.

It intentionally does **not** reinterpret FerrDb driver/suppressor annotations
as gene-regulates-gene edges. Current STRING, Reactome, and ChEMBL data are
excluded from the main experiment until historical releases or publication
year filters are available.

Run:

```powershell
python codex-data\temporal_probe\run_probe.py
```

The first run queries NCBI ESummary for PubMed years and caches the response.
Subsequent runs can use `--offline`. Outputs are written under
`codex-output/temporal_probe`.

Implemented baselines: seeded Random, Degree, PageRank, ComplEx, and RotatE.
GraphRAG is deliberately not faked: it needs a frozen pre-2023 retrieval corpus.
