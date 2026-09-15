import {ref} from 'vue'
import {creationAttempt,latestRequest} from './workflow.js'
const clone=value=>JSON.parse(JSON.stringify(value))

export function scopeController({api,project,emit,drafts={}}){
  const data=ref(null),details=ref(null),busy=ref(false),error=ref(null),dirty=ref(false),saved=ref(false)
  const gate=latestRequest()
  let attempt=null,active=true
  const current=ticket=>active&&gate.current(ticket,project().id)
  function changed(){dirty.value=true;saved.value=false}
  function remember(){if(data.value&&dirty.value) drafts[project().id]={details:clone(details.value),data:clone(data.value),attempt}}
  function apply(result){data.value=result;details.value=clone(result.scope.details);dirty.value=false;saved.value=true;attempt=null;delete drafts[project().id];emit('saved',result)}
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
      const input={action,expected_revision:data.value.project_revision,...(action==='edit'?{}:{details:clone(details.value)})}
      attempt=creationAttempt(attempt,input)
      const result=await api.scopeCommand(id,input,attempt.key)
      if(current(ticket))apply(result)
    }catch(e){if(current(ticket)){error.value=e;saved.value=false}}finally{if(current(ticket))busy.value=false}
  }
  function syncRevision(revision){if(data.value&&!busy.value&&!error.value&&revision>data.value.project_revision)data.value.project_revision=revision}
  function dispose(){remember();active=false;gate.begin(null)}
  return {data,details,busy,error,dirty,saved,changed,load,command,syncRevision,dispose}
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
