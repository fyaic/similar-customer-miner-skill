import copy
import hashlib
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from . import VERSION
from .security import redact, secret_values, private_json
from .store import units

REFERENCES = Path(__file__).resolve().parents[2] / 'references'
# __file__: scripts/peers_core/api.py -> skill is parents[2]
CATALOG = json.loads((REFERENCES / 'api-catalog.json').read_text())
PRICES = json.loads((REFERENCES / 'prices.json').read_text())


def validate(value, schema, path='body'):
    if value is None and schema.get('nullable'):
        return
    choices = schema.get('oneOf') or schema.get('anyOf')
    if choices:
        for option in choices:
            try:
                validate(value,option,path)
                return
            except ValueError:
                pass
        raise ValueError(path + ': no schema variant matches')
    typ = schema.get('type')
    valid = {'object': isinstance(value,dict), 'array': isinstance(value,list),
             'string': isinstance(value,str), 'integer': type(value) is int,
             'number': type(value) in (int,float), 'boolean': type(value) is bool,
             'null': value is None}
    if typ in valid and not valid[typ]:
        raise ValueError(path + ': expected ' + typ)
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(path + ': unsupported enum')
    if isinstance(value,dict):
        missing = [k for k in schema.get('required',[]) if k not in value]
        if missing:
            raise ValueError(path + ': missing ' + ', '.join(missing))
        for k,v in value.items():
            if k in schema.get('properties',{}):
                validate(v,schema['properties'][k],path+'.'+k)
    if isinstance(value,list):
        for i,v in enumerate(value):
            validate(v,schema.get('items',{}),path+'['+str(i)+']')
    if type(value) in (int,float):
        if not Decimal(str(value)).is_finite():
            raise ValueError(path + ': number is not finite')
        if value < schema.get('minimum',value) or value > schema.get('maximum',value):
            raise ValueError(path + ': number out of bounds')


def normalize_search_aliases(name,body):
    """Keep common search constraints from silently becoming ignored extension fields."""
    if name not in ('company.search','people.search'):return
    aliases={'company_names':('company','names')}
    if name=='company.search':
        aliases.update({k:('company',v) for k,v in [('domain','domains'),('domains','domains'),('names','names')]})
    else:
        aliases.update({'company_domains':('company','domains'),'titles':('job','job_titles'),
                        'job_titles':('job','job_titles'),'departments':('job','departments')})
    for alias,(group,field) in aliases.items():
        if alias not in body:continue
        value=body.pop(alias)
        if isinstance(value,str):value=[value]
        target=body.setdefault(group,{})
        if not isinstance(target,dict):raise ValueError(group+' must be an object')
        if field in target and target[field]!=value:raise ValueError('Conflicting search filters: '+alias+' and '+group+'.'+field)
        target[field]=value
    job=body.get('job')
    if name=='people.search' and isinstance(job,dict) and 'titles' in job:
        value=job.pop('titles');value=[value] if isinstance(value,str) else value
        if 'job_titles' in job and job['job_titles']!=value:raise ValueError('Conflicting job title filters')
        job['job_titles']=value


def prepare(name, body=None, params=None, insight_prefix='/insight'):
    if name not in CATALOG['operations']:
        raise ValueError('Unknown operation; use catalog')
    spec = copy.deepcopy(CATALOG['operations'][name])
    body = copy.deepcopy({} if body is None else body)
    if not isinstance(body,dict):
        raise ValueError('Request body must be an object')
    normalize_search_aliases(name,body)
    if name in ('company.search','company.enrich','people.search','people.enrich'):
        wf = body.setdefault('waterfall',{})
        if not isinstance(wf,dict):
            raise ValueError('waterfall must be an object')
        wf.setdefault('mode','first_match')
        if wf['mode'] not in ('first_match','aggregate'):
            raise ValueError('Unknown waterfall mode')
        if name.endswith('.search'):
            body.setdefault('page',1);body.setdefault('per_page',10)
            if type(body['page']) is not int or type(body['per_page']) is not int or body['page']<1 or body['per_page']<1:
                raise ValueError('page and per_page must be positive integers')
        if name=='people.enrich':
            wf.setdefault('reveal_phone',False)
            if wf['reveal_phone'] in ('true','false'):wf['reveal_phone']=wf['reveal_phone']=='true'
            if wf['reveal_phone'] not in (True,False,'true','false'):
                raise ValueError('Invalid reveal_phone')
    schemas=spec['schemas']
    if name=='email.verify':
        modes={'single':0,'bulk_create':1,'bulk_result':2}
        if body.get('type') not in modes:raise ValueError('email type must be single, bulk_create or bulk_result')
        schemas=[schemas[modes[body['type']]]]
        if body['type']=='bulk_create' and (not isinstance(body.get('emails'),list) or not body['emails']):raise ValueError('Nonempty emails list required')
    if schemas:
        errors=[]
        for schema in schemas:
            try:
                validate(body,schema)
                break
            except ValueError as exc:errors.append(str(exc))
        else:
            raise ValueError('; '.join(errors))
    for field in re.findall(r'{([^}]+)}',spec['path']):
        value = str((params or {}).get(field,''))
        if not re.fullmatch(r'[A-Za-z0-9_-]+',value):
            raise ValueError('Missing/invalid path parameter: '+field)
        spec['path'] = spec['path'].replace('{'+field+'}',value)
    if spec['path'].startswith('/insight/'):
        spec['path'] = insight_prefix + spec['path'][len('/insight'):]
    spec['body'] = body
    # Output includes no credentials, but the internal body retains them for a single request.
    return spec


