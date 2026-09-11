from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AccessFacts:
    authenticated: bool
    project_role: str | None
    license_valid: bool
    entitlement_valid: bool
    purpose_allowed: bool
    content_available: bool

    def allows(self, operation: str) -> bool:
        roles = {"read": {"viewer", "researcher", "owner"}, "write": {"researcher", "owner"}, "approve": {"owner"}}
        return (self.authenticated and self.project_role in roles[operation] and self.license_valid
                and self.entitlement_valid and self.purpose_allowed and self.content_available)

    def require(self, operation: str):
        from config.errors import BusinessError
        if not self.allows(operation):
            raise BusinessError("ACCESS_INTERSECTION_DENIED", "权限、许可、权益、用途或内容状态不允许该操作", status=403,
                                owner="project_owner", recovery="核验当前许可与项目成员权限")
