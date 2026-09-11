from dataclasses import dataclass

@dataclass(frozen=True)
class Evidence:
    source_record_id: str
    page: int | None
    excerpt_hash: str | None
    status: str
    human_verified: bool

    @property
    def locatable(self): return self.page is not None and self.excerpt_hash is not None

    def supports_claim(self): return self.status == "supported" and self.human_verified and self.locatable
