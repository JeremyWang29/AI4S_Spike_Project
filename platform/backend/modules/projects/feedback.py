"""Actual project returns and diagnostic feedback, never official Gold."""
import csv
import io
import re
import uuid
from copy import deepcopy
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from config.errors import BusinessError
from modules.core import fingerprint
from .models import FeedbackObject, ResearchConstraint
from .validation import invalid, text, enumeration
from . import services

def objects(project, kind): return FeedbackObject.objects.filter(project=project,kind=kind).order_by('created_at','id')
def put(project,kind,content,identity=None):
    return FeedbackObject.objects.create(project=project,kind=kind,identity=identity or str(uuid.uuid4()),content=content)
def dto(obj): return {'id':str(obj.id),'kind':obj.kind,**obj.content}
def get(project,kind,ident):
    try: obj=objects(project,kind).filter(id=uuid.UUID(str(ident))).first()
    except (ValueError,TypeError,AttributeError): obj=None
    if not obj: raise BusinessError('FEEDBACK_NOT_FOUND','当前项目中没有该回传对象',status=404)
    return obj
def read(project):
    return {'project_id':str(project.id),'project_revision':project.revision,
            'items':[dto(o) for o in FeedbackObject.objects.filter(project=project).order_by('created_at','id')],
            'diagnostic_only':True,'official_evaluation':'DISABLED'}
def scope_now(project):
    scope=project.constraints.order_by('-version').first()
    if not scope or scope.status!='confirmed': raise BusinessError('SCOPE_CONFIRMATION_REQUIRED','请先确认范围',status=409)
    return scope
def canonical_identifier(key,value):
    value=value.strip().casefold()
    if key=='doi': value=re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)','',value)
    if key=='patent_number': value=re.sub(r'[^a-z0-9]','',value)
    return value
def import_records(project,data,scope):
    kind=enumeration(data.get('record_kind'),('literature','patent'),'记录类型')
    platform=text(data.get('platform'),'平台',100)
    task_id=text(data.get('task_id'),'任务来源',160)
    raw=data.get('records')
    if 'csv' in data:
        value=text(data['csv'],'CSV',10000)
        try: raw=list(csv.DictReader(io.StringIO(value)))
        except csv.Error: invalid('CSV格式错误')
    if not isinstance(raw,list) or not 1<=len(raw)<=200: invalid('每批需要1至200条真实记录')
    clean=[]
    for row in raw:
        if not isinstance(row,dict) or set(row)-{'title','abstract','doi','pmid','patent_number','publication_date','application_date'}: invalid('回传字段无效；禁止全文或Gold输入')
        title=text(row.get('title'),'标题',2000)
        abstract=text(row.get('abstract',''),'摘要',8000,False)
        ids={key:canonical_identifier(key,text(row.get(key,''),key,200,False)) for key in ('doi','pmid','patent_number')}
        from datetime import date
        dates={}
        for key in ('publication_date','application_date'):
            value=row.get(key,'') or ''
            if value:
                try:
                    if date.fromisoformat(value).isoformat()!=value: raise ValueError()
                except (ValueError,TypeError): invalid('记录日期须为完整日期或留空；未知精度不可伪造')
            dates[key]=value
        clean.append({'record_kind':kind,'title':title,'abstract':abstract,'identifiers':ids,**dates})
    imported=put(project,'import',{'raw_records':deepcopy(raw),'platform':platform,'task_id':task_id,'scope_id':str(scope.id),'count':len(raw)})
    added=0
    for row in clean:
        aliases={k+':'+v for k,v in row['identifiers'].items() if v}
        title_key=re.sub(r'\W+','',row['title'].casefold())
        existing=None
        for candidate in objects(project,'record'):
            c=candidate.content
            other={k+':'+v for k,v in c['identifiers'].items() if v}
            conflicting=any(c['identifiers'].get(k) and v and c['identifiers'][k]!=v for k,v in row['identifiers'].items())
            if c['record_kind']==kind and not conflicting and ((aliases & other) or re.sub(r'\W+','',c['title'].casefold())==title_key): existing=candidate; break
        provenance={'import_id':str(imported.id),'platform':platform,'task_id':task_id,'scope_id':str(scope.id)}
        if existing:
            existing.content['provenance'].append(provenance)
            existing.content.setdefault('source_variants', []).append({'title':row['title'],'abstract':row['abstract'],
                'identifiers':deepcopy(row['identifiers']),'publication_date':row['publication_date'],
                'application_date':row['application_date'],'provenance':provenance})
            existing.content['identifiers'].update({k:v for k,v in row['identifiers'].items() if v})
            existing.save(update_fields=('content',))
        else:
            if objects(project,'record').count()>=2000: invalid('项目最多2000条独立记录，请缩小首轮回传范围')
            put(project,'record',{**row,'provenance':[provenance],
                'source_variants':[{'title':row['title'],'abstract':row['abstract'],
                    'identifiers':deepcopy(row['identifiers']),'publication_date':row['publication_date'],
                    'application_date':row['application_date'],'provenance':provenance}]},
                fingerprint({'kind':kind,'title':title_key,'ids':row['identifiers']})); added+=1
    return {'import_id':str(imported.id),'added':added,'duplicates':len(clean)-added}
