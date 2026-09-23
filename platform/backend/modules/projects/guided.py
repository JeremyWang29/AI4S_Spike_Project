"""Structured scope contracts; legacy confirmed versions remain byte-for-byte intact."""
from copy import deepcopy
from datetime import date
from .validation import invalid, text, enumeration

FIELDS = ('object', 'mechanism', 'method', 'outcome', 'context')
RELATIONS = ('original', 'synonym', 'broader', 'narrower', 'related')
LANGUAGES = ('unlimited', 'zh', 'en', 'ja', 'de', 'fr', 'other')
LITERATURE_TYPES = ('unlimited', 'article', 'review', 'systematic_review', 'meta_analysis', 'preprint', 'conference', 'thesis', 'other')
PATENT_TYPES = ('unlimited', 'invention', 'utility_model', 'design', 'other')

def defaults():
    return {'schema_version': 2, 'research_fields': {key: {'status': 'unanswered', 'selected': [], 'text': ''} for key in FIELDS},
            'boundary': {'start': None, 'end': None, 'patent_date': 'publication', 'languages': ['unlimited'],
                         'literature_types': ['unlimited'], 'patent_types': ['unlimited']}}

def upgrade(details):
    result = deepcopy(details)
    if result.get('schema_version') == 2: return result
    result.update(defaults())
    answers = result.get('answers', {})
    for key in FIELDS:
        if answers.get(key): result['research_fields'][key].update(status='answered', text=answers[key])
    # Preserve unknown legacy boundaries for explicit review rather than narrow them.
    result['legacy_boundary'] = {key: answers.get(key, '') for key in ('years', 'languages', 'types')}
    result['legacy_boundary_reviewed'] = not any(result['legacy_boundary'].values())
    import re
    match = re.fullmatch(r'(\d{4})\s*[-—–至]\s*(\d{4})', answers.get('years', '').strip())
    if match:
        result['boundary'].update(start=match[1]+'-01-01', end=match[2]+'-12-31')
    for item in result.get('candidates', []):
        item.setdefault('relation', 'original'); item.setdefault('parent_keyword', item['term']); item.setdefault('variant_selected', False)
    return result

def validate(details, confirming=False):
    result = deepcopy(details)
    fields = result.get('research_fields')
    if not isinstance(fields, dict) or set(fields) != set(FIELDS): invalid('研究字段不完整')
    for key, field in fields.items():
        if not isinstance(field, dict) or set(field) - {'status','selected','text','review_required'}: invalid('研究字段格式无效')
        enumeration(field.get('status'), ('unanswered','answered','not_applicable','exploratory'), key)
        value = text(field.get('text',''), key, 2000, required=False)
        selected = field.get('selected', [])
        if not isinstance(selected,list) or len(selected)>20 or any(not isinstance(x,str) or len(x)>80 for x in selected): invalid('建议选择无效')
        if len(set(selected)) != len(selected): invalid('建议选择重复')
        if confirming and (field['status']=='unanswered' or field.get('review_required')): invalid('请回答研究字段或明确标记不适用／探索中，并复核变更')
        if field['status']=='answered' and not value: invalid('已回答字段需要填写内容')
        if field['status'] in ('not_applicable','exploratory') and selected: invalid('不适用或探索中不能同时选择建议')
        result['answers'][key] = value if field['status']=='answered' else ''
    boundary = result.get('boundary')
    if not isinstance(boundary,dict) or set(boundary) != set(defaults()['boundary']): invalid('边界字段无效')
    for key in ('start','end'):
        if boundary[key] is not None:
            try:
                if not isinstance(boundary[key],str) or date.fromisoformat(boundary[key]).isoformat()!=boundary[key]: raise ValueError()
            except (ValueError,TypeError): invalid('日期必须是有效的 YYYY-MM-DD')
    if boundary['start'] and boundary['end'] and boundary['start']>boundary['end']: invalid('起始日期不能晚于结束日期')
    if bool(boundary['start']) != bool(boundary['end']): invalid('自定义日期需要完整起止日期')
    enumeration(boundary['patent_date'], ('publication','application'), '专利日期')
    for key, allowed in (('languages',LANGUAGES),('literature_types',LITERATURE_TYPES),('patent_types',PATENT_TYPES)):
        values=boundary[key]
        if not isinstance(values,list) or not values or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values) or ('unlimited' in values and len(values)>1): invalid('不限与具体边界选项互斥')
    if confirming and result.get('legacy_boundary') and result.get('legacy_boundary_reviewed') is not True: invalid('请核对历史文字边界后明确确认映射')
    return result
