"""Structured credential error typology.

Every external data source in this skill can fail for credential-related
reasons: a key was never configured, a key was revoked, the quota ran out,
or the key lacks permission.  Historically each tool surfaced these as a
mix of silent fallbacks, bare ``RuntimeError`` strings, or raw
``requests.HTTPError`` — leaving callers unable to distinguish a budget
problem from a network blip.

This module gives every credential failure a single shared vocabulary so
the CLI, the preflight check, and downstream callers can react precisely.
"""
from __future__ import annotations

from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Error hierarchy
# --------------------------------------------------------------------------- #

class SecretError(Exception):
    """Base class for all credential-related failures.

    Attributes:
        service:  which provider the key belongs to (``apify``, ``hunter`` …).
        kind:     machine-readable category, one of
                  ``missing`` / ``invalid`` / ``exhausted`` / ``forbidden``.
        remediation: a short, human-readable hint on how to fix it.
    """

    kind = "secret_error"

    def __init__(
        self,
        service: str,
        message: str,
        *,
        kind: Optional[str] = None,
        remediation: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        self.service = service
        self.kind = kind or self.kind
        self.remediation = remediation
        self.status_code = status_code
        super().__init__(f"[{self.kind}] {service}: {message}")

    def to_dict(self) -> dict[str, Any]:
        """Structured representation for JSON reports / CLI summaries."""
        return {
            "service": self.service,
            "kind": self.kind,
            "message": str(self),
            "remediation": self.remediation,
            "status_code": self.status_code,
        }


class SecretMissingError(SecretError):
    """The credential is not configured at all (empty config / no env var)."""

    kind = "missing"

    def __init__(self, service: str, env_var: Optional[str] = None, **kw: Any):
        where = f" (set via {env_var} or config/local.yaml)" if env_var else " (set in config/local.yaml)"
        kw.setdefault(
            "remediation",
            f"Add the {service} credential{where} and re-run.",
        )
        super().__init__(service, f"no {service} credential configured", **kw)


class SecretInvalidError(SecretError):
    """The provider rejected the key (HTTP 401 / key malformed)."""

    kind = "invalid"

    def __init__(self, service: str, detail: str = "key rejected by provider", **kw: Any):
        kw.setdefault(
            "remediation",
            f"The {service} key was rejected. Verify it is copied correctly and still "
            f"active in the provider dashboard.",
        )
        super().__init__(service, detail, **kw)


class SecretExhaustedError(SecretError):
    """Quota / rate-limit hit (HTTP 402, 429, or plan-exhausted body)."""

    kind = "exhausted"

    def __init__(self, service: str, detail: str = "quota or rate limit exceeded", **kw: Any):
        kw.setdefault(
            "remediation",
            f"The {service} quota is exhausted. Wait for the reset window or upgrade the plan.",
        )
        super().__init__(service, detail, **kw)


class SecretForbiddenError(SecretError):
    """The key is valid but lacks permission for this resource (HTTP 403)."""

    kind = "forbidden"

    def __init__(self, service: str, detail: str = "forbidden", **kw: Any):
        kw.setdefault(
            "remediation",
            f"The {service} key is valid but lacks permission for this resource "
            f"(e.g. Apify monthly hard-limit, or the token scope is too narrow).",
        )
        super().__init__(service, detail, **kw)


# --------------------------------------------------------------------------- #
# HTTP response → SecretError classifier
# --------------------------------------------------------------------------- #

_KIND_BY_STATUS = {
    401: SecretInvalidError,
    402: SecretExhaustedError,
    403: SecretForbiddenError,
    429: SecretExhaustedError,
}


def classify_http_error(service: str, resp: Any) -> SecretError:
    """Map a ``requests.Response`` with a failure status to a ``SecretError``.

    Call this *instead of* ``resp.raise_for_status()`` when the response came
    from an authenticated endpoint.  Network / connection errors (which have no
    response object) should still propagate as their own exception type.

    Args:
        service: provider slug, e.g. ``"apify"``.
        resp:    a ``requests.Response`` whose ``status_code`` indicates failure.

    Returns:
        A ``SecretError`` subclass instance.  Never returns for 2xx responses
        (raises ``ValueError`` — this helper is only for failures).

    Raises:
        ValueError: if ``resp.status_code`` is a success code.
        requests.HTTPError: for non-credential HTTP errors (5xx etc.) so the
            caller's existing error handling still works.
    """
    import requests  # local import to avoid hard dep at import time

    status = resp.status_code

    if status < 400:
        raise ValueError(f"classify_http_error called on success status {status}")

    # Try to extract a useful detail message from the body.
    detail = f"HTTP {status}"
    try:
        body = resp.json()
        msg = (
            body.get("error", {}).get("message")
            or body.get("error", {}).get("description")
            or body.get("message")
            or body.get("error")
        )
        if msg:
            detail = f"HTTP {status}: {msg}"
    except (ValueError, AttributeError):
        if resp.text:
            detail = f"HTTP {status}: {resp.text[:200]}"

    err_cls = _KIND_BY_STATUS.get(status)
    if err_cls is not None:
        return err_cls(service, detail, status_code=status)

    # 5xx and other non-credential failures: re-raise as HTTPError so callers
    # can still catch transient infra issues separately.
    raise requests.HTTPError(detail, response=resp)


def raise_for_status_classified(service: str, resp: Any) -> None:
    """Drop-in replacement for ``resp.raise_for_status()`` that classifies
    credential errors into ``SecretError`` subtypes.

    For 2xx: returns silently (same as ``raise_for_status``).
    For 401/402/403/429: raises the matching ``SecretError`` subclass.
    For other 4xx/5xx: raises ``requests.HTTPError`` (same as ``raise_for_status``).
    """
    if resp.status_code < 400:
        return
    raise classify_http_error(service, resp)
