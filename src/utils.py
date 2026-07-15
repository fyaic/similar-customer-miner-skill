"""Shared utilities: logging, cache, helpers."""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Set up root logger."""
    logger = logging.getLogger("similar_customer_miner")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_cache_dir(config: Dict[str, Any]) -> Optional[Path]:
    """Return cache directory from config."""
    cache_enabled = config.get("cache", {}).get("enabled", True)
    if not cache_enabled:
        return None
    raw = config.get("cache", {}).get("dir", "~/.cache/similar-customer-miner")
    path = Path(os.path.expanduser(raw))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(*args: Any) -> str:
    """Generate a deterministic cache key."""
    payload = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def read_cache(cache_dir: Path, key: str, ttl_days: int) -> Optional[Any]:
    """Read cached value if not expired."""
    if not cache_dir:
        return None
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(days=ttl_days):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_cache(cache_dir: Path, key: str, value: Any) -> None:
    """Write value to cache."""
    if not cache_dir:
        return
    path = cache_dir / f"{key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, default=str)


def clean_text(value: Any) -> Optional[str]:
    """Clean text field."""
    if value is None:
        return None
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text if text else None


def split_values(value: Optional[str], separators: Optional[List[str]] = None) -> List[str]:
    """Split a string by common separators."""
    if not value:
        return []
    seps = separators or ["/", ",", ";", "|", "、"]
    pattern = "|".join(re.escape(s) for s in seps)
    parts = re.split(pattern, str(value))
    return [p.strip() for p in parts if p.strip()]


def normalize_company_name(name: Optional[str]) -> Optional[str]:
    """Normalize company name for matching."""
    if not name:
        return None
    name = str(name).strip().lower()
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name)
    suffixes = [
        "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
        "co", "company", "plc", "gmbh", "sa", "srl", "bv", "pty", "kg",
    ]
    words = name.split()
    words = [w for w in words if w not in suffixes]
    return " ".join(words) if words else name


def bucket_number(value: Optional[str]) -> Optional[str]:
    """Convert numeric-ish value to a bucket label."""
    if not value:
        return None
    text = str(value).lower().replace(",", "").replace("$", "").strip()
    # Extract first numeric token
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return str(value).strip()
    num = float(match.group())
    # Heuristic: if user wrote "million" or contains many digits
    if "million" in text or "m" in text or num >= 1_000_000:
        num = num if num >= 1_000 else num * 1_000_000
    elif "billion" in text or "b" in text:
        num = num * 1_000_000_000
    elif "thousand" in text or "k" in text:
        num = num * 1_000
    if num >= 1_000_000_000:
        return "10亿+"
    if num >= 100_000_000:
        return "1-10亿"
    if num >= 10_000_000:
        return "1000万-1亿"
    if num >= 1_000_000:
        return "100-1000万"
    if num >= 100_000:
        return "10-100万"
    return "<10万"
