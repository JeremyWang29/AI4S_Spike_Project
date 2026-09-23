"""Deterministic draft decomposition. No execution, inference, or approval."""
import json
import re
from pathlib import Path
from config.errors import BusinessError


def load_template():
    return json.loads((Path(__file__).parent / "templates/life_science_v1.json").read_text(encoding="utf-8"))


def decompose(snapshot, template):
    sources = [{"source": snapshot["title_source"], "text": snapshot["research_title"]},
               {"source": "scope.direction", "text": snapshot["scope"]["content"]["direction"]}]
    sources += [{"source": f"scope.core_keywords.{i}", "text": term} for i, term in enumerate(snapshot["scope"]["content"]["core_keywords"])]
    sources += [{"source": f"scope.answers.{key}", "text": value} for key, value in snapshot["scope"]["content"]["answers"].items() if key in ("object", "mechanism", "method", "outcome", "context")]
    sources += [{"source": f"concept.terms.{i}", "text": term} for i, term in enumerate(snapshot["concept"]["terms"])]
    blocks, unresolved, recognized = [], [], set()
    for entry in template["entries"]:
        variants = [(term, None) for term in entry["synonyms"]]
        variants += [(term, subclass) for subclass, terms in entry.get("subclasses", {}).items() for term in terms]
        spans = []
        for source in sources:
            for term, subclass in variants:
                pattern = re.escape(term)
                if term.isascii(): pattern = r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])"
                for match in re.finditer(pattern, source["text"], re.I):
                    spans.append({**source, "start": match.start(), "end": match.end(), "fragment": match.group(), "subclass": subclass})
                    recognized.add(term.casefold())
        if not spans: continue
        refs = [{"term": term, "origin": "vocabulary_suggestion", "source": template["vocabulary_source"],
                 "relation": "synonym", "subclass": subclass} for term, subclass in variants]
        refs += [{"term": span["fragment"], "origin": "accepted_term" if span["source"].startswith("concept.") else "user_term", "source": span["source"], "relation": "original", "subclass": span["subclass"]} for span in spans]
        blocks.append({"block_key": entry["key"], "facet_type": entry["facet"], "label": entry["label"], "source_spans": spans, "term_refs": refs, "relation_hypotheses": []})
    # Unknown supplied terms and acronyms remain explicit manual decisions, never silently discarded.
    candidates = [(s, s["text"]) for s in sources if s["source"].startswith(("scope.core_keywords", "concept.terms"))]
    candidates += [(s, m.group()) for s in sources for m in re.finditer(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,}(?![A-Za-z0-9])", s["text"])]
    unknown = {}
    for source, term in candidates:
        if term.casefold() in recognized: continue
        span = {**source, "fragment": term, "start": source["text"].find(term), "end": source["text"].find(term) + len(term)}
        ref = {"term": term, "origin": "accepted_term" if source["source"].startswith("concept.") else "user_term", "source": source["source"], "relation": "original"}
        if term.casefold() in unknown:
            block = unknown[term.casefold()]
            if span not in block["source_spans"]: block["source_spans"].append(span)
            if ref not in block["term_refs"]: block["term_refs"].append(ref)
            continue
        key = "U" + str(len(unknown) + 1)
        block = {"block_key": key, "facet_type": "unresolved", "label": term[:240], "source_spans": [span], "term_refs": [ref], "relation_hypotheses": []}
        blocks.append(block); unknown[term.casefold()] = block
        unresolved.append({"code": "TERM_MEANING_UNRESOLVED", "message": "请确认词义或缩写：" + term, "source_spans": block["source_spans"], "block_refs": [key]})
    for source in sources:
        for marker in template["relation_markers"] + ["LSD1-PRMT5"]:
            if marker in source["text"]:
                hypothesis = {"status": "unverified", "marker": marker, "source": source, "message": "关系待核查，不能视为已证实机制或复合体"}
                unresolved.append({"code": "RELATION_UNVERIFIED", **hypothesis})
                for block in blocks:
                    if any(s["source"] == source["source"] for s in block["source_spans"]): block["relation_hypotheses"].append(hypothesis)
    diseases = [b for b in blocks if b["facet_type"] == "disease"]
    if len(diseases) > 1:
        unresolved.append({"code": "RESEARCH_OBJECT_CONFLICT", "message": "题目、关键词或范围包含不同疾病对象，请确认边界", "source_spans": [s for b in diseases for s in b["source_spans"]]})
    title_entities = {b["block_key"] for b in blocks if b["facet_type"] in ("entity", "unresolved") and any(s["source"] == snapshot["title_source"] for s in b["source_spans"])}
    keyword_entities = {b["block_key"] for b in blocks if b["facet_type"] in ("entity", "unresolved") and any(s["source"].startswith("scope.core_keywords") for s in b["source_spans"])}
    if title_entities and keyword_entities and title_entities != keyword_entities:
        unresolved.append({"code": "TITLE_KEYWORD_CONFLICT", "message": "题目与关键词研究实体不一致，请人工确认", "source_spans": sources})
    unresolved.append({"code": "DECOMPOSITION_REVIEW_REQUIRED", "message": "规则拆分需人工核对未识别语义与任务边界", "source_spans": sources})
    if not blocks:
        unresolved.append({"code": "MANUAL_DECOMPOSITION_REQUIRED", "message": "题目尚无可确定概念，请人工拆分", "source_spans": sources})
    withheld = set()
    for decision in snapshot["concept"].get("decisions", []):
        if decision.get("decision") not in ("rejected", "replaced"): continue
        for block in blocks:
            if any(r["term"].casefold() == decision["term"].casefold() for r in block["term_refs"]):
                withheld.add(block["block_key"])
                unresolved.append({"code": "CONCEPT_DECISION_CONFLICT", "message": "原始输入仍含已拒绝或替换词：" + decision["term"] + "；相关块暂不分配任务，需人工核对", "block_refs": [block["block_key"]], "decision": decision})
    keys = {b["block_key"] for b in blocks} - withheld
    def ast(expr):
        return {"type": "block", "ref": expr, "within_block": "OR"} if isinstance(expr, str) else {"type": "bool", "op": expr[0], "children": [ast(e) for e in expr[1:]]}
    def refs(expr):
        return [expr] if isinstance(expr, str) else [r for child in expr[1:] for r in refs(child)]
    def task(key, purpose, expression, partition="target_disease_main", prerequisites=None):
        return {"task_key": key, "purpose": purpose, "required_blocks": refs(expression), "optional_variant_refs": [], "logical_ast": ast(expression), "filters": {}, "exclusions": [], "output_partition": partition, "prerequisites": prerequisites or [], "expansion_conditions": []}
    tasks = []
    if set("ABCDEFG") <= keys:
        tasks = [task(t["key"], t["purpose"], t["expression"]) for t in template["initial_tasks"]]
    else:
        for i, block in enumerate(blocks):
            if block["block_key"] in withheld: continue
            partition = "target_disease_main" if block["facet_type"] == "disease" else "cross_disease_supplement"
            tasks.append(task(f"T{i+1:02}", "概念定位，待确认任务组合", block["block_key"], partition))
    first = [t["task_key"] for t in tasks]
    later = []
    entities = [b["block_key"] for b in blocks if b["facet_type"] == "entity" and b["block_key"] not in withheld]
    for index, (left, right) in enumerate(zip(entities, entities[1:])):
        key = f"M{index+1:02}"
        pair = task(key, "跨疾病机制配对补查", ["AND", left, right], "cross_disease_supplement", first)
        pair["expansion_conditions"] = ["首批结果回传后确认机制补查需求"]
        tasks.append(pair); later.append(key)
    assigned = {ref for t in tasks for ref in t["required_blocks"]}
    for block in blocks:
        if block["block_key"] not in assigned:
            unresolved.append({"code": "BLOCK_TASK_PLACEMENT_PENDING", "message": "检索块尚未纳入任务，需确认用途：" + block["label"], "block_refs": [block["block_key"]]})
    if snapshot["scope"]["content"].get("answers"):
        unresolved.append({"code": "SCOPE_FILTER_MAPPING_PENDING", "message": "已确认的年份、语言和纳排边界保留在输入快照；尚未转成任务过滤条件，执行前必须核对。"})
    batches = [{"batch_key": "initial", "task_refs": first, "prerequisites": [], "activation_conditions": ["M1.2追问与显式确认后方可启用"], "status": "planned"}]
    if later: batches.append({"batch_key": "mechanism_followup", "task_refs": later, "prerequisites": first, "activation_conditions": ["首批结果回传且用户确认补查"], "status": "planned"})
    return {"blocks": blocks, "tasks": tasks, "batches": batches, "unresolved_items": unresolved}


def validate_structure(content, template):
    try:
        _validate_structure(content, template)
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        raise BusinessError("INVALID_SEARCH_PLAN", "检索方案字段或引用无效", recovery="重新生成草稿或联系维护者") from exc


def _validate_structure(content, template):
    def fail(): raise BusinessError("INVALID_SEARCH_PLAN", "检索方案结构无效", recovery="重新生成草稿或联系维护者")
    blocks, tasks, batches = content["blocks"], content["tasks"], content["batches"]
    if not all(isinstance(v, list) for v in (blocks, tasks, batches, content["unresolved_items"])): fail()
    fields = [(blocks, {"block_key", "facet_type", "label", "source_spans", "term_refs", "relation_hypotheses"}),
              (tasks, {"task_key", "purpose", "required_blocks", "optional_variant_refs", "logical_ast", "filters", "exclusions", "output_partition", "prerequisites", "expansion_conditions"}),
              (batches, {"batch_key", "task_refs", "prerequisites", "activation_conditions", "status"})]
    for records, expected in fields:
        for record in records:
            if not isinstance(record, dict) or set(record) != expected: fail()
    for block in blocks:
        if not isinstance(block["label"], str) or not 1 <= len(block["label"]) <= 240: fail()
    keys = {b["block_key"] for b in blocks}
    task_keys = {t["task_key"] for t in tasks}
    if len(keys) != len(blocks) or len(task_keys) != len(tasks) or len({b["batch_key"] for b in batches}) != len(batches): fail()
    for b in blocks:
        if b["facet_type"] not in template["facets"] or not b["source_spans"]: fail()
        if any(r["origin"] not in ("user_term", "accepted_term", "vocabulary_suggestion") or r["relation"] not in ("original", "synonym", "broader", "narrower", "related") for r in b["term_refs"]): fail()
    def walk(node, depth=0):
        if not isinstance(node, dict) or depth > 12: fail()
        if node.get("type") == "block":
            if set(node) != {"type", "ref", "within_block"} or node["ref"] not in keys or node["within_block"] != "OR": fail()
            return {node["ref"]}
        if set(node) != {"type", "op", "children"} or node.get("type") != "bool" or node.get("op") not in ("AND", "OR") or not isinstance(node.get("children"), list) or len(node["children"]) < 2: fail()
        return set().union(*(walk(c, depth+1) for c in node["children"]))
    dependencies = {}
    for task in tasks:
        if set(task["required_blocks"]) != walk(task["logical_ast"]) or task["optional_variant_refs"] or task["filters"] or task["exclusions"]: fail()
        if task["output_partition"] not in template["partitions"] or not set(task["prerequisites"]) <= task_keys: fail()
        dependencies[task["task_key"]] = task["prerequisites"]
    def visit(key, path):
        if key in path: fail()
        for dep in dependencies[key]: visit(dep, path | {key})
    for key in dependencies: visit(key, set())
    for batch in batches:
        if batch["status"] != "planned" or not set(batch["task_refs"]) <= task_keys or not set(batch["prerequisites"]) <= task_keys: fail()

    scheduled = set()
    for batch in batches:
        members = set(batch["task_refs"])
        if len(members) != len(batch["task_refs"]) or members & scheduled: fail()
        if not set(batch["prerequisites"]) <= scheduled: fail()
        remaining = set(members)
        done = set(scheduled)
        while remaining:
            ready = {key for key in remaining if set(dependencies[key]) <= done}
            if not ready: fail()
            remaining -= ready; done |= ready
        scheduled |= members
    if scheduled != task_keys: fail()
