"""Stable enumerations shared by agents, memory, and safety controls."""

from enum import StrEnum


class UserRole(StrEnum):
    """Roles used for least-privilege access checks."""

    STUDENT = "student"
    COUNSELOR = "counselor"
    ADMINISTRATOR = "administrator"
    SYSTEM = "system"


class SensitivityLevel(StrEnum):
    """Data classification; higher levels require stricter handling."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class AccessScope(StrEnum):
    """Audience allowed to retrieve a memory record."""

    OWNER = "owner"
    AUTHORIZED_STAFF = "authorized_staff"
    SYSTEM_ONLY = "system_only"


class MemoryTier(StrEnum):
    """The three retention tiers defined by the white paper."""

    EPHEMERAL = "ephemeral"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class RouteLevel(StrEnum):
    """Router execution level: immediate skill route or deep planning."""

    L1 = "l1"
    L2 = "l2"


class SecurityEventType(StrEnum):
    """Auditable security event categories."""

    PROMPT_INJECTION = "prompt_injection"
    RATE_LIMIT = "rate_limit"
    PII_REDACTED = "pii_redacted"
    ACCESS_DENIED = "access_denied"
    HIGH_RISK_ESCALATION = "high_risk_escalation"