def sample(project,data,scope):
    if data.get('sample_id'):
        previous=get(project,'sample',data['sample_id'])
        if previous.content['scope_id']!=str(scope.id): invalid('样本范围已失效')
        population=previous.content['population']; seed=previous.content['seed']; root=previous.content['root']
        snapshot=previous.content['population_snapshot']
        used={i for o in objects(project,'sample') if o.content['root']==root for i in o.content['record_ids']}
    else:
        population=[str(o.id) for o in objects(project,'record')]; seed=text(data.get('seed','diagnostic20-v1'),'随机种子',100)
        root=str(uuid.uuid4()); used=set();snapshot={str(o.id):deepcopy(o.content) for o in objects(project,'record')}
    strata={}
    for ident in population:
        if ident in used: continue
        record=snapshot[ident]
        stratum=record['record_kind']+':'+record['provenance'][0]['platform']+':'+record['provenance'][0]['task_id']
        strata.setdefault(stratum,[]).append(ident)
    for bucket in strata.values(): bucket.sort(key=lambda ident:fingerprint({'seed':seed,'record':ident}))
    selected=[]
    while len(selected)<20 and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(selected)<20: selected.append(strata[key].pop(0))
    if not selected: invalid('没有尚未抽取的记录')
    obj=put(project,'sample',{'scope_id':str(scope.id),'seed':seed,'root':root,'population':population,
        'population_fingerprint':fingerprint(snapshot),'population_snapshot':snapshot,'record_ids':selected,'shortfall':20-len(selected),
        'diagnostic_only':True,'not_gold':True,'not_precision':True})
    return dto(obj)
def labels_for(project,scope):
    return [o for o in objects(project,'label') if o.content['scope_id']==str(scope.id) and o.content.get('applicability','current')=='current']
def criteria_input(data):
    criteria=data.get('criteria')
    if not isinstance(criteria,dict) or set(criteria)!={'include','exclude','exclude_terms'}: invalid('纳排条件格式无效')
    for key in criteria:
        values=criteria[key]
        if not isinstance(values,list) or len(values)>100: invalid('纳排条件必须为列表')
        for value in values: text(value,'纳排条件',1000)
    if not criteria['include'] and not criteria['exclude']: invalid('请填写至少一条纳入或排除条件')
    if {s.strip().casefold() for s in criteria['include']} & {s.strip().casefold() for s in criteria['exclude']}: invalid('纳入与排除条件冲突')
    return criteria
def impact(project,scope,criteria):
    labels=labels_for(project,scope)
    affected=[]
    for label in labels:
        record=get(project,'record',label.content['record_id'])
        corpus=(record.content['title']+' '+record.content['abstract']).casefold()
        if label.content['label']=='relevant' and any(term.casefold() in corpus for term in criteria['exclude_terms']): affected.append(str(record.id))
    facts={'scope_id':str(scope.id),'criteria':criteria,'labels':[dto(o) for o in labels],
           'population':[dto(o) for o in objects(project,'record')]}
    return {'fingerprint':fingerprint(facts),'affected_relevant_ids':sorted(set(affected)),
            'scope_id':str(scope.id),'criteria':criteria,'text_rules_require_human_application':True}
