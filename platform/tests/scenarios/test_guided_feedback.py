"""The first real return is diagnostic feedback, never a Gold evaluation."""
from copy import deepcopy
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from modules.projects.models import Project, FeedbackObject, ResearchConstraint
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
        response = self.client.post(self.base + '/scope/suggestions', {
            'expected_revision': 1}, content_type='application/json')
        self.assertEqual(response.json()['status'], 'DENIED')
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
                'expected_revision': 2}, content_type='application/json')
            self.assertEqual(first.status_code, 200, first.content)
            self.assertEqual(first.json()['status'], 'ready')
            second = self.client.post(self.base + '/scope/suggestions', {
                'expected_revision': 2}, content_type='application/json')
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
