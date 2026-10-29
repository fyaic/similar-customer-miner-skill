#!/usr/bin/env python3
"""Build an allowlisted, checksummed skill ZIP. Internal keys never enter Git."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from src.tradewind_core import VERSION
PREFIX = 'similar-customer-miner/'


def build(output, key_file=None, recipient='internal'):
    output = Path(output).resolve()
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',recipient):
        raise ValueError('Invalid recipient')
    # Refuse mixed release documentation rather than silently shipping stale instructions.
    for name in ['README.md','README.en.md','ENGINEERING.md','ENGINEERING.zh-CN.md','docs/TRADEWIND_V2.md','docs/RELEASE_REVIEW.md']:
        if VERSION not in (ROOT/name).read_text().splitlines()[0]:
            raise ValueError('Release title/version mismatch: '+name)
    for name in ['docs/validation.json','docs/package-validation.json']:
        if json.loads((ROOT/name).read_text()).get('version') != VERSION:
            raise ValueError('Validation version mismatch: '+name)
    for name in ['SKILL.md','pyproject.toml','config/default.yaml']:
        if not re.search(r'version\s*[:=]\s*[\"\']'+re.escape(VERSION)+r'[\"\']', (ROOT/name).read_text()):
            raise ValueError('Source version mismatch: '+name)
    files = {}
    for folder in ['src','tools','config','references']:
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and path.suffix in {'.py','.yaml','.json','.md'} and '__pycache__' not in path.parts and path.name not in {'local.yaml','secrets.yaml'}:
                files[str(path.relative_to(ROOT))] = path.read_bytes()
    for name in ['SKILL.md','README.md','README.en.md','requirements.txt','LICENSE','scripts/run.py','scripts/verify_package.py','scripts/tradewind_ops.py','scripts/check_output.py','scripts/run_report.py','examples/en_one_anchor.csv','examples/sample_customers.xlsx']:
        files[name] = (ROOT/name).read_bytes()
    # API contracts are needed at runtime; internal probe annotations are not.
    catalog = json.loads(files['references/api-catalog.json'])
    def strip_review_annotations(value):
        if isinstance(value, dict):
            return {k: strip_review_annotations(v) for k, v in value.items()
                    if k not in {'live_verified', 'live_scope'}}
        if isinstance(value, list):
            return [strip_review_annotations(v) for v in value]
        return value
    files['references/api-catalog.json'] = (json.dumps(strip_review_annotations(catalog), ensure_ascii=False, indent=2)+'\n').encode()
    # Reject secrets even if accidentally placed in an allowlisted source file.
    secret_pattern = re.compile(rb'(?:tw_live_[A-Za-z0-9_-]{12,}|apify_api_[A-Za-z0-9_-]{12,})')
    for name,data in files.items():
        if secret_pattern.search(data):
            raise ValueError('Credential detected in public source: '+name)
    identity = None
    if key_file:
        key_text = Path(key_file).read_text().strip()
        if 'TRADEWIND_API_KEY=' in key_text:
            key_text = next(line.split('=',1)[1].strip().strip('\"\'') for line in key_text.splitlines() if line.startswith('TRADEWIND_API_KEY='))
        if not re.fullmatch(r'tw_live_[A-Za-z0-9_-]{20,}',key_text):
            raise ValueError('Invalid Trade Wind key file')
        fingerprint=hashlib.sha256(key_text.encode()).hexdigest()[:16]
        identity={'recipient':recipient,'version':VERSION,'key_fingerprint':fingerprint,
                  'package_id':f'similar-customer-miner-{recipient}-{VERSION}-{fingerprint}',
                  'private':True,'provider':'tradewind','distribution_profile':'recipient'}
        files['.credentials/tradewind.env']=('TRADEWIND_API_KEY='+key_text+'\n').encode()
        files['DISTRIBUTION.json']=(json.dumps(identity,ensure_ascii=False,indent=2)+'\n').encode()
        files['README.md'] = (f'# 内部可直接使用包：{recipient}\n\n版本 {VERSION}；内置 Trade Wind 凭证。安装时保留 `.credentials/` 隐藏目录。仅向获准使用此账户的同事分发，不上传公开仓库。\n\n'+files['README.md'].decode()).encode()
    revision = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    status = subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True)
    manifest={'version':VERSION,'distribution_profile':'recipient','source_revision':revision.stdout.strip() if revision.returncode == 0 else None,
              'source_dirty':bool(status.stdout.strip()) if status.returncode == 0 else None,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.is_symlink():raise ValueError('Refusing symlink output')
    # Restrict file permissions before writing any secret-bearing bytes.
    import os
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.chmod(output,0o600)
    with os.fdopen(fd,'wb') as stream, zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(PREFIX+name,date_time=(2026,10,29,0,0,0))
            info.external_attr=(0o100600 if name.startswith('.credentials/') else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    sha=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(sha+'  '+output.name+'\n')
    return {'path':str(output),'sha256':sha,'files':len(files),'internal':bool(key_file),'identity':identity}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True);p.add_argument('--key-file');p.add_argument('--recipient',default='internal')
    a=p.parse_args();print(json.dumps(build(a.output,a.key_file,a.recipient),ensure_ascii=False,indent=2))
