from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .services import create_plan, read_plan, list_plans


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def collection(request, project_id):
    if request.method == "GET": return JsonResponse(list_plans(request.user, project_id))
    data, replay = create_plan(request.user, project_id, request.data, request.headers.get("Idempotency-Key", "").strip())
    response = JsonResponse(data, status=201)
    if replay: response["Idempotent-Replay"] = "true"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def detail(request, plan_id):
    return JsonResponse(read_plan(request.user, plan_id))
