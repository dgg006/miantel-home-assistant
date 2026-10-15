"""Errors deliberately exclude URLs, response bodies and account identifiers."""


class MiAntelError(Exception):
    """Base error with a static, public-safe message."""


class AuthenticationError(MiAntelError):
    """Credentials were rejected or the authenticated session could not be restored."""


class AdditionalAuthenticationRequired(AuthenticationError):
    """TuID requires an interactive step unsupported by this client."""


class SessionExpired(MiAntelError):
    """A normal login is required."""


class ConnectionError(MiAntelError):
    """Transport or upstream server failure."""


class RateLimited(ConnectionError):
    """The upstream server asked to slow down."""


class ParseError(MiAntelError):
    """The website no longer matches a supported read-only view."""
