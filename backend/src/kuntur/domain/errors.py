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