def command(project,state,data):
    action=enumeration(data.get('action'),('import','sample','label','propose','preview','confirm'),'反馈操作')
    scope=scope_now(project)
    if action=='import': return import_records(project,data,scope)
    if action=='sample': return sample(project,data,scope)
    if action=='label':
        sampled=get(project,'sample',data.get('sample_id'))
        record=get(project,'record',data.get('record_id'))
        if sampled.content['scope_id']!=str(scope.id) or str(record.id) not in sampled.content['record_ids']: invalid('标注记录不属于当前范围样本')
        label=enumeration(data.get('label'),('relevant','irrelevant','uncertain'),'相关性')
        reason=text(data.get('reason',''),'理由',2000,False)
        if label=='irrelevant' and not reason: invalid('不相关判断需要说明理由')
        reason_code=enumeration(data.get('reason_code','other'),('object','mechanism','method','outcome','context','date','type','language','insufficient','other'),'理由类别')
        key=fingerprint({'scope':str(scope.id),'record':str(record.id)})
        previous=objects(project,'label').filter(identity=key).first()
        history=deepcopy(previous.content.get('history',[])) if previous else []
        if previous: history.append({k:v for k,v in previous.content.items() if k!='history'})
        obj,_=FeedbackObject.objects.update_or_create(project=project,kind='label',identity=key,defaults={'content':{
            'record_id':str(record.id),'sample_id':str(sampled.id),'scope_id':str(scope.id),'label':label,
            'reason':reason,'reason_code':reason_code,'applicability':'current','history':history}})
        return dto(obj)
    if action=='propose':
        labels=labels_for(project,scope)
        if not labels: invalid('请先对真实回传记录标注')
        criteria={'include':[],'exclude':[],'exclude_terms':[]}; unresolved=[]
        for label in labels:
            c=label.content
            if c['label']=='uncertain': continue
            key='include' if c['label']=='relevant' else 'exclude'
            if not c['reason']:
                unresolved.append({'record_id':c['record_id'],'reason_code':c['reason_code']})
                continue
            reason=c['reason']
            if reason not in criteria[key]: criteria[key].append(reason)
        return dto(put(project,'proposal',{'criteria':criteria,'unresolved_labels':unresolved,'label_ids':[str(o.id) for o in labels],
            'scope_id':str(scope.id),'source':'human_return_feedback','status':'requires_edit_and_confirmation'}))
    criteria=criteria_input(data)
    current=impact(project,scope,criteria)
    if action=='preview': return dto(put(project,'impact',current))
    preview=get(project,'impact',data.get('impact_id'))
    if preview.content!=current: raise BusinessError('STALE_CRITERIA_IMPACT','纳排条件、标注或总体已变化，请重新预览影响',status=409)
    if data.get('confirmed') is not True: invalid('需要明确确认新纳排版本')
    criteria_version=objects(project,'criteria').count()+1
    obj=put(project,'criteria',{**current,'version':criteria_version,'status':'confirmed','confirmed_at':timezone.now().isoformat()})
    details=deepcopy(scope.details); details['criteria_id']=str(obj.id)
    details['answers']['include']='\n'.join(criteria['include']); details['answers']['exclude']='\n'.join(criteria['exclude'])
    successor=ResearchConstraint.objects.create(project=project,version=scope.version+1,status='confirmed',
        direction=scope.direction,core_keywords=deepcopy(scope.core_keywords),details=details,confirmed_at=timezone.now())
    services.create_dependencies(project,successor); services.invalidate_dependents(project,scope.id)
    from modules.knowledge.services import freeze_concepts
    from .models import DependencyEdge
    concept=freeze_concepts(project.id,successor)
    DependencyEdge.objects.create(project=project,source_id=successor.id,target_id=concept.id,target_kind='concept')
    for label in labels_for(project,scope):
        label.content['applicability']='needs_revalidation'; label.save(update_fields=('content',))
    for key in ('evaluations','annotations','gold'):
        for item in state.data.get(key,[]):
            if isinstance(item,dict): item.update(applicability='needs_revalidation',qualified=False)
    project.required_dependencies={key:'needs_revalidation' for key in project.required_dependencies}
    project.save(update_fields=('required_dependencies',))
    return {'criteria':dto(obj),'scope_version':successor.version,'affected_relevant_ids':current['affected_relevant_ids']}

@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def endpoint(request,project_id):
    from .views import _mutate, _project
    if request.method=='GET': return JsonResponse(read(_project(request.user,project_id)))
    if not isinstance(request.data,dict): invalid('反馈命令必须为对象')
    return _mutate(request,project_id,'feedback.'+str(request.data.get('action','')),command)
