from dataclasses import dataclass
from modules.core import fingerprint
from config.errors import BusinessError

@dataclass
class ModelPolicy:
    license_allows_external: bool
    project_allows_external: bool
    quality_baseline_verified: bool

def prepare_request(policy, materials, purpose):
    if not policy.license_allows_external or not policy.project_allows_external:
        raise BusinessError("MODEL_INPUT_NOT_ALLOWED", "许可或项目策略不允许外部模型处理", status=403, recovery="改用人工流程或获得明确许可")
    return {"purpose": purpose, "materials": [{"id": m["id"], "hash": m["hash"]} for m in materials],
            "cache_key": fingerprint({"purpose": purpose, "materials": [(m["id"], m["hash"]) for m in materials]})}

def route_status(policy): return "ENABLED" if policy.quality_baseline_verified else "UNCONFIGURED"
