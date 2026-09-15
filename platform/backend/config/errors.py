import uuid
import logging
import traceback


def unexpected_error(exc):
    trace = str(uuid.uuid4())
    frames = [(frame.filename, frame.lineno, frame.name) for frame in traceback.extract_tb(exc.__traceback__)]
    logging.getLogger("ai4s.errors").error("Unhandled error trace=%s type=%s frames=%s", trace, type(exc).__name__, frames)
    return body(BusinessError("INTERNAL_ERROR", "服务暂时无法完成请求", status=500,
        recovery="保留幂等键并重试；持续失败请联系管理员"), trace)


class BusinessError(Exception):
    def __init__(self, code, message, *, status=422, owner="researcher", recovery="补全依赖后重试", details=None):
        self.code, self.message, self.status = code, message, status
        self.owner, self.recovery, self.details = owner, recovery, details or {}
        super().__init__(message)


def body(exc, trace_id):
    return {"error": {"code": exc.code, "message": exc.message, "owner": exc.owner,
                      "recovery": exc.recovery, "details": exc.details, "trace_id": trace_id}}


def csrf_failure(request, reason=""):
    from django.http import JsonResponse
    exc = BusinessError("CSRF_FAILED", "CSRF 校验失败", status=403, owner="requester",
                        recovery="刷新页面获取新令牌后重试")
    return JsonResponse(body(exc, request.headers.get("X-Trace-Id", str(uuid.uuid4()))), status=403)


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_handler
    trace = context["request"].headers.get("X-Trace-Id", str(uuid.uuid4()))
    if isinstance(exc, BusinessError):
        return __import__("rest_framework.response", fromlist=["Response"]).Response(body(exc, trace), status=exc.status)
    response = drf_handler(exc, context)
    if response is not None:
        code = "NOT_AUTHENTICATED" if response.status_code == 403 and not context["request"].user.is_authenticated else "REQUEST_REJECTED"
        response.data = body(BusinessError(code, "请求被拒绝", status=response.status_code), trace)
    else:
        from rest_framework.response import Response
        response = Response(unexpected_error(exc), status=500)
    return response


class BusinessErrorMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        from django.conf import settings
        from django.http import JsonResponse
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1
        if length > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            return JsonResponse(body(BusinessError("REQUEST_TOO_LARGE", "请求体超过大小限制", status=413), str(uuid.uuid4())), status=413)
        return self.get_response(request)

    def process_exception(self, request, exc):
        from django.http import JsonResponse
        if isinstance(exc, BusinessError):
            return JsonResponse(body(exc, str(uuid.uuid4())), status=exc.status)
        return JsonResponse(unexpected_error(exc), status=500)
