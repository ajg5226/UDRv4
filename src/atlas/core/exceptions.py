"""Custom exception hierarchy for ATLAS."""

from typing import Any, Optional


class AtlasError(Exception):
    """Base exception for all ATLAS errors."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        parts = [self.message]
        if self.details:
            parts.append(f"Details: {self.details}")
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        return " | ".join(parts)


class ConfigurationError(AtlasError):
    """Raised when configuration is invalid or missing."""

    pass


class ProviderError(AtlasError):
    """Raised when a data provider operation fails."""

    def __init__(
        self,
        message: str,
        *,
        provider_name: str,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message, details=details, cause=cause)
        self.provider_name = provider_name
        self.retryable = retryable


class DatabaseError(AtlasError):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str,
        *,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, details=details, cause=cause)
        self.operation = operation
        self.table = table


class ValidationError(AtlasError):
    """Raised when data validation fails."""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        expected: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=details)
        self.field = field
        self.value = value
        self.expected = expected


class PipelineError(AtlasError):
    """Raised when pipeline orchestration fails."""

    def __init__(
        self,
        message: str,
        *,
        run_id: Optional[int] = None,
        stage: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        partial_success: bool = False,
    ) -> None:
        super().__init__(message, details=details, cause=cause)
        self.run_id = run_id
        self.stage = stage
        self.partial_success = partial_success


class AuthenticationError(AtlasError):
    """Raised when authentication fails."""

    pass


class RateLimitError(ProviderError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        *,
        provider_name: str,
        retry_after: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            provider_name=provider_name,
            details=details,
            retryable=True,
        )
        self.retry_after = retry_after


class DataQualityError(ValidationError):
    """Raised when data quality checks fail."""

    def __init__(
        self,
        message: str,
        *,
        check_name: str,
        threshold: Optional[float] = None,
        actual: Optional[float] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=details)
        self.check_name = check_name
        self.threshold = threshold
        self.actual = actual
