"""Domain exceptions. Adapters translate them into protocol answers (e.g. HTTP 400/404/409)."""


class DomainError(Exception):
    """Base class for every business rule violation."""


class DomainValidationError(DomainError, ValueError):
    """A value object or entity was built with invalid data."""


class InvalidTransitionError(DomainError):
    """An entity was asked to move to a state its lifecycle does not allow."""


class NotFoundError(DomainError):
    """The requested aggregate does not exist."""


class CommandNotAllowedError(DomainError):
    """The command does not exist for this kind of device, or the device cannot take commands now."""


class PermissionDeniedError(DomainError):
    """The actor's role does not allow the action."""


class AuthenticationError(DomainError):
    """Wrong credentials, or a token that is missing, expired or belongs to nobody active. The message
    never says which: that would help someone guessing accounts."""


class TooManyAttemptsError(DomainError):
    """Too many failed logins for this account from this origin; ``retry_after_s`` says when to retry."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"Too many failed attempts: retry in {retry_after_s} s")
        self.retry_after_s = retry_after_s
