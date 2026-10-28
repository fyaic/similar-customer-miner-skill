import hashlib
import json
import os
import re
from pathlib import Path

SECRET = re.compile(r'password|secret|token|authorization|api.?key|client_id|credential|^key$|^bearer$', re.I)
TOKEN = re.compile(r'\btw_[A-Za-z0-9_-]+|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if SECRET.search(k) else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        return TOKEN.sub('[REDACTED]', value)
    return value


def secret_values(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if SECRET.search(k) and isinstance(v, str):
                yield v
            else:
                yield from secret_values(v)
    elif isinstance(value, list):
        for v in value:
            yield from secret_values(v)


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing symlink output')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        os.chmod(path, 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def read_env(path):
    values = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.removeprefix('export ').strip()
            if key.startswith('TRADEWIND_'):
                values[key] = value.strip().strip('\"\'')
    return values


def settings(env_file=None):
    # No shell evaluation or arbitrary parent-directory credential discovery.
    path = Path(env_file) if env_file else Path.cwd() / '.env'
    values = read_env(path)
    env = {k: v for k, v in os.environ.items() if k.startswith('TRADEWIND_')}
    if env_file:
        if not values.get('TRADEWIND_API_KEY'):
            raise ValueError('Explicit env file is missing or has no TRADEWIND_API_KEY')
        values = {**env, **values}
        source = 'explicit_file'
    else:
        source = 'environment' if env.get('TRADEWIND_API_KEY') else 'workspace_file' if values.get('TRADEWIND_API_KEY') else 'none'
        values.update(env)
    skill_root=Path(__file__).resolve().parents[2]
    bundled=skill_root/'.credentials/tradewind.env'
    metadata_path=skill_root/'DISTRIBUTION.json'
    distribution=None
    if metadata_path.exists() and not bundled.exists():
        raise ValueError('Internal package incomplete: retain the entire .credentials folder when installing')
    if bundled.exists():
        if bundled.is_symlink() or bundled.parent.is_symlink() or metadata_path.is_symlink():raise ValueError('Refusing symlink bundled credentials or metadata')
        key=read_env(bundled).get('TRADEWIND_API_KEY','')
        try:meta=json.loads(metadata_path.read_text())
        except (OSError,ValueError):raise ValueError('Internal package metadata missing or invalid') from None
        if not isinstance(meta,dict) or not key or meta.get('key_fingerprint')!=hashlib.sha256(key.encode()).hexdigest()[:16]:
            raise ValueError('Internal package credentials do not match distribution metadata')
        recipient=meta.get('recipient','');package_id=meta.get('package_id','')
        if not isinstance(recipient,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',recipient) or not isinstance(package_id,str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,128}',package_id):
            raise ValueError('Invalid internal package identity')
        # A recipient's default package must not silently bill another workspace key.
        # Maintainers can intentionally override with --env-file; doctor exposes it.
        if env_file is None:values['TRADEWIND_API_KEY']=key;source='bundled'
        distribution={'recipient':recipient,'package_id':package_id,
                      'bundled_key_active':values.get('TRADEWIND_API_KEY')==key}
    base = values.get('TRADEWIND_API_BASE_URL', 'https://app.trade-wind.co').rstrip('/')
    if base != 'https://app.trade-wind.co':
        raise ValueError('Credentials may only be sent to https://app.trade-wind.co')
    prefix = values.get('TRADEWIND_INSIGHT_PREFIX', '/api/insight')
    if prefix not in ('/insight', '/api/insight'):
        raise ValueError('Invalid Insight prefix')
    return {'key': values.get('TRADEWIND_API_KEY', ''), 'config_source':source,'distribution':distribution,
            'base': base, 'insight_prefix': prefix,
            'state': values.get('TRADEWIND_STATE_DIR', str(Path.cwd() / '.similar-state'))}
