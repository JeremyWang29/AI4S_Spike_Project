"""Bounded HTTP gateway. Reserve one paid attempt under lock, call outside it."""
import json
import uuid
from urllib.request import Request, build_opener, HTTPRedirectHandler
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from config.errors import BusinessError
from modules.core import fingerprint, require_revision
from modules.identity.authorization import require_project
from .models import SuggestionReceipt, MutationRecord
from .guided import FIELDS, RELATIONS
from .validation import invalid, text, bounded_json
from modules.knowledge.services import graph_terms_for

def config():
    return getattr(settings, 'AI4S_SCOPE_PROVIDER', {})

def inputs_for(project, scope):
    fields = scope.details.get('research_fields', {})
    return {'title': project.name, 'direction': scope.direction, 'core_keywords': scope.core_keywords,
            'research_fields': {key: {'status': fields.get(key, {}).get('status'),
                'text': fields.get(key, {}).get('text', '') if fields.get(key, {}).get('status') == 'answered' else ''}
                for key in FIELDS}}

def graph_candidates(rows):
    return [dict(row, decision='pending', replacement='', variant_selected=False,
                 reason=row['definition'] or '图谱术语', review_required=False, conflict=False) for row in rows]

def shareable_graph_context(rows):
    return [{key: row[key] for key in ('concept_id','term','definition','parent_keyword','relation','graph_version')}
            for row in rows if row['external_sharing_allowed']]

def reconcile(terms):
    by_surface = {}
    for term in terms:
        key = (term['parent_keyword'].casefold(), term['term'].casefold())
        by_surface.setdefault(key, []).append(term)
    for group in by_surface.values():
        concepts = {(t.get('concept_id'), t['relation']) for t in group if t['source'] == 'graph'}
        relations = {t['relation'] for t in group}
        ambiguous = len(concepts) > 1 or len(relations) > 1
        if ambiguous:
            for term in group: term['conflict'] = True
    return terms

def http_generate(inputs, cfg):
    if not isinstance(cfg.get('url'), str) or not cfg['url'].startswith('https://'):
        raise ValueError('provider URL must use HTTPS')
    request = Request(cfg['url'], data=json.dumps({'model': cfg['model'], 'input': inputs,
        'schema': 'ai4s-guided-scope-v1', 'mechanisms_are_hypotheses': True}).encode(),
        headers={'Content-Type':'application/json', 'Authorization':'Bearer '+cfg['key']}, method='POST')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError('provider redirects forbidden')
    with build_opener(NoRedirect).open(request, timeout=min(max(float(cfg.get('timeout',20)),1),60)) as response:
        raw=response.read(min(int(cfg.get('max_bytes',65536)),262144)+1)
    if len(raw)>min(int(cfg.get('max_bytes',65536)),262144): raise ValueError('output limit')
    return json.loads(raw)

