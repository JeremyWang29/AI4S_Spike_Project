import csv, io, re

def parse_csv(text): return list(csv.DictReader(io.StringIO(text)))
def parse_ris(text):
    records, current = [], None
    for line in text.splitlines():
        match = re.match(r"^([A-Z0-9]{2})  - (.*)$", line)
        if not match: continue
        tag, value = match.groups()
        if tag == "TY": current = {"type": value}; continue
        if current is None: continue
        if tag == "ER": records.append(current); current = None; continue
        key = {"TI": "title", "T1": "title", "AB": "abstract", "PY": "year", "DO": "source_id", "AN": "source_id"}.get(tag)
        if key: current[key] = value
    return records
def parse_bibtex(text):
    return [{k.lower(): v.strip().strip("{},\"") for k, v in re.findall(r"(?m)^\s*(\w+)\s*=\s*(.+?)[,]?\s*$", block)}
            for block in re.split(r"(?=@\w+\s*\{)", text) if block.strip()]