def estimate(spec):
    path = spec['path'].replace('/api/insight/','/insight/')
    body = spec['body']
    if spec['access'] in ('read','admin'):
        return Decimal(0)
    if path.startswith('/api/agentic/'):
        return None  # list/task may settle delivered leads, not just search
    op = path.removeprefix('/api/').lstrip('/')
    rates = [r for r in PRICES['rates'] if r['operation']==op]
    if path=='/api/email/verify':
        if body.get('type')=='bulk_result':return Decimal(0)
        return Decimal('.1') * (len(body.get('emails',[])) if body.get('type')=='bulk_create' else 1)
    if any('source' in r for r in rates):
        wf = body.get('waterfall',{})
        sources = wf.get('source_order')
        if isinstance(sources,list):
            if not sources:raise ValueError('source_order must not be empty')
            aliases={'store_leads':'storelead','storeleads':'storelead','ecommerce':'storelead'}
            sources=[aliases.get(s,s) for s in sources]
            if op=='company/search':
                if body.get('ecommerce',{}).get('enabled') is True and 'storelead' not in sources:sources.append('storelead')
                if body.get('local_search',{}).get('enabled') is True and 'map' not in sources:sources.append('map')
        if sources is not None and (not isinstance(sources,list) or not sources or any(s not in {r['source'] for r in rates} for s in sources)):
            raise ValueError('Unknown/empty source_order; use catalog and price reference')
        phone = wf.get('reveal_phone') in (True,'true')
        selected = [r for r in rates if (not sources or r['source'] in sources) and (r.get('phone')==phone or phone and r['source'] not in ('apollo','rocketreach'))]
        # Even first_match can enrich different fields from multiple sources.
        return sum((Decimal(r['credits']) for r in selected),Decimal(0))
    if rates:
        rate = rates[0]
        if rate['unit']=='returned row':
            limit = body.get('limit')
            if type(limit) is not int or limit < 1:
                return None
            return Decimal(rate['credits']) * limit
        return Decimal(rate['credits'])
    return None


def billing(payload):
    if not isinstance(payload,dict):return None
    meta = payload.get('meta') or {}
    bill = meta.get('billing') or payload.get('billing') or {}
    for key in ('total_credits_charged','credits_charged','platform_credits_charged'):
        if bill.get(key) is not None:
            units(bill[key])
            return Decimal(str(bill[key]))
    return None


def outcome(payload):
    if not isinstance(payload,dict):return 'completed'
    if payload.get('success') is False or payload.get('status') in ('failed','error') or payload.get('error'):
        return 'failed'
    status = str(payload.get('status','')).lower()
    if status in ('pending','running','processing','queued','created') or (payload.get('meta') or {}).get('waterfall',{}).get('async_pending'):
        return 'pending'
    if payload.get('task_id') or payload.get('taskId'):
        if status not in ('completed','done','success'):
            return 'pending'
    data=payload.get('data')
    dimensions=data.get('dimensions') if isinstance(data,dict) else None
    if isinstance(dimensions,dict) and any(isinstance(v,dict) and (v.get('error') or v.get('status') in ('error','failed')) for v in dimensions.values()):
        return 'partial'
    if isinstance(data,dict) and data.get('code') not in (None,0,1,200,'0','1','200'):
        return 'failed'
    return 'completed'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Redirect refused; credentials not forwarded')


def transport(method,url,body,headers,timeout):
    request=urllib.request.Request(url,data=None if body is None else json.dumps(body,allow_nan=False).encode(),headers=headers,method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=timeout) as res:
            raw=res.read(16*1024*1024+1)
            code=res.status
    except urllib.error.HTTPError as exc:
        code=exc.code;raw=exc.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:
        raise ValueError('Response too large; request outcome must be reconciled')
    try:payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError):payload={'text':raw.decode('utf8',errors='replace')}
    return code,payload


