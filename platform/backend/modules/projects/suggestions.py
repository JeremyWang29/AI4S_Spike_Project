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
from .models import SuggestionReceipt
from .guided import FIELDS, RELATIONS
from .validation import invalid, text, bounded_json

def config():
    return getattr(settings, 'AI4S_SCOPE_PROVIDER', {})

def inputs_for(project, scope):
    confirmed = project.constraints.filter(status='confirmed').order_by('-version').first()
    return {'title': project.name, 'direction': scope.direction, 'core_keywords': scope.core_keywords,
            'confirmed_answers': confirmed.details.get('answers', {}) if confirmed else {}}

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
    for term in raw['terms']:
        if not isinstance(term,dict) or set(term)!={'term','parent_keyword','relation','reason'}: invalid('术语格式无效')
        if term['parent_keyword'] not in inputs['core_keywords'] or term['relation'] not in RELATIONS[1:]: invalid('术语关系无效')
        result['terms'].append({'id':str(uuid.uuid4()),'term':text(term['term'],'术语',200),
            'parent_keyword':term['parent_keyword'],'relation':term['relation'],'reason':text(term['reason'],'理由',1000),
            'source':'model','decision':'pending','replacement':'','variant_selected':False})
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
        if not project.external_processing_allowed: return JsonResponse({'status':'DENIED','manual_available':True})
        if not all(cfg.get(k) for k in ('url','model','key')): return JsonResponse({'status':'UNCONFIGURED','manual_available':True})
        if scope.status!='draft': raise BusinessError('SCOPE_IMMUTABLE','请先创建范围草稿',status=409)
        inputs=inputs_for(project,scope)
        regeneration=text(request.data.get('regenerate_key',''),'显式重新生成标识',80,False)
        signature=fingerprint({'inputs':inputs,'scope_id':str(scope.id),'model':cfg['model'],'url':cfg['url'],'schema':1,'regenerate_key':regeneration})
        receipt=SuggestionReceipt.objects.filter(project=project,fingerprint=signature).first()
        if receipt: return JsonResponse(payload(receipt))
        if SuggestionReceipt.objects.filter(project=project).count()>=int(cfg.get('quota',20)):
            return JsonResponse({'status':'QUOTA_EXHAUSTED','manual_available':True})
        receipt=SuggestionReceipt.objects.create(project=project,fingerprint=signature,scope_id=scope.id,
            revision=project.revision,inputs=inputs)
    try:
        result=validate_output(http_generate(inputs,cfg),inputs)
        result['model']=cfg['model']; result['input_fingerprint']=signature
        result['source']='current_project_basics_and_confirmed_answers'
        status='ready'
    except Exception:
        result={}; status='failed'
    with transaction.atomic():
        project=require_project(request.user,project_id,'write',True)
        scope=project.constraints.order_by('-version').first()
        if (not project.external_processing_allowed or project.revision!=expected or scope.id!=receipt.scope_id
                or inputs_for(project,scope)!=inputs or config()!=cfg): status='stale'; result={}
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
        project.external_processing_allowed = data['allowed']
        project.save(update_fields=('external_processing_allowed',))
        return read_scope(project)
    return _mutate(request, project_id, 'scope.external_processing', save_policy)

def verify_selections(project,scope,proposed):
    selected=[v for field in proposed.get('research_fields',{}).values() for v in field.get('selected',[])]
    model_terms=[t for t in proposed['candidates'] if t.get('source')=='model']
    if not selected and not model_terms: return
    receipts=list(SuggestionReceipt.objects.filter(project=project,status='ready',scope_id=scope.id))
    previous={t['id']:t for t in scope.details.get('candidates',[]) if t.get('source')=='model'}
    for key,field in proposed['research_fields'].items():
        options={o['id'] for receipt in receipts if receipt.inputs==inputs_for(project,scope) for o in receipt.result['fields'][key]['options']}
        options.update(scope.details.get('research_fields',{}).get(key,{}).get('selected',[]))
        if not set(field['selected'])<=options: invalid('伪造建议选择')
    originals={**previous,**{t['id']:t for receipt in receipts for t in receipt.result['terms']}}
    for term in model_terms:
        original=originals.get(term['id'])
        if not original or any(term.get(k)!=original[k] for k in ('term','source','relation','parent_keyword','reason')): invalid('伪造模型术语来源')
