"""No-credential network diagnosis and conservative pre-connect classification."""
import errno
import json
import re
import urllib.error
import urllib.parse
import urllib.request


def connection_refused(exc):
    # Only a typed URLError caused by a refused connection establishes this
    # narrow pre-request failure. Timeouts/resets/TLS/generic exceptions do not.
    if not isinstance(exc, urllib.error.URLError) or isinstance(exc, urllib.error.HTTPError):
        return False
    reason = exc.reason
    return isinstance(reason, OSError) and (getattr(reason, 'winerror', None) == 10061
        or getattr(reason, 'errno', None) in {errno.ECONNREFUSED, 10061})


def proxy_summary(url, mode='system'):
    parsed = urllib.parse.urlsplit(url)
    proxies = urllib.request.getproxies() if mode == 'system' else {}
    bypass = mode == 'direct' or urllib.request.proxy_bypass(parsed.hostname)
    raw = proxies.get(parsed.scheme) if not bypass else None
    if raw:
        p = urllib.parse.urlsplit(raw if '://' in raw else 'http://'+raw)
        try: port = p.port or (443 if p.scheme == 'https' else 80)
        except ValueError: port = None
        return {'mode': mode, 'route': 'proxy', 'host': p.hostname, 'port': port}
    return {'mode': mode, 'route': 'direct', 'host': parsed.hostname, 'port': parsed.port or 443}


class StopRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def diagnose(mode='system', timeout=8):
    if mode not in {'system', 'direct'}:
        raise ValueError('proxy mode must be system or direct')
    url='https://app.trade-wind.co/'
    try:
        route=proxy_summary(url, mode)
    except (ValueError, OSError):
        return {'route':{'mode':mode,'route':'invalid_configuration'},'network_reachable':False,
                'business_api_calls':0,'credentials_sent':False,'category':'proxy_configuration_error',
                'next_action':'代理配置无法解析，未发起请求；请由运维检查配置，未修改系统设置。'}
    handlers=[StopRedirect()]
    if mode == 'direct': handlers.append(urllib.request.ProxyHandler({}))
    result={'route':route,'target':url,'method':'HEAD','credentials_sent':False,
            'business_api_calls':0,'billing':'not_applicable','http_status':None}
    try:
        with urllib.request.build_opener(*handlers).open(urllib.request.Request(url, method='HEAD'), timeout=timeout) as response:
            result.update(http_status=response.status, network_reachable=True)
    except urllib.error.HTTPError as exc:
        # Even a 403/405 or redirect proves an HTTP exchange, not API usability.
        result.update(http_status=exc.code, network_reachable=True)
    except Exception as exc:
        result.update(network_reachable=False,error_type=type(exc).__name__,
            category='connection_refused' if connection_refused(exc) else 'network_unresolved')
    result['next_action'] = ('网络路径可达；这不证明业务API、key或余额正常。' if result['network_reachable'] else
        '代理连接被拒绝：检查已配置代理服务/端口，未修改系统设置。' if route['route']=='proxy' and result.get('category')=='connection_refused' else
        '连接未建立或网络检查失败；保留诊断报告，不重复收费查询，不承诺等待后自动恢复。')
    return result


def legacy_refusal(row):
    """Strict opt-in migration of rc4's preserved Windows refusal evidence."""
    try: payload=json.loads(row.get('response') or '{}')
    except (ValueError, TypeError): return False
    return bool(row['state']=='unknown' and not row['billing_known'] and row['charged']==0
        and not row.get('request_id') and not row.get('task_id')
        and row.get('notes')=='Transport/protocol failed; reconcile before retry'
        and row.get('path') in {'/api/company/search','/api/company/enrich','/api/people/search','/api/people/enrich','/api/email/verify','/api/customs/search'}
        and isinstance(payload,dict) and payload.get('error_type')=='URLError'
        and payload.get('http_status') is None and payload.get('payload') is None
        and re.search(r'\[WinError 10061\]', str(payload.get('message',''))))
