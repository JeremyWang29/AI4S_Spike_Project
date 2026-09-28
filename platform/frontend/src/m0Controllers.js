import {ref} from 'vue'
import {creationAttempt,latestRequest} from './workflow.js'
const clone=value=>JSON.parse(JSON.stringify(value))

export function scopeController({api,project,emit,drafts={}}){
  const data=ref(null),details=ref(null),busy=ref(false),error=ref(null),dirty=ref(false),saved=ref(false),suggestions=ref(null)
  const gate=latestRequest()
  let attempt=null,active=true
  const current=ticket=>active&&gate.current(ticket,project().id)
  function changed(){dirty.value=true;saved.value=false}
  function remember(){if(data.value&&dirty.value) drafts[project().id]={details:clone(details.value),data:clone(data.value),attempt}}
  function apply(result){data.value=result;details.value=clone(result.scope.details);suggestions.value=null;dirty.value=false;saved.value=true;attempt=null;delete drafts[project().id];emit('saved',result)}
  async function load(restore=false){
    const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{
      const result=await api.scope(id);if(!current(ticket))return
      const draft=restore&&drafts[id]
      if(draft){data.value=clone(draft.data);details.value=clone(draft.details);attempt=draft.attempt;changed();if(result.project_revision!==data.value.project_revision)error.value={code:'REVISION_CONFLICT',message:'服务器版本已变化；本地未保存内容已保留',recovery:'核对并合并后再保存'}}
      else apply(result)
    }catch(e){if(current(ticket))error.value=e}finally{if(current(ticket))busy.value=false}
  }
  async function command(action){
    if(busy.value||!data.value)return
    const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{
      const input={action,expected_revision:data.value.project_revision,...(action==='edit'?{}:{details:clone(details.value),...(data.value.scope.core_keywords?{core_keywords:clone(data.value.scope.core_keywords)}:{})})}
      attempt=creationAttempt(attempt,input)
      const result=await api.scopeCommand(id,input,attempt.key)
      if(current(ticket))apply(result)
    }catch(e){if(current(ticket)){error.value=e;saved.value=false}}finally{if(current(ticket))busy.value=false}
  }
  async function recommend(regenerate=false){
    if(busy.value||!data.value||!api.suggestions||dirty.value||data.value.scope?.status!=='draft'){
      if(dirty.value)error.value={code:'UNSAVED_SCOPE',message:'请先保存五项研究内容，再生成候选词'}
      return
    }
    const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{
      const result=await api.suggestions(id,{expected_revision:data.value.project_revision,...(regenerate?{regenerate_key:crypto.randomUUID()}:{})})
      if(!current(ticket))return
      suggestions.value=result
      if(result.status==='ready'){
        details.value.suggestion_receipt=result.id
        for(const term of result.result.terms)if(!details.value.candidates.some(t=>t.id===term.id))details.value.candidates.push(clone(term))
        const surfaces=new Map()
        for(const term of details.value.candidates){
          const key=`${term.parent_keyword?.toLocaleLowerCase()}|${term.term?.toLocaleLowerCase()}`
          const group=surfaces.get(key)||[];group.push(term);surfaces.set(key,group)
        }
        for(const group of surfaces.values()){
          const relations=new Set(group.map(term=>term.relation))
          const graphConcepts=new Set(group.filter(term=>term.source==='graph').map(term=>`${term.concept_id}|${term.relation}`))
          if(relations.size>1||graphConcepts.size>1)for(const term of group)term.conflict=true
        }
        changed()
      }
    }catch(e){if(current(ticket))error.value=e}finally{if(current(ticket))busy.value=false}
  }
  async function setExternal(allowed){
    if(busy.value||!data.value||dirty.value){
      if(dirty.value)error.value={code:'UNSAVED_SCOPE',message:'请先保存范围修改，再更改外部处理许可'}
      return
    }
    const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{
      const result=await api.externalProcessing(id,{allowed,expected_revision:data.value.project_revision},crypto.randomUUID())
      if(!current(ticket))return
      data.value={...data.value,scope:result.scope,external_processing_allowed:result.external_processing_allowed,providers:result.providers,project_revision:result.project_revision}
      details.value=clone(result.scope.details);suggestions.value=null
      emit('saved',result)
    }catch(e){if(current(ticket))error.value=e}finally{if(current(ticket))busy.value=false}
  }
  function selectOption(field,option,selected){
    const value=details.value.research_fields[field]
    value.selected=selected?[...new Set([...value.selected,option.id])]:value.selected.filter(id=>id!==option.id)
    if(selected){value.status='answered';value.text=[value.text,option.text].filter(Boolean).join('；');value.review_required=false}
    else value.review_required=true
    changed()
  }
  function syncRevision(revision){if(data.value&&!busy.value&&!error.value&&revision>data.value.project_revision)data.value.project_revision=revision}
  function dispose(){remember();active=false;gate.begin(null)}
  return {data,details,busy,error,dirty,saved,suggestions,changed,load,command,recommend,setExternal,selectOption,syncRevision,dispose}
}

export function feedbackController({api,project,emit}){
  const data=ref(null),busy=ref(false),error=ref(null),result=ref(null)
  const gate=latestRequest();let active=true,attempt=null
  const current=ticket=>active&&gate.current(ticket,project().id)
  async function load(){const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{const value=await api.feedback(id);if(current(ticket))data.value=value}catch(e){if(current(ticket))error.value=e}finally{if(current(ticket))busy.value=false}}
  async function command(body){
    if(busy.value||!data.value)return
    const id=project().id,ticket=gate.begin(id);busy.value=true;error.value=null
    try{
      const input={...clone(body),expected_revision:data.value.project_revision};attempt=creationAttempt(attempt,input)
      const value=await api.feedbackCommand(id,input,attempt.key)
      if(!current(ticket))return
      result.value=value;attempt=null
      const scope=await api.scope(id);if(!current(ticket))return
      emit('saved',scope)
      const fresh=await api.feedback(id);if(current(ticket))data.value=fresh
    }catch(e){if(current(ticket))error.value=e}finally{if(current(ticket))busy.value=false}
  }
  return {data,busy,error,result,load,command,dispose(){active=false;gate.begin(null)}}
}

export function actionController({projectId,emit}){
  const busy=ref(false),error=ref(null)
  let active=true,generation=0
  const attempts=new Map()
  async function run(kind,body,perform,apply=()=>{}){
    if(busy.value)return
    const id=projectId(),ticket=++generation;busy.value=true;error.value=null
    const current=()=>active&&generation===ticket&&projectId()===id
    try{
      const attempt=creationAttempt(attempts.get(kind),{kind,projectId:id,body})
      attempts.set(kind,attempt)
      const result=await perform(attempt.key)
      if(!current())return
      attempts.delete(kind)
      if(result?.project_revision)emit('updated',{project_id:id,project_revision:result.project_revision})
      await apply(result,current)
    }catch(e){if(current())error.value=e}finally{if(current())busy.value=false}
  }
  return {busy,error,run,dispose(){active=false;generation++}}
}
