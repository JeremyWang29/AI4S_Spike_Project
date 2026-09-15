from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from datetime import timedelta
from config.errors import BusinessError
from .models import Event, Outbox, Task


def append_event(project_id, kind, payload):
    # Caller holds the owning project lock in the same transaction.
    sequence = (Event.objects.filter(stream_id=project_id).aggregate(value=Max("stream_seq"))["value"] or 0) + 1
    event = Event.objects.create(stream_id=project_id, stream_seq=sequence, event_type=kind, payload=payload)
    Outbox.objects.create(event=event)
    return event


def retry_task(project_id, task_id, current_version_id):
    task = Task.objects.select_for_update().filter(pk=task_id, project_id=project_id).first()
    if not task: raise BusinessError("TASK_NOT_FOUND", "任务不存在", status=404)
    if task.status != "failed" or task.target_version_id != current_version_id:
        raise BusinessError("TASK_RETRY_CONFLICT", "任务已过期或不可重试", status=409)
    if task.kind != "projection.rebuild":
        raise BusinessError("TASK_RECONCILIATION_REQUIRED", "外部任务须先人工对账，不能自动付费重试")
    task.status, task.lease_until = "accepted", None
    task.fencing_token += 1
    task.save(update_fields=("status", "fencing_token", "lease_until"))
    append_event(project_id, "TaskRetryRequested", {"task_id": str(task.id), "fencing_token": task.fencing_token})
    # M0 projection recovery is a bounded, local operation, executed synchronously.
    task.status, task.lease_until = "running", timezone.now() + timedelta(minutes=1)
    task.save(update_fields=("status", "lease_until"))
    complete_task(task.id, task.fencing_token)
    task.refresh_from_db()
    return {"id": str(task.id), "status": task.status, "fencing_token": task.fencing_token}


@transaction.atomic
def complete_task(task_id, fencing_token):
    from modules.projects.models import Project
    from modules.projects.services import rebuild_projection
    initial = Task.objects.get(pk=task_id)
    project = Project.objects.select_for_update().get(pk=initial.project_id)
    task = Task.objects.select_for_update().get(pk=task_id)
    current = project.constraints.order_by("-version").first()
    if task.status != "running" or task.fencing_token != fencing_token or not task.lease_until or task.lease_until <= timezone.now() or not current or task.target_version_id != current.id:
        raise BusinessError("STALE_TASK_RESULT", "任务结果已过期", status=409)
    if task.kind != "projection.rebuild":
        raise BusinessError("TASK_HANDLER_UNCONFIGURED", "任务处理器尚未配置")
    task.status = "succeeded"
    task.save(update_fields=("status",))
    append_event(project.id, "TaskCompleted", {"task_id": str(task.id)})
    rebuild_projection(project)
