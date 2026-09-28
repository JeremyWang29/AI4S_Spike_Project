"""The first real return is diagnostic feedback, never a Gold evaluation."""
from copy import deepcopy
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from modules.projects.models import Project, FeedbackObject, ResearchConstraint
from modules.knowledge.services import import_graph_terms
from modules.knowledge.models import ConceptVersion
from modules.retrieval.services import list_plans


class GuidedFeedbackScenarios(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('guided-owner')
        self.client.force_login(self.user)
        response = self.client.post('/api/v1/projects', {
            'name': 'PSMB5 与食管鳞癌放疗抵抗', 'direction': '铁死亡和放疗反应',
            'core_keywords': ['PSMB5', '铁死亡'], 'expected_revision': 0,
        }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='create-guided')
        self.assertEqual(response.status_code, 201, response.content)
        self.project = Project.objects.get(pk=response.json()['id'])
        self.base = f'/api/v1/projects/{self.project.id}'

    def command(self, path, body, key):
        self.project.refresh_from_db()
        return self.client.post(self.base + path, {
            **body, 'expected_revision': self.project.revision,
        }, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)

    def confirm_manual_scope(self):
        details = deepcopy(self.client.get(self.base + '/scope').json()['scope']['details'])
        for field in details['research_fields'].values():
            field['status'] = 'exploratory'
        for term in details['candidates']:
            term['decision'] = 'accepted'
        details['semantic_review'] = '人工复核原始关键词；研究字段待探索。'
        response = self.command('/scope', {'action': 'confirm', 'details': details}, 'confirm-manual')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['scope']['status'], 'confirmed')

    def test_manual_scope_and_return_sample_criteria_history(self):
        self.confirm_manual_scope()
        records = [
            {'title': f'样本{i:02d} 食管鳞癌研究', 'abstract': '人工核查用题录',
             'doi': f'10.99999/example-{i:02d}', 'publication_date': '2026-01-15'}
            for i in range(24)
        ]
        first = self.command('/feedback', {'action': 'import', 'record_kind': 'literature',
            'platform': 'Web of Science', 'task_id': 'Q01', 'records': records}, 'import-one')
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()['added'], 24)
        duplicate = self.command('/feedback', {'action': 'import', 'record_kind': 'literature',
            'platform': 'Scopus', 'task_id': 'Q02', 'records': records[:2]}, 'import-two')
        self.assertEqual(duplicate.status_code, 200, duplicate.content)
        self.assertEqual(duplicate.json()['duplicates'], 2)
        self.assertEqual(FeedbackObject.objects.filter(project=self.project, kind='record').count(), 24)
        sampled = self.command('/feedback', {'action': 'sample', 'seed': 'fixed-42'}, 'sample-one')
        self.assertEqual(sampled.status_code, 200, sampled.content)
        sample = sampled.json()
        self.assertEqual(len(sample['record_ids']), 20)
        self.assertTrue(sample['not_gold'] and sample['not_precision'])
        next_batch = self.command('/feedback', {'action': 'sample', 'sample_id': sample['id']}, 'sample-two')
        self.assertEqual(next_batch.status_code, 200, next_batch.content)
        self.assertEqual(len(next_batch.json()['record_ids']), 4)
        self.assertFalse(set(sample['record_ids']) & set(next_batch.json()['record_ids']))
        record_id = sample['record_ids'][0]
        labelled = self.command('/feedback', {'action': 'label', 'sample_id': sample['id'],
            'record_id': record_id, 'label': 'relevant', 'reason_code': 'object',
            'reason': '符合研究对象'}, 'label-relevant')
        self.assertEqual(labelled.status_code, 200, labelled.content)
        criteria = {'include': ['食管鳞癌'], 'exclude': ['非食管研究'],
                    'exclude_terms': ['食管鳞癌']}
        impact = self.command('/feedback', {'action': 'preview', 'criteria': criteria}, 'preview-one')
        self.assertEqual(impact.status_code, 200, impact.content)
        self.assertEqual(impact.json()['affected_relevant_ids'], [record_id])
        stale = self.command('/feedback', {'action': 'confirm', 'criteria': {
            **criteria, 'exclude_terms': ['其他']}, 'impact_id': impact.json()['id'],
            'confirmed': True}, 'confirm-stale')
        self.assertEqual(stale.status_code, 409, stale.content)
        confirmed = self.command('/feedback', {'action': 'confirm', 'criteria': criteria,
            'impact_id': impact.json()['id'], 'confirmed': True}, 'confirm-criteria')
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual(confirmed.json()['scope_version'], 2)
        self.assertEqual(ResearchConstraint.objects.filter(project=self.project).count(), 2)
        self.assertEqual(FeedbackObject.objects.filter(project=self.project, kind='record').count(), 24)
        edited=self.command('/scope',{'action':'edit'},'edit-after-criteria')
        self.assertEqual(edited.status_code,200,edited.content)
        self.assertEqual(edited.json()['scope']['details']['criteria_id'],confirmed.json()['criteria']['id'])
        saved=self.command('/scope',{'action':'save','details':edited.json()['scope']['details']},'save-after-criteria')
        self.assertEqual(saved.status_code,200,saved.content)
        self.assertEqual(saved.json()['scope']['details']['criteria_id'],confirmed.json()['criteria']['id'])

    def test_stratified_sample_is_seeded_and_covers_each_task(self):
        self.confirm_manual_scope()
        for task in ('Q01','Q02'):
            rows = [{'title':f'{task} 样本{i:02d}', 'doi':f'10.99999/{task}-{i:02d}'} for i in range(15)]
            response=self.command('/feedback',{'action':'import','record_kind':'literature',
                'platform':'Web of Science','task_id':task,'records':rows},'import-'+task)
            self.assertEqual(response.status_code,200,response.content)
        first=self.command('/feedback',{'action':'sample','seed':'fixed-strata'},'sample-strata-one').json()
        second=self.command('/feedback',{'action':'sample','seed':'fixed-strata'},'sample-strata-repeat').json()
        self.assertEqual(first['record_ids'],second['record_ids'])
        items=self.client.get(self.base+'/feedback').json()['items']
        by_id={item['id']:item for item in items if item['kind']=='record'}
        strata=[by_id[ident]['provenance'][0]['task_id'] for ident in first['record_ids']]
        self.assertEqual(strata.count('Q01'),10)
        self.assertEqual(strata.count('Q02'),10)

    def test_confirmed_typed_terms_reach_the_plan_without_expanding_main(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        for term in details['candidates']: term['decision']='accepted'
        for term, parent, relation, variant in (
            ('ferroptosis','铁死亡','synonym',False),
            ('regulated cell death','铁死亡','broader',True),
            ('radiotherapy','PSMB5','related',False),
        ):
            details['candidates'].append({'id':str(uuid.uuid4()),'term':term,'source':'manual',
                'decision':'accepted','replacement':'','relation':relation,
                'parent_keyword':parent,'variant_selected':variant})
        details['semantic_review']='人工确认术语关系与独立变体。'
        response=self.command('/scope',{'action':'confirm','details':details},'confirm-typed')
        self.assertEqual(response.status_code,200,response.content)
        inputs=list_plans(self.user,self.project.id)['inputs']
        plan=self.client.post(self.base+'/search-plans',{'expected_revision':0,**inputs},
            content_type='application/json',HTTP_IDEMPOTENCY_KEY='typed-plan')
        self.assertEqual(plan.status_code,201,plan.content)
        blocks=plan.json()['blocks']
        ferro=[block for block in blocks if any(ref['term']=='铁死亡' for ref in block['term_refs'])]
        self.assertTrue(any(ref['term']=='ferroptosis' and ref['relation']=='synonym'
            for block in ferro for ref in block['term_refs']))
        self.assertTrue(any(block['block_key'].startswith('V') and block['label']=='regulated cell death'
            for block in blocks))
        self.assertTrue(any(block['block_key'].startswith('V') and block['label']=='radiotherapy'
            for block in blocks))


    @override_settings(AI4S_SCOPE_PROVIDER={
        'url': 'https://example.invalid/guided', 'model': 'test-model',
        'key': 'test-only', 'quota': 2, 'timeout': 1, 'max_bytes': 65536})
    def test_provider_denied_then_allowed_cached_and_validated(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-before-model').status_code,200)
        response = self.client.post(self.base + '/scope/suggestions', {
            'expected_revision': 2}, content_type='application/json')
        self.assertEqual(response.json()['result']['model_status'], 'DENIED')
        self.assertEqual(FeedbackObject.objects.count(), 0)
        allowed = self.command('/scope/external-processing', {'allowed': True}, 'allow-model')
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertTrue(allowed.json()['external_processing_allowed'])
        raw = {'fields': {name: {'options': [
            {'text': f'{name}-{i}', 'reason': '基于本项目主题的候选'} for i in range(3)
        ], 'question': ''} for name in ('object','mechanism','method','outcome','context')},
            'terms': [{'term': 'ferroptosis', 'parent_keyword': '铁死亡',
                       'relation': 'synonym', 'reason': '中英同义'}]}
        with patch('modules.projects.suggestions.http_generate', return_value=raw) as generate:
            first = self.client.post(self.base + '/scope/suggestions', {
                'expected_revision': 3}, content_type='application/json')
            self.assertEqual(first.status_code, 200, first.content)
            self.assertEqual(first.json()['status'], 'ready')
            second = self.client.post(self.base + '/scope/suggestions', {
                'expected_revision': 3}, content_type='application/json')
            self.assertEqual(second.json()['id'], first.json()['id'])
            self.assertEqual(generate.call_count, 1)
        self.assertTrue(first.json()['result']['fields']['mechanism']['options'][0]['hypothesis'])
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        choice=first.json()['result']['fields']['object']['options'][0]
        details['research_fields']['object'].update(status='answered',selected=[choice['id']],text=choice['text'])
        changed=self.command('/scope',{'action':'save','details':details,'direction':'调整后的研究方向'},'change-direction')
        self.assertEqual(changed.status_code,200,changed.content)
        self.assertEqual(changed.json()['scope']['details']['research_fields']['object']['selected'],[choice['id']])
        self.assertTrue(changed.json()['scope']['details']['research_fields']['object']['review_required'])
        reviewed=deepcopy(changed.json()['scope']['details'])
        reviewed['research_fields']['object']['review_required']=False
        saved=self.command('/scope',{'action':'save','details':reviewed},'review-direction')
        self.assertEqual(saved.status_code,200,saved.content)

    @override_settings(AI4S_SCOPE_PROVIDER={'url':'https://example.invalid/guided',
        'model':'test-model','key':'test-only'})
    def test_model_receives_saved_answered_fields_only(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        details['research_fields']['object'].update(status='answered',text='食管鳞癌细胞')
        details['research_fields']['mechanism'].update(status='not_applicable',text='未保存为事实')
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-mixed-fields').status_code,200)
        self.assertEqual(self.command('/scope/external-processing',{'allowed':True},'allow-mixed-fields').status_code,200)
        self.project.refresh_from_db()
        with patch('modules.projects.suggestions.http_generate',side_effect=RuntimeError('test provider')) as generate:
            response=self.client.post(self.base+'/scope/suggestions',
                {'expected_revision':self.project.revision},content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        fields=generate.call_args.args[0]['research_fields']
        self.assertEqual(fields['object'],{'status':'answered','text':'食管鳞癌细胞'})
        self.assertEqual(fields['mechanism'],{'status':'not_applicable','text':''})
        self.assertEqual(fields['method'],{'status':'exploratory','text':''})

    @override_settings(AI4S_SCOPE_PROVIDER={
        'url':'https://example.invalid/guided','model':'test-model',
        'key':'test-only','quota':1,'timeout':1,'max_bytes':65536})
    def test_failed_paid_attempt_consumes_quota(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-quota-scope').status_code,200)
        self.assertEqual(self.command('/scope/external-processing',{'allowed':True},'allow-quota-model').status_code,200)
        self.project.refresh_from_db()
        with patch('modules.projects.suggestions.http_generate',side_effect=RuntimeError('provider failed')) as generate:
            first=self.client.post(self.base+'/scope/suggestions',{'expected_revision':self.project.revision,
                'regenerate_key':'first'},content_type='application/json')
            import_graph_terms(self.project.id,'quota-v1','licensed',[
                {'concept_id':'quota:1','source_position':'synthetic:quota:1','term':'ferroptosis','parent_keyword':'铁死亡','relation':'synonym'}])
            second=self.client.post(self.base+'/scope/suggestions',{'expected_revision':self.project.revision,
                'regenerate_key':'second'},content_type='application/json')
        self.assertEqual(first.status_code,200,first.content)
        self.assertEqual(first.json()['result']['model_status'],'FAILED')
        self.assertEqual(second.json()['status'],'ready')
        self.assertEqual(second.json()['result']['model_status'],'QUOTA_EXHAUSTED')
        self.assertEqual([t['term'] for t in second.json()['result']['terms']],['ferroptosis'])
        self.assertEqual(generate.call_count,1)

    def test_graph_terms_are_project_scoped_and_stale_release_needs_review(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-five-states').status_code,200)
        other_id=uuid.uuid4()
        import_graph_terms(other_id,'private-v1','private-license',[
            {'concept_id':'other:1','source_position':'synthetic:other:1','term':'SECRET','parent_keyword':'铁死亡','relation':'synonym'}])
        import_graph_terms(self.project.id,'public-v1','project-license',[
            {'concept_id':'go:1','source_position':'synthetic:go:1','term':'ferroptosis','definition':'调控性细胞死亡',
             'parent_keyword':'铁死亡','relation':'synonym'}])
        response=self.client.post(self.base+'/scope/suggestions',{'expected_revision':2},content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'ready')
        self.assertEqual(response.json()['result']['model_status'],'DENIED')
        terms=response.json()['result']['terms']
        self.assertEqual([term['term'] for term in terms],['ferroptosis'])
        self.assertEqual(terms[0]['concept_id'],'go:1')
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for candidate in details['candidates']: candidate['decision']='accepted'
        tampered=deepcopy(details)
        tampered['candidates'].append({**terms[0],'license':'forged'})
        self.assertEqual(self.command('/scope',{'action':'save','details':tampered},'forge-graph').status_code,422)
        details['candidates'].append(terms[0])
        saved=self.command('/scope',{'action':'save','details':details},'save-graph')
        self.assertEqual(saved.status_code,200,saved.content)
        import_graph_terms(self.project.id,'public-v1','project-license',[])
        current=self.client.get(self.base+'/scope').json()['scope']['details']
        self.assertTrue(current['candidates'][-1]['review_required'])
        current['candidates'][-1]['decision']='accepted'
        current['semantic_review']='人工核查图谱失效项。'
        blocked=self.command('/scope',{'action':'confirm','details':current},'confirm-stale-graph')
        self.assertEqual(blocked.status_code,422)
        self.assertFalse(ConceptVersion.objects.filter(project_id=self.project.id).exists())

    def test_unchanged_graph_reimport_keeps_candidate_identity(self):
        rows=[{'concept_id':'go:1','source_position':'synthetic:go:1','term':'ferroptosis','parent_keyword':'铁死亡','relation':'synonym'}]
        import_graph_terms(self.project.id,'stable-v1','licensed',rows)
        from modules.knowledge.services import graph_terms_for
        first=graph_terms_for(self.project.id,['铁死亡'])
        import_graph_terms(self.project.id,'stable-v1','licensed',rows)
        second=graph_terms_for(self.project.id,['铁死亡'])
        self.assertEqual(first,second)

    def test_new_graph_version_deactivates_only_its_access_scope(self):
        from modules.knowledge.models import GraphTerm
        from modules.knowledge.services import graph_terms_for, graph_candidate_is_current
        other_id=uuid.uuid4()
        old=[{'concept_id':'go:old','source_position':'synthetic:old','term':'old term',
              'parent_keyword':'铁死亡','relation':'synonym'}]
        new=[{'concept_id':'go:new','source_position':'synthetic:new','term':'new term',
              'parent_keyword':'铁死亡','relation':'synonym'}]
        import_graph_terms(self.project.id,'v1','licensed',old)
        import_graph_terms(other_id,'v1','licensed',old)
        old_candidate=graph_terms_for(self.project.id,['铁死亡'])[0]
        import_graph_terms(self.project.id,'v2','licensed',new)
        current=graph_terms_for(self.project.id,['铁死亡'])
        self.assertEqual([row['term'] for row in current],['new term'])
        self.assertFalse(graph_candidate_is_current(old_candidate,current))
        self.assertFalse(GraphTerm.objects.get(project_id=self.project.id,graph_version='v1').active)
        self.assertTrue(GraphTerm.objects.get(project_id=other_id,graph_version='v1').active)

    @override_settings(AI4S_SCOPE_PROVIDER={'url':'https://example.invalid/guided','model':'test-model','key':'test-only'})
    def test_pending_sourced_terms_require_review_after_saved_scope_changes(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-pending-base').status_code,200)
        self.assertEqual(self.command('/scope/external-processing',{'allowed':True},'allow-pending-model').status_code,200)
        import_graph_terms(self.project.id,'pending-v1','licensed',[
            {'concept_id':'g1','source_position':'synthetic:g1','term':'graph term',
             'parent_keyword':'铁死亡','relation':'synonym'}])
        raw={'fields':{name:{'options':[],'question':'待追问'} for name in ('object','mechanism','method','outcome','context')},
             'terms':[{'term':'model term','parent_keyword':'铁死亡','relation':'related','reason':'待核查'}]}
        with patch('modules.projects.suggestions.http_generate',return_value=raw):
            result=self.client.post(self.base+'/scope/suggestions',{'expected_revision':3},content_type='application/json')
        self.assertEqual(result.status_code,200,result.content)
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        details['candidates'].extend(result.json()['result']['terms'])
        saved=self.command('/scope',{'action':'save','details':details},'save-pending-terms')
        self.assertEqual(saved.status_code,200,saved.content)
        changed=deepcopy(saved.json()['scope']['details'])
        changed['research_fields']['object'].update(status='answered',text='新研究对象')
        answer_save=self.command('/scope',{'action':'save','details':changed},'change-answer-pending')
        self.assertEqual(answer_save.status_code,200,answer_save.content)
        reviewed_details=answer_save.json()['scope']['details']
        candidates=reviewed_details['candidates']
        self.assertTrue(all(item['review_required'] for item in candidates if item['source'] in ('graph','model')))
        for item in candidates:
            if item['source'] in ('graph','model'): item['review_required']=False
        reviewed=self.command('/scope',{'action':'save','details':reviewed_details},'review-pending')
        self.assertEqual(reviewed.status_code,200,reviewed.content)
        keyword_save=self.command('/scope',{'action':'save','details':reviewed.json()['scope']['details'],
            'core_keywords':['PSMB5','铁死亡','radiotherapy']},'change-keyword-pending')
        self.assertEqual(keyword_save.status_code,200,keyword_save.content)
        self.assertTrue(all(item['review_required'] for item in keyword_save.json()['scope']['details']['candidates']
                            if item['source'] in ('graph','model')))

    def test_graph_import_requires_traceable_source_and_caps_one_keyword(self):
        from config.errors import BusinessError
        with self.assertRaises(BusinessError):
            import_graph_terms(None,'platform-v1','restricted',[])
        with self.assertRaises(BusinessError):
            import_graph_terms(self.project.id,'missing-source','licensed',[
                {'concept_id':'c1','term':'ferroptosis','parent_keyword':'铁死亡','relation':'synonym'}])
        rows=[{'concept_id':f'c{i}','source_position':f'synthetic:c{i}',
            'term':f'term {i}','parent_keyword':'铁死亡','relation':'related'} for i in range(101)]
        with self.assertRaises(BusinessError):
            import_graph_terms(self.project.id,'too-many','licensed',rows)

    @override_settings(AI4S_SCOPE_PROVIDER={'url':'https://example.invalid/guided','model':'test-model','key':'test-only'})
    def test_graph_model_relation_conflict_requires_human_review(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-conflict-scope').status_code,200)
        self.assertEqual(self.command('/scope/external-processing',{'allowed':True},'allow-conflict-model').status_code,200)
        import_graph_terms(self.project.id,'graph-v1','licensed',[
            {'concept_id':'c1','source_position':'synthetic:c1','term':'ferroptosis','parent_keyword':'铁死亡','relation':'related'}])
        raw={'fields':{name:{'options':[], 'question':'待追问'} for name in ('object','mechanism','method','outcome','context')},
             'terms':[{'term':'ferroptosis','parent_keyword':'铁死亡','relation':'synonym','reason':'模型推测'}]}
        with patch('modules.projects.suggestions.http_generate',return_value=raw) as generate:
            response=self.client.post(self.base+'/scope/suggestions',{'expected_revision':3},content_type='application/json')
        self.assertEqual(generate.call_args.args[0]['graph_context'],[])
        self.assertEqual(response.status_code,200,response.content)
        candidates=response.json()['result']['terms']
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(item['conflict'] for item in candidates))
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for item in details['candidates']: item['decision']='accepted'
        details['candidates'].extend(candidates)
        details['candidates'][-2]['decision']='accepted'
        details['candidates'][-1]['decision']='rejected'
        details['semantic_review']='核对来源关系，保留图谱相关词。'
        blocked=self.command('/scope',{'action':'confirm','details':details},'confirm-unreviewed-conflict')
        self.assertEqual(blocked.status_code,422)
        details['candidates'][-2]['relation_reviewed']=True
        details['candidates'][-2]['relation_review_reason']='核对图谱概念定位和模型推测后选相关关系。'
        confirmed=self.command('/scope',{'action':'confirm','details':details},'confirm-reviewed-conflict')
        self.assertEqual(confirmed.status_code,200,confirmed.content)
        concept=ConceptVersion.objects.get(project_id=self.project.id)
        self.assertTrue(any(term['term']=='ferroptosis' and term['relation']=='related' for term in concept.content['typed_terms']))

    def test_keyword_revision_creates_new_original_and_retains_old_decision(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        changed=self.command('/scope',{'action':'save','details':details,
            'core_keywords':['PSMB5','radiotherapy']},'change-original-keyword')
        self.assertEqual(changed.status_code,200,changed.content)
        scope=changed.json()['scope']
        self.assertEqual(scope['core_keywords'],['PSMB5','radiotherapy'])
        old=next(c for c in scope['details']['candidates'] if c['term']=='铁死亡')
        new=next(c for c in scope['details']['candidates'] if c['term']=='radiotherapy')
        self.assertTrue(old['review_required'])
        self.assertEqual(new['source'],'project_keyword')
        self.assertEqual(new['parent_keyword'],'radiotherapy')
        for candidate in scope['details']['candidates']:
            candidate['decision']='rejected' if candidate['term']=='铁死亡' else 'accepted'
        scope['details']['semantic_review']='已核对关键词变更并弃用旧词。'
        confirmed=self.command('/scope',{'action':'confirm','details':scope['details']},'confirm-keyword-change')
        self.assertEqual(confirmed.status_code,200,confirmed.content)
        self.assertEqual(ConceptVersion.objects.get(project_id=self.project.id).content['terms'],['PSMB5','radiotherapy'])

    def test_current_original_keyword_cannot_be_rejected_at_confirmation(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        for candidate in details['candidates']:
            candidate['decision']='rejected' if candidate['term']=='PSMB5' else 'accepted'
        details['semantic_review']='人工核查关键词。'
        response=self.command('/scope',{'action':'confirm','details':details},'reject-current-keyword')
        self.assertEqual(response.status_code,422,response.content)
        self.assertFalse(ConceptVersion.objects.filter(project_id=self.project.id).exists())

    def test_new_manual_candidate_cannot_be_an_original_keyword(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        details['candidates'].append({'id':str(uuid.uuid4()),'term':'new primary term',
            'source':'manual','decision':'pending','replacement':'','relation':'original',
            'parent_keyword':'PSMB5','variant_selected':False})
        response=self.command('/scope',{'action':'save','details':details},'manual-original')
        self.assertEqual(response.status_code,422,response.content)

    @override_settings(AI4S_SCOPE_PROVIDER={'url':'https://example.invalid/guided','model':'test-model','key':'test-only'})
    def test_only_shareable_graph_fragments_reach_model(self):
        details=deepcopy(self.client.get(self.base+'/scope').json()['scope']['details'])
        for field in details['research_fields'].values(): field['status']='exploratory'
        self.assertEqual(self.command('/scope',{'action':'save','details':details},'save-share-scope').status_code,200)
        self.assertEqual(self.command('/scope/external-processing',{'allowed':True},'allow-share-model').status_code,200)
        import_graph_terms(self.project.id,'v1','licensed',[
            {'concept_id':'private','source_position':'synthetic:private','term':'hidden','definition':'secret','parent_keyword':'PSMB5','relation':'related'},
            {'concept_id':'shareable','source_position':'synthetic:shareable','term':'public','parent_keyword':'铁死亡','relation':'synonym'}],
            external_sharing_allowed=False)
        from modules.knowledge.models import GraphTerm
        GraphTerm.objects.filter(project_id=self.project.id,concept_id='shareable').update(external_sharing_allowed=True)
        raw={'fields':{name:{'options':[], 'question':'待追问'} for name in ('object','mechanism','method','outcome','context')},'terms':[]}
        with patch('modules.projects.suggestions.http_generate',return_value=raw) as generate:
            response=self.client.post(self.base+'/scope/suggestions',{'expected_revision':3},content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        context=generate.call_args.args[0]['graph_context']
        self.assertEqual([item['concept_id'] for item in context],['shareable'])
        self.assertNotIn('secret',str(context))
