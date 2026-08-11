"""Domain-specific errors suitable for API mapping and audit logging."""


class PlatformError(Exception):
    """Base exception for expected platform failures."""


class SecurityViolationError(PlatformError):
    """Raised when input violates a gateway protection rule."""


class AccessDeniedError(PlatformError):
    """Raised when a caller attempts to access a protected resource."""


class SkillNotFoundError(PlatformError):
    """Raised when a router target has not been registered."""
