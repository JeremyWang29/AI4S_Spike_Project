from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from config.errors import BusinessError
from .services import audit, consume_login_attempt, issue_token, login_bucket, redeem_token, revoke_sessions


@ensure_csrf_cookie
@csrf_protect
def session_login(request):
    if request.method == "GET":
        return JsonResponse({"authenticated": request.user.is_authenticated,
            "username": request.user.get_username() if request.user.is_authenticated else None,
            "user_id": request.user.pk if request.user.is_authenticated else None,
            "administrator": request.user.is_staff if request.user.is_authenticated else False})
    if request.method != "POST":
        raise BusinessError("METHOD_NOT_ALLOWED", "只允许 GET/POST", status=405)
    username, password = request.POST.get("username", ""), request.POST.get("password", "")
    if len(username) > 150 or len(password) > 1024:
        raise BusinessError("LOGIN_FAILED", "账号或密码无效", status=403)
    consume_login_attempt(login_bucket(username, request.META.get("REMOTE_ADDR", "")))
    consume_login_attempt(login_bucket(username, "account"))
    from django.db import transaction
    from django.contrib.auth import get_user_model
    with transaction.atomic():
        # Session creation and revocation serialize on the same account row.
        get_user_model().objects.select_for_update().filter(username=username).first()
        user = authenticate(request, username=username, password=password)
        if user is None:
            denied = True
        else:
            denied = False
            login(request, user)
            request.session.save()
            audit(user, "session.login", user.pk)
    if denied:
        audit(None, "session.denied", "login")
        raise BusinessError("LOGIN_FAILED", "账号或密码无效", status=403)
    from .models import LoginAttempt
    LoginAttempt.objects.filter(key__in=[login_bucket(username, request.META.get("REMOTE_ADDR", "")), login_bucket(username, "account")]).update(failures=0)
    return JsonResponse({"authenticated": True, "username": user.username, "user_id": user.pk, "administrator": user.is_staff})


@csrf_protect
def session_logout(request):
    if request.method != "POST":
        raise BusinessError("METHOD_NOT_ALLOWED", "只允许 POST", status=405)
    audit(request.user, "session.logout", request.user.pk or "anonymous")
    logout(request)
    return JsonResponse({"authenticated": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue(request):
    if not isinstance(request.data, dict): raise BusinessError("INVALID_INPUT", "请求格式无效")
    return JsonResponse(issue_token(request.user, request.data.get("username"), request.data.get("kind")))


@csrf_protect
def redeem(request):
    import json
    if request.method != "POST":
        raise BusinessError("METHOD_NOT_ALLOWED", "只允许 POST", status=405)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict): raise ValueError()
    except (ValueError, UnicodeDecodeError):
        raise BusinessError("INVALID_INPUT", "请求格式无效")
    return JsonResponse(redeem_token(data.get("token"), data.get("password")))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke(request):
    from django.contrib.auth import get_user_model
    from django.db import transaction
    if not isinstance(request.data, dict): raise BusinessError("INVALID_INPUT", "请求格式无效")
    target = request.data.get("user_id", request.user.pk)
    if type(target) is not int or (target != request.user.pk and not request.user.is_staff):
        raise BusinessError("ACCOUNT_FORBIDDEN", "无权撤销该账号会话", status=403)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(pk=target).first()
        if not user:
            raise BusinessError("ACCOUNT_FORBIDDEN", "账号不可用", status=404)
        revoke_sessions(user)
        audit(request.user, "session.revoke_all", user.pk)
    return JsonResponse({"revoked": True})
