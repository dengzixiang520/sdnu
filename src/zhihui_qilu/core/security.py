"""Security isolation gateway for authorization, input screening, and redaction."""

import re
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Callable

from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import SecurityEventType, SensitivityLevel, UserRole
from zhihui_qilu.core.errors import AccessDeniedError, SecurityViolationError
from zhihui_qilu.core.models import AgentRequest, SecurityEvent


class SecurityIsolationGateway:
    """Enforce least privilege before routing and redact content before disclosure."""

    _INJECTION_PATTERNS = tuple(
        re.compile(pattern, flags=re.IGNORECASE)
        for pattern in (
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"system\s+prompt",
            r"忽略.{0,12}(指令|规则)",
            r"越狱",
        )
    )
    _PII_PATTERNS = (
        (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE_REDACTED]"),
        (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL_REDACTED]"),
        (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[ID_REDACTED]"),
    )

    def __init__(self, settings: Settings, audit_sink: Callable[[SecurityEvent], None] | None = None) -> None:
        self._settings = settings
        self._audit_sink = audit_sink
        self._requests: dict[str, deque[datetime]] = defaultdict(deque)

    def inspect_request(self, request: AgentRequest, allowed_roles: set[UserRole] | None = None) -> AgentRequest:
        """Validate permissions, rate limit, and injection indicators before routing."""
        if allowed_roles and request.context.role not in allowed_roles:
            self._emit(SecurityEventType.ACCESS_DENIED, request, {"reason": "role_not_allowed"})
            raise AccessDeniedError("当前角色无权调用该能力")
        self._enforce_rate_limit(request)
        if any(pattern.search(request.text) for pattern in self._INJECTION_PATTERNS):
            self._emit(SecurityEventType.PROMPT_INJECTION, request, {"reason": "matched_policy_pattern"})
            raise SecurityViolationError("请求包含不安全的指令模式，已被安全网关拦截")
        return request.model_copy(update={"text": self.redact(request.text, request)})

    def redact(self, text: str, request: AgentRequest | None = None) -> str:
        """Mask common PII patterns without retaining the raw values in audit metadata."""
        redacted = text
        changed = False
        for pattern, replacement in self._PII_PATTERNS:
            redacted, count = pattern.subn(replacement, redacted)
            changed = changed or count > 0
        if changed and request is not None:
            self._emit(SecurityEventType.PII_REDACTED, request, {"reason": "pii_masked"})
        return redacted

    def may_disclose_raw_content(self, role: UserRole, sensitivity: SensitivityLevel) -> bool:
        """Raw sensitive chat content is never available to ordinary business agents."""
        return sensitivity in {SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL} or role == UserRole.SYSTEM

    def _enforce_rate_limit(self, request: AgentRequest) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        self._prune_idle_users(cutoff, now)
        bucket = self._requests[request.context.user_id]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self._settings.security_rate_limit_per_minute:
            self._emit(SecurityEventType.RATE_LIMIT, request, {"reason": "per_minute_limit"})
            raise SecurityViolationError("请求过于频繁，请稍后再试")
        bucket.append(now)

    def _prune_idle_users(self, cutoff: datetime, now: datetime) -> None:
        """Drop empty or long-idle buckets so the in-memory limiter stays bounded."""
        if len(self._requests) < 256:
            return
        idle_threshold = now - timedelta(minutes=5)
        for user_id in list(self._requests):
            bucket = self._requests[user_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket or bucket[-1] <= idle_threshold:
                del self._requests[user_id]

    def _emit(self, event_type: SecurityEventType, request: AgentRequest, details: dict[str, str]) -> None:
        if self._audit_sink:
            self._audit_sink(SecurityEvent(event_type=event_type, request_id=request.context.request_id, user_id=request.context.user_id, details=details))
