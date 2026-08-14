"""Credential health check and preflight validation.

Provides a single :func:`check_credentials` entry point that inspects the
loaded config, classifies each credential's status, and optionally performs
a lightweight live auth probe for the critical ones.

Used by:
    - ``src.cli``  — preflight before a live pipeline run
    - ``scripts/check_secrets.py`` — standalone health-report command
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from src.secret_errors import SecretError, SecretMissingError

logger = logging.getLogger("similar_customer_miner")

# (service, config_section, config_key, env_var, required, optional_label)
CREDENTIAL_REGISTRY = [
    ("apify", "apify", "api_token", "APIFY_API_TOKEN", True, "ImportYeti buyer discovery + BOL verify"),
    ("hunter", "hunter", "api_key", "HUNTER_API_KEY", False, "email discovery"),
    ("opencorporates", "opencorporates", "api_token", "OPENCORPORATES_API_TOKEN", False, "company registration verify"),
    ("comtrade", "comtrade", "subscription_key", "COMTRADE_SUBSCRIPTION_KEY", False, "macro market size (raises rate limits)"),
    ("google", "google", "fact_check_api_key", "GOOGLE_FACT_CHECK_API_KEY", False, "external fact-check citations"),
]


@dataclass
class CredentialReport:
    """Status of a single credential."""

    service: str
    configured: bool
    required: bool
    env_var: str
    status: str  # "ok" | "missing" | "invalid" | "exhausted" | "forbidden" | "unchecked"
    detail: Optional[str] = None
    remediation: Optional[str] = None
    uses: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "configured": self.configured,
            "required": self.required,
            "env_var": self.env_var,
            "status": self.status,
            "detail": self.detail,
            "remediation": self.remediation,
            "uses": self.uses,
        }


@dataclass
class HealthReport:
    """Aggregate credential health report."""

    checks: List[CredentialReport] = field(default_factory=list)

    @property
    def all_required_ok(self) -> bool:
        return all(c.status == "ok" for c in self.checks if c.required)

    @property
    def has_fatal(self) -> bool:
        """True if any *required* credential is missing or broken."""
        return any(
            c.required and c.status in {"missing", "invalid", "forbidden"}
            for c in self.checks
        )

    def fatal_errors(self) -> List[CredentialReport]:
        return [c for c in self.checks if c.required and c.status in {"missing", "invalid", "forbidden"}]

    def warnings(self) -> List[CredentialReport]:
        return [c for c in self.checks if not c.required and c.status != "ok"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_required_ok": self.all_required_ok,
            "has_fatal": self.has_fatal,
            "checks": [c.to_dict() for c in self.checks],
        }


def _get_credential(config: Dict[str, Any], section: str, key: str, env_var: str) -> Optional[str]:
    """Read a credential from config or env, whichever is set."""
    val = config.get(section, {}).get(key)
    if val:
        return val
    return os.getenv(env_var)


def check_credentials(
    config: Dict[str, Any],
    *,
    live_probe: bool = False,
    probe_only: Optional[List[str]] = None,
) -> HealthReport:
    """Inspect all registered credentials and return a health report.

    Args:
        config:     the fully loaded + mode-applied config dict.
        live_probe: if True, perform a lightweight auth check against each
                    configured credential's provider (e.g. Apify ``/users/me``).
        probe_only: if set, only live-probe these service names (e.g.
                    ``["apify"]``).  Ignored when ``live_probe`` is False.
    """
    report = HealthReport()

    for service, section, key, env_var, required, uses in CREDENTIAL_REGISTRY:
        cred = _get_credential(config, section, key, env_var)
        if not cred:
            report.checks.append(CredentialReport(
                service=service,
                configured=False,
                required=required,
                env_var=env_var,
                status="missing",
                detail=f"not set in config/{section}.{key} or ${env_var}",
                remediation=f"Add {service} key to config/local.yaml or set {env_var}",
                uses=uses,
            ))
            continue

        # Credential is configured. If not probing, assume ok structurally.
        if not live_probe:
            report.checks.append(CredentialReport(
                service=service,
                configured=True,
                required=required,
                env_var=env_var,
                status="unchecked",
                detail="configured (live probe not requested)",
                uses=uses,
            ))
            continue

        # Live probe: only probe if in probe_only (or probe_only is None = all)
        if probe_only and service not in probe_only:
            report.checks.append(CredentialReport(
                service=service,
                configured=True,
                required=required,
                env_var=env_var,
                status="unchecked",
                detail="configured (skipped probe)",
                uses=uses,
            ))
            continue

        status, detail, remediation = _probe_service(service, cred)
        report.checks.append(CredentialReport(
            service=service,
            configured=True,
            required=required,
            env_var=env_var,
            status=status,
            detail=detail,
            remediation=remediation,
            uses=uses,
        ))

    return report


def _probe_service(service: str, credential: str) -> tuple[str, Optional[str], Optional[str]]:
    """Perform a lightweight auth probe for a single service.

    Returns ``(status, detail, remediation)``.  Network errors are reported
    as ``"unchecked"`` (not fatal) — we don't want a flaky connection to block
    the pipeline; the real call will surface it.
    """
    try:
        if service == "apify":
            resp = requests.get(
                "https://api.apify.com/v2/users/me",
                params={"token": credential},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return "ok", f"auth ok (account: {data.get('username', data.get('id', '?'))})", None
            from src.secret_errors import classify_http_error
            err = classify_http_error("apify", resp)
            return err.kind, str(err), err.remediation

        if service == "hunter":
            resp = requests.get(
                "https://api.hunter.io/v2/account",
                params={"api_key": credential},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                calls_left = data.get("calls", {})
                return "ok", f"auth ok (plan: {data.get('plan_name', '?')}, email credits: {calls_left.get('left', '?')})", None
            from src.secret_errors import classify_http_error
            err = classify_http_error("hunter", resp)
            return err.kind, str(err), err.remediation

        if service == "google":
            resp = requests.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={"query": "test", "key": credential},
                timeout=15,
            )
            if resp.status_code == 200:
                return "ok", "auth ok", None
            from src.secret_errors import classify_http_error
            err = classify_http_error("google", resp)
            return err.kind, str(err), err.remediation

        if service == "opencorporates":
            # Just check the key is non-empty; a full probe would burn the
            # rate-limited free tier. Mark as "unchecked" (configured).
            return "unchecked", "configured (probe skipped to conserve rate limit)", None

        if service == "comtrade":
            return "unchecked", "configured (probe skipped — UN API requires subscription)", None

        return "unchecked", "configured (unknown service)", None

    except requests.ConnectionError as exc:
        logger.debug("Probe connection error for %s: %s", service, exc)
        return "unchecked", f"configured (probe failed: network — {exc.__class__.__name__})", None
    except Exception as exc:
        logger.debug("Probe error for %s: %s", service, exc)
        return "unchecked", f"configured (probe failed: {exc.__class__.__name__})", None


def format_report(report: HealthReport, *, use_color: bool = True) -> str:
    """Render a human-readable credential health report."""
    lines = ["", "=" * 60, "Credential Health Report", "=" * 60]

    status_icon = {
        "ok": "✅",
        "missing": "❌",
        "invalid": "🔑",
        "exhausted": "⏳",
        "forbidden": "🚫",
        "unchecked": "✔️ ",  # configured but not probed
    }

    for c in report.checks:
        icon = status_icon.get(c.status, "?")
        req_tag = " [REQUIRED]" if c.required else " [optional]"
        lines.append(f"  {icon} {c.service:<18} {c.status:<10}{req_tag}")
        if c.detail:
            lines.append(f"     └─ {c.detail}")
        if c.remediation:
            lines.append(f"     └─ fix: {c.remediation}")

    # Summary
    lines.append("")
    if report.all_required_ok:
        lines.append("✅ All required credentials are healthy.")
    else:
        fatal = report.fatal_errors()
        lines.append(f"❌ {len(fatal)} required credential(s) have issues:")
        for c in fatal:
            lines.append(f"   • {c.service}: {c.status} — {c.remediation}")

    warnings = report.warnings()
    if warnings:
        lines.append(f"⚠️  {len(warnings)} optional credential(s) have issues (pipeline will degrade gracefully).")

    lines.append("=" * 60)
    return "\n".join(lines)
