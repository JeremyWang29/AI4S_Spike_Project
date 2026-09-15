from django.db.models import Q
from config.errors import BusinessError
from .models import ProjectMembership


def visible_projects(user):
    from modules.projects.models import Project
    return Project.objects.filter(Q(owner=user) | Q(memberships__user=user)).distinct()


def project_role(user, project):
    if project.owner_id == user.pk:
        return "owner"
    return ProjectMembership.objects.filter(project=project, user=user).values_list("role", flat=True).first()


def require_project(user, project_id, operation="read", lock=False):
    from modules.projects.models import Project
    query = Project.objects.select_for_update() if lock else Project.objects
    project = query.filter(pk=project_id).first()
    role = project_role(user, project) if project else None
    allowed = {"read": {"owner", "researcher", "reviewer"}, "write": {"owner", "researcher"}, "members": {"owner"}}
    if role not in allowed.get(operation, set()):
        raise BusinessError("PROJECT_NOT_FOUND", "项目不存在或无权访问", status=404)
    return project


def require_material(user, project_id, facts):
    require_project(user, project_id)
    if facts is None or not facts.allows("read"):
        raise BusinessError("PROJECT_NOT_FOUND", "项目不存在或无权访问", status=404)


def set_member(actor, project, user_id, role):
    from django.contrib.auth import get_user_model
    require_project(actor, project.id, "members")
    if type(user_id) is not int or user_id == project.owner_id or role not in ("researcher", "reviewer", "remove"):
        raise BusinessError("MEMBERSHIP_INVALID", "成员或角色无效")
    if role == "remove":
        ProjectMembership.objects.filter(project=project, user_id=user_id).delete()
        return {"user_id": user_id, "role": role}
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if not user:
        raise BusinessError("MEMBERSHIP_INVALID", "成员或角色无效")
    ProjectMembership.objects.update_or_create(project=project, user=user, defaults={"role": role, "assigned_actions": []})
    return {"user_id": user_id, "role": role}