def validate_output(raw, inputs):
    bounded_json(raw)
    if not isinstance(raw,dict) or set(raw)!={'fields','terms'}: invalid('模型响应格式无效')
    if not isinstance(raw['fields'],dict) or set(raw['fields'])!=set(FIELDS): invalid('模型研究字段不完整')
    result={'fields':{},'terms':[]}
    for key, field in raw['fields'].items():
        if not isinstance(field,dict) or set(field)!={'options','question'}: invalid('模型字段格式无效')
        options=field['options']; question=text(field['question'],'追问',1000,False)
        if not isinstance(options,list) or not ((3<=len(options)<=5 and not question) or (not options and question)): invalid('建议必须为3至5项或明确追问')
        normalized=[]
        for option in options:
            if not isinstance(option,dict) or set(option)!={'text','reason'}: invalid('建议格式无效')
            normalized.append({'id':str(uuid.uuid4()),'text':text(option['text'],'建议',500),
                'reason':text(option['reason'],'理由',1000),'hypothesis':key=='mechanism'})
        if len({o['text'].casefold() for o in normalized})!=len(normalized): invalid('建议不得重复')
        result['fields'][key]={'options':normalized,'question':question}
    if not isinstance(raw['terms'],list) or len(raw['terms'])>100: invalid('模型术语过多')
    for index, term in enumerate(raw['terms']):
        if not isinstance(term,dict) or set(term)!={'term','parent_keyword','relation','reason'}: invalid('术语格式无效')
        if term['parent_keyword'] not in inputs['core_keywords'] or term['relation'] not in RELATIONS[1:]: invalid('术语关系无效')
        result['terms'].append({'id':str(uuid.uuid4()),'term':text(term['term'],'术语',200),
            'parent_keyword':term['parent_keyword'],'relation':term['relation'],'reason':text(term['reason'],'理由',1000),
            'source':'model','decision':'pending','replacement':'','variant_selected':False,
            'concept_id':None,'source_position':f'model:terms:{index}',
            'definition':'','graph_version':None,'license':None,
            'review_required':False,'conflict':False})
    return result

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recommend(request, project_id):
    if not isinstance(request.data,dict) or set(request.data)-{'expected_revision','regenerate_key'}: invalid('建议仅接受项目版本，不接受外部上下文')
    expected=request.data.get('expected_revision')
    if type(expected) is not int: invalid('缺少项目版本')
    cfg=config()
    with transaction.atomic():
        project=require_project(request.user,project_id,'write',True)
        require_revision(project.revision,expected)
        scope=project.constraints.order_by('-version').first()
        if scope.status!='draft': raise BusinessError('SCOPE_IMMUTABLE','请先创建范围草稿',status=409)
        inputs=inputs_for(project,scope)
        if any(inputs['research_fields'][key]['status'] not in ('answered','not_applicable','exploratory')
               or (inputs['research_fields'][key]['status']=='answered' and not inputs['research_fields'][key]['text'].strip()) for key in FIELDS):
            invalid('请先保存五项研究字段的明确状态')
        rows=graph_terms_for(project.id,scope.core_keywords)
        model_allowed=bool(project.external_processing_allowed and all(cfg.get(k) for k in ('url','model','key')))
        model_status='AVAILABLE' if model_allowed else ('DENIED' if not project.external_processing_allowed else 'UNCONFIGURED')
        policy_receipt=MutationRecord.objects.filter(project=project,action='scope.external_processing').order_by('-created_at','-id').values_list('id',flat=True).first()
        regeneration=text(request.data.get('regenerate_key',''),'显式重新生成标识',80,False)
        signature=fingerprint({'inputs':inputs,'scope_id':str(scope.id),'graph':rows,
            'model':cfg.get('model') if model_allowed else None,'url':cfg.get('url') if model_allowed else None,
            'model_status':model_status,'policy_receipt':str(policy_receipt),
            'schema':2,'regenerate_key':regeneration})
        receipt=SuggestionReceipt.objects.filter(project=project,fingerprint=signature).first()
        if receipt: return JsonResponse(payload(receipt))
        if model_allowed and SuggestionReceipt.objects.filter(
                project=project, result__model_status__in=('PENDING', 'AVAILABLE', 'FAILED')).count()>=int(cfg.get('quota',20)):
            model_allowed=False
            model_status='QUOTA_EXHAUSTED'
            signature=fingerprint({'inputs':inputs,'scope_id':str(scope.id),'graph':rows,
                'model':None,'url':None,'model_status':model_status,
                'policy_receipt':str(policy_receipt),'schema':2,'regenerate_key':regeneration})
            receipt=SuggestionReceipt.objects.filter(project=project,fingerprint=signature).first()
            if receipt: return JsonResponse(payload(receipt))
        receipt=SuggestionReceipt.objects.create(project=project,fingerprint=signature,scope_id=scope.id,
            revision=project.revision,inputs=inputs,
            result={'model_status':'PENDING' if model_allowed else model_status})
    result={'fields':{key:{'options':[],'question':''} for key in FIELDS},
            'terms':graph_candidates(rows), 'graph_status':'AVAILABLE' if rows else 'NO_COVERAGE',
            'model_status':model_status,'input_fingerprint':signature}
    try:
        if model_allowed:
            generated=validate_output(http_generate({**inputs,'graph_context':shareable_graph_context(rows)},cfg),inputs)
            result['fields']=generated['fields']
            for index, term in enumerate(generated['terms']):
                term['source_position']=f'model:{receipt.id}:terms:{index}'
            result['terms'].extend(generated['terms'])
            result['model']=cfg['model']
        status='ready'
    except Exception:
        result['model_status']='FAILED'
        status='ready'
    reconcile(result['terms'])
    result['groups']={keyword:[term for term in result['terms'] if term['parent_keyword']==keyword]
                      for keyword in inputs['core_keywords']}
    with transaction.atomic():
        project=require_project(request.user,project_id,'write',True)
        scope=project.constraints.order_by('-version').first()
        if (project.revision!=expected or scope.id!=receipt.scope_id or inputs_for(project,scope)!=inputs
                or graph_terms_for(project.id,scope.core_keywords)!=rows
                or (model_allowed and (not project.external_processing_allowed or config()!=cfg))):
            status='stale'; result={}
        receipt.status=status; receipt.result=result; receipt.save(update_fields=('status','result'))
    return JsonResponse(payload(receipt))

def payload(receipt):
    return {'id':str(receipt.id),'status':receipt.status,'fingerprint':receipt.fingerprint,
            'result':receipt.result,'manual_available':True}

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def external_processing(request, project_id):
    from .views import _mutate
    from .services import read_scope
    def save_policy(project, state, data):
        if type(data.get('allowed')) is not bool: invalid('请明确选择是否允许外部模型处理本项目基本信息')
        changed = project.external_processing_allowed != data['allowed']
        project.external_processing_allowed = data['allowed']
        project.save(update_fields=('external_processing_allowed',))
        if changed:
            scope = project.constraints.order_by('-version').first()
            if scope and scope.status == 'draft':
                for candidate in scope.details.get('candidates',[]):
                    if candidate.get('source') == 'model': candidate['review_required'] = True
                scope.save(update_fields=('details',))
        return read_scope(project)
    return _mutate(request, project_id, 'scope.external_processing', save_policy)

def verify_selections(project,scope,proposed):
    selected=[v for field in proposed.get('research_fields',{}).values() for v in field.get('selected',[])]
    sourced_terms=[t for t in proposed['candidates'] if t.get('source') in ('model','graph')]
    if not selected and not sourced_terms: return
    receipts=list(SuggestionReceipt.objects.filter(project=project,status='ready',scope_id=scope.id))
    previous={t['id']:t for t in scope.details.get('candidates',[]) if t.get('source') in ('model','graph')}
    for key,field in proposed['research_fields'].items():
        options={o['id'] for receipt in receipts if receipt.inputs==inputs_for(project,scope) for o in receipt.result.get('fields',{}).get(key,{}).get('options',[])}
        options.update(scope.details.get('research_fields',{}).get(key,{}).get('selected',[]))
        if not set(field['selected'])<=options: invalid('伪造建议选择')
    current_inputs=inputs_for(project,scope)
    originals={**previous,**{t['id']:t for receipt in receipts if receipt.inputs==current_inputs
                             for t in receipt.result.get('terms',[])}}
    for term in sourced_terms:
        original=originals.get(term['id'])
        fixed=('term','source','relation','parent_keyword','reason','concept_id','source_position','definition','graph_version','license','external_sharing_allowed')
        if not original or any(term.get(k)!=original.get(k) for k in fixed): invalid('伪造建议术语来源')