class Client:
    def __init__(self,settings,store,send=transport):
        self.settings=settings;self.store=store;self.send=send

    def call(self,name,body,op_id,params=None,query=None,reserve=None,admin=False,unbounded=False,timeout=45,settles=None,secret_output=None):
        spec=prepare(name,body,params,self.settings['insight_prefix'])
        method,path=spec['method'],spec['path']
        if spec['access']=='admin' and not admin:
            raise ValueError('Account mutation requires --admin-authorized from explicit user intent')
        if path.startswith('/api/agentic/') and not unbounded:
            raise ValueError('Agentic requires --accept-unbounded-cost; cancellation and provider cap unverified')
        public=path.startswith('/api/reference/') or path in ('/api/health','/api/metrics','/api/customs/reference/countries','/api/auth/register','/api/auth/login')
        if not public and not self.settings['key']:
            raise ValueError('Missing TRADEWIND_API_KEY; use doctor')
        est=estimate(spec)
        billable=spec['access']=='data' and not (path=='/api/email/verify' and spec['body'].get('type')=='bulk_result')
        if reserve is None:
            if est is None:raise ValueError('Unbounded/unknown unit count; supply a planning --reserve, not a provider hard cap')
            reserve=est
        elif est is not None and Decimal(str(reserve))<est:
            raise ValueError('Reserve below published conservative estimate')
        units(reserve)
        query=query or {}
        url=self.settings['base']+path
        if query:url+='?'+urllib.parse.urlencode(query,doseq=True)
        secrets=[self.settings['key'],*secret_values(spec['body']),*secret_values(query)]
        fingerprint=hashlib.sha256(json.dumps([method,path,spec['body'],query],sort_keys=True,allow_nan=False).encode()).hexdigest()
        safe_request=redact({'body':spec['body'],'query':query},secrets)
        parent=None
        is_result = '/insight/customs/' in path and method=='GET' or path=='/api/email/verify' and spec['body'].get('type')=='bulk_result'
        if is_result and not settles:
            raise ValueError('Task result requires --settles creation-operation-id; use task-adopt for external tasks')
        if secret_output and (spec['access']!='admin' or not admin):
            raise ValueError('Secret output is only for explicitly authorized account operations')
        if settles:
            parent=self.store.get(settles)
            if not parent or not parent['task_id']:
                raise ValueError('Settlement parent needs a persisted task id')
            expected=parent['task_id']
            actual=(params or {}).get('task_id') or spec['body'].get('task_id')
            insight=parent['path'].replace('/api/insight/','/insight/')
            is_insight=insight in ('/insight/customs/match','/insight/customs/profile') and path.replace('/api/insight/','/insight/')==insight+'/'+expected
            is_bulk=parent['path']=='/api/email/verify' and spec['body'].get('type')=='bulk_result'
            if expected!=actual or not (is_insight or is_bulk):
                raise ValueError('Settlement route/task does not match parent')
        previous=self.store.reserve(op_id,fingerprint,method,path,safe_request,reserve,billable)
        if previous:
            return {'operation_id':op_id,'reused':True,'state':previous['state'],'response':json.loads(previous['response'] or '{}'),'billing_known':bool(previous['billing_known'])}
        headers={'Accept':'application/json','Content-Type':'application/json','User-Agent':f'Similar-Customer-Miner/{VERSION}'}
        if self.settings['key'] and path not in ('/api/auth/register','/api/auth/login'):
            headers['Authorization']='Bearer '+self.settings['key']
        safe=None;code=None
        try:
            code,payload=self.send(method,url,None if method=='GET' else spec['body'],headers,timeout)
            if secret_output and 200<=code<300:
                private_json(secret_output,payload)
            secrets.extend(secret_values(payload))
            safe=redact(payload,secrets)
            charged=billing(payload)
            state=outcome(payload) if 200<=code<300 else 'failed'
            # Nonterminal/protocol outcomes are never silently converted to free failures.
            if code<200 or code>=500 or 300<=code<400:state='unknown'
            if state=='completed' and (spec['access']=='data') and not isinstance(payload,dict):state='unknown'
            if isinstance(payload,dict) and 'text' in payload and spec['access']=='data':state='unknown'
            if charged is None and spec['access'] in ('read','admin') and not parent:
                charged=Decimal(0)
            if state=='completed' and billable and charged is None:state='unknown'
            request_id=payload.get('request_id') if isinstance(payload,dict) else None
            task_id=(payload.get('task_id') or payload.get('taskId') or (payload.get('data',{}).get('taskId') if isinstance(payload.get('data'),dict) else None)) if isinstance(payload,dict) else None
            self.store.finish(op_id,(('completed' if 200<=code<300 else 'failed') if parent else state),safe,0 if parent else charged,request_id,task_id,note='HTTP '+str(code)+'; transport='+('live' if self.send is transport else 'injected'))
            if parent and state in ('completed','failed','partial'):
                # Query billing is the cumulative parent-task charge, not a second charge.
                self.store.finish(settles,state,json.loads(parent['response'] or '{}'),charged,note='settlement via '+op_id,cumulative=True)
            return {'operation_id':op_id,'reused':False,'http_status':code,'state':state,'credits':str(charged) if charged is not None else None,'response':safe}
        except Exception as exc:
            self.store.finish(op_id,'failed' if parent else 'unknown',{'error_type':type(exc).__name__,'message':redact(str(exc),secrets),'http_status':code,'payload':safe},0 if parent else None,note='Query failed; parent task remains reserved' if parent else 'Transport/protocol failed; reconcile before retry')
            return {'operation_id':op_id,'state':'failed' if parent else 'unknown','credits':None,'error_type':type(exc).__name__}
