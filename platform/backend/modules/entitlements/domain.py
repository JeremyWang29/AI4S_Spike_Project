from dataclasses import dataclass

REWARD_SECONDS = 7_776_000

@dataclass
class Grant:
    eligibility_id: str
    asset_id: str
    remaining_seconds: int = REWARD_SECONDS
    active: bool = False

class Ledger:
    def __init__(self): self.grants = []; self.eligibility_ids = set(); self.entries = set()
    def reward(self, eligibility_id, asset_id):
        if eligibility_id in self.eligibility_ids: return next(g for g in self.grants if g.eligibility_id == eligibility_id)
        grant = Grant(eligibility_id, asset_id); self.grants.append(grant); self.eligibility_ids.add(eligibility_id); self._activate_head(asset_id); return grant
    def _activate_head(self, asset_id):
        pending = [g for g in self.grants if g.asset_id == asset_id and g.remaining_seconds > 0]
        for i, g in enumerate(pending): g.active = i == 0
    def settle(self, asset_id, seconds, available=True, reason="tick"):
        heads = [g for g in self.grants if g.asset_id == asset_id and g.active]
        if not available or not heads: return 0
        g = heads[0]; key = (g.eligibility_id, reason)
        if key in self.entries: return 0
        used = min(seconds, g.remaining_seconds); g.remaining_seconds -= used; self.entries.add(key)
        if g.remaining_seconds == 0: g.active = False; self._activate_head(asset_id)
        return used
