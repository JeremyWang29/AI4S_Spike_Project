import {ref} from 'vue'

export function searchPlanController({api,project}){
const plans=ref([]),inputs=ref(null),error=ref(null),busy=ref(false),title=ref('')
let generation=0,attempt=null
async function load(){
  const current=++generation
  busy.value=true;error.value=null;plans.value=[];inputs.value=null
  try{const result=await api.searchPlans(project().id);if(current!==generation)return;plans.value=result.items;inputs.value=result.inputs;error.value=result.blocker}
  catch(err){if(current===generation)error.value=err}
  finally{if(current===generation)busy.value=false}
}
async function create(){
  if(busy.value||!inputs.value)return
  const current=generation,projectId=project().id
  const body={...inputs.value,...(title.value.trim()?{research_title:title.value}:{})}
  const signature=JSON.stringify(body)
  if(!attempt||attempt.signature!==signature)attempt={signature,key:crypto.randomUUID()}
  busy.value=true;error.value=null
  try{const plan=await api.createSearchPlan(projectId,body,attempt.key);if(current!==generation)return;attempt=null;await load()}
  catch(err){if(current===generation)error.value=err}
  finally{if(current===generation)busy.value=false}
}

return {plans,inputs,error,busy,title,load,create,reset(){title.value='';attempt=null;return load()},dispose(){generation++}}
}
