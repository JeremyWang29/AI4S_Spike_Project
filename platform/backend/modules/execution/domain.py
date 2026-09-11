from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from modules.core import fingerprint
from config.errors import BusinessError


@dataclass
class ReliableTask:
    target_version_id: str
    input_data: dict
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: str = "accepted"
    fencing_token: int = 1
    output: object = None

    def retry_lease(self):
        self.fencing_token += 1
        return self.fencing_token

    def complete(self, token, output, current_target_version, cancelled=False):
        if token != self.fencing_token:
            raise BusinessError("STALE_WORKER", "过期 Worker 不能写入当前状态", status=409, recovery="丢弃该输出")
        self.output = output
        self.status = "historical" if cancelled or current_target_version != self.target_version_id else "completed"


@dataclass
class Budget:
    limit: Decimal
    currency: str
    reserved: Decimal = Decimal("0")
    spent: Decimal = Decimal("0")
    unknown: Decimal = Decimal("0")

    def reserve(self, amount):
        amount = Decimal(amount)
        if self.reserved + self.spent + self.unknown + amount > self.limit:
            raise BusinessError("BUDGET_EXCEEDED", "预算不足", status=422, owner="project_owner", recovery="调整预算或减少输入")
        self.reserved += amount
    def mark_unknown(self, amount):
        amount = Decimal(amount); self.reserved -= amount; self.unknown += amount
