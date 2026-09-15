from datetime import timedelta
from hashlib import sha256
import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from config.errors import BusinessError
from .models import AuditRecord, CredentialToken, LoginAttempt


def audit(actor, action, object_id):
    AuditRecord.objects.create(actor=actor if actor and actor.is_authenticated else None,
                               action=action, object_id=str(object_id))


def revoke_sessions(user):
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()


@transaction.atomic
def issue_token(actor, username, kind):
    if not actor.is_staff:
        raise BusinessError("ACCOUNT_FORBIDDEN", "仅管理员可管理账号", status=403)
    if kind not in ("invite", "reset") or not isinstance(username, str) or not 1 <= len(username.strip()) <= 150:
        raise BusinessError("ACCOUNT_INPUT_INVALID", "账号或令牌用途无效")
    # Serializes issuance, including a previously nonexistent invited account.
    administrator = get_user_model().objects.filter(is_staff=True).order_by("pk").first()
    get_user_model().objects.select_for_update().get(pk=administrator.pk)
    user = get_user_model().objects.select_for_update().filter(username=username.strip()).first()
    if kind == "invite":
        if user and user.is_active:
            raise BusinessError("ACCOUNT_INPUT_INVALID", "该账号已存在，请使用密码重置")
        if not user: user = get_user_model().objects.create_user(username.strip(), is_active=False)
    if not user:
        raise BusinessError("ACCOUNT_INPUT_INVALID", "账号不可用")
    CredentialToken.objects.filter(user=user, kind=kind, consumed_at=None).update(consumed_at=timezone.now())
    raw = secrets.token_urlsafe(32)
    token = CredentialToken.objects.create(user=user, kind=kind, digest=sha256(raw.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=24 if kind == "invite" else 1))
    audit(actor, "credential.issued." + kind, user.pk)
    return {"token": raw, "expires_at": token.expires_at.isoformat(), "username": user.username, "user_id": user.pk}


@transaction.atomic
def redeem_token(raw, password):
    if not isinstance(raw, str) or len(raw) > 256 or not isinstance(password, str) or len(password) > 1024:
        raise BusinessError("CREDENTIAL_DENIED", "凭据无效或已过期", status=403)
    token = CredentialToken.objects.filter(digest=sha256(raw.encode()).hexdigest()).first()
    if not token or token.consumed_at or token.expires_at <= timezone.now():
        raise BusinessError("CREDENTIAL_DENIED", "凭据无效或已过期", status=403)
    user = get_user_model().objects.select_for_update().get(pk=token.user_id)
    token = CredentialToken.objects.select_for_update().get(pk=token.pk)
    if token.consumed_at or token.expires_at <= timezone.now():
        raise BusinessError("CREDENTIAL_DENIED", "凭据无效或已过期", status=403)
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise BusinessError("PASSWORD_INVALID", "密码不符合要求", details={"messages": exc.messages})
    token.consumed_at = timezone.now()
    token.save(update_fields=("consumed_at",))
    user.set_password(password)
    if token.kind == "invite":
        user.is_active = True
    user.save(update_fields=("password", "is_active"))
    revoke_sessions(user)
    audit(user, "credential.redeemed." + token.kind, user.pk)
    return {"redeemed": True}


def login_bucket(username, remote_addr):
    return sha256((str(remote_addr) + ":" + str(username).casefold()[:150]).encode()).hexdigest()


@transaction.atomic
def consume_login_attempt(key):
    bucket, _ = LoginAttempt.objects.get_or_create(key=key, defaults={"window_start": timezone.now()})
    bucket = LoginAttempt.objects.select_for_update().get(pk=key)
    if bucket.window_start <= timezone.now() - timedelta(minutes=15):
        bucket.window_start, bucket.failures = timezone.now(), 0
    if bucket.failures >= 5:
        raise BusinessError("LOGIN_THROTTLED", "尝试次数过多，请15分钟后重试", status=429)
    bucket.failures += 1
    bucket.save()
