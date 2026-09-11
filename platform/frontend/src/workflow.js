import {platforms} from './state.js'

export const PREVIEW_SCHEMA = 2

export function normalizeKeywords(values){
  const raw = Array.isArray(values) ? values : String(values||'').split(/[，,;；\n]/)
  const seen = new Set(), result=[]
  for(const value of raw){
    const term=String(value).trim(), key=term.toLocaleLowerCase()
    if(term && !seen.has(key)){seen.add(key);result.push(term)}
  }
  return result
}

export function validateProject(input){
  const errors={}
  if(!String(input.name||'').trim()) errors.name='请输入项目名称'
  if(!String(input.direction||'').trim()) errors.direction='请输入研究方向'
  if(normalizeKeywords(input.core_keywords).length===0) errors.core_keywords='至少输入一个有效关键词'
  return {valid:Object.keys(errors).length===0,errors,keywords:normalizeKeywords(input.core_keywords)}
}

export function creationAttempt(previous,values,makeKey=()=>crypto.randomUUID()){
  const fingerprint=JSON.stringify(values)
  return previous?.fingerprint===fingerprint?previous:{fingerprint,key:makeKey()}
}

export function scopeReady(scope,suggestions){
  const fields=Object.entries(scope||{}).filter(([key])=>!['confirmed','conflictsResolved'].includes(key))
  return fields.length>0&&fields.every(([,value])=>String(value||'').trim())&&scope.conflictsResolved===true&&suggestions?.every(item=>item.decision!=='pending')===true
}

export function explorationReady(item){
  return Boolean(item&&String(item.executedQuery||'').trim()&&item.executedAt&&Number.isInteger(item.hits)&&item.hits>=0&&Number.isInteger(item.exported)&&item.exported>=0&&item.exported<=item.hits&&item.file)
}

export function snapshotReady(preview){return Boolean(preview?.stopDecision&&preview?.corpusChecks?.inclusion&&preview?.corpusChecks?.dedupe)}

export function generateQuery(platformId, keywords){
  const terms=normalizeKeywords(keywords)
  const primary=terms[0]||'研究主题', secondary=terms[1]||'应用场景'
  const query={
    cnki:`主题=(${safeTerm(primary)}) AND 主题=(${safeTerm(secondary)})`,
    wos:`TS=(${safeTerm(primary)} AND ${safeTerm(secondary)})`,
    pubmed:`(${safeTerm(primary)}[Title/Abstract]) AND (${safeTerm(secondary)}[Title/Abstract])`,
    patsnap:`TACD:(${safeTerm(primary)} AND ${safeTerm(secondary)})`,
  }[platformId]
  return query||`(${terms.map(safeTerm).join(' AND ')})`
}

function safeTerm(value){return `"${String(value).replaceAll('"','\\"')}"`}

export function evaluateGate(input){
  const blockers=[]
  const counts=['validGold','positiveGold','negativeGold','unknownCount']
  const rates=['tuningRecall','tuningPrecision','independentRecall','independentPrecision']
  const countValues=Object.fromEntries(counts.map(key=>[key,Number(input[key])]))
  const rateValues=Object.fromEntries(rates.map(key=>[key,Number(input[key])]))
  if(counts.some(key=>!Number.isInteger(countValues[key])||countValues[key]<0)) blockers.push('Gold数量必须是非负整数')
  if(rates.some(key=>!Number.isFinite(rateValues[key])||rateValues[key]<0||rateValues[key]>1)) blockers.push('查全率和查准率必须为0至1的有限数')
  if(countValues.validGold!==countValues.positiveGold+countValues.negativeGold) blockers.push('Gold正负例之和必须等于有效Gold')
  if(countValues.validGold<50) blockers.push('有效Gold不足50条')
  if(countValues.positiveGold<=0) blockers.push('Gold正例分母无效')
  if(countValues.negativeGold<=0) blockers.push('缺少Gold负例回归集')
  if(countValues.unknownCount!==0) blockers.push('unknown必须为0')
  for(const stage of ['tuning','independent']){
    if(rateValues[`${stage}Recall`]<.85) blockers.push(`${stage==='tuning'?'调优':'独立验收'}查全率不足85%`)
    if(rateValues[`${stage}Precision`]<.85) blockers.push(`${stage==='tuning'?'调优':'独立验收'}查准率不足85%`)
  }
  if(input.packageExposed) blockers.push('独立验收包已暴露，必须新建独立包')
  const checks=input.checks||{}
  const requiredChecks=['rules','syntax','semantic','execution','return','quality']
  if(!requiredChecks.every(key=>checks[key]===true)) blockers.push('六类检查尚未全部通过')
  return {validated:blockers.length===0,blockers}
}

export function invalidateAfter(preview, stepIndex){
  const copy=JSON.parse(JSON.stringify(preview))
  const ids=['project','scope','platforms','exploration','seeds','evaluation','corpus','analysis']
  for(const id of ids.slice(stepIndex+1)) copy.stepStates[id]='needs_revalidation'
  copy.stopDecision=null
  copy.corpusFrozen=false
  return copy
}

export function initialPreview(project){
  const queryIds=['cnki','wos','pubmed','patsnap']
  const stepStates=project.workflow?.step_states||{project:'complete',scope:'current',platforms:'locked',exploration:'locked',seeds:'locked',evaluation:'locked',corpus:'locked',analysis:'locked'}
  const scope=project.demo
    ? {object:'肿瘤细胞',mechanism:'铁死亡调控',method:'放疗联合干预',outcome:'放疗敏感性',context:'实体瘤模型',years:'2020—2026',languages:'中文、英文',types:'论文、专利',include:'机制或干预研究',exclude:'仅综述且无新证据',resources:'细胞与公开组学数据',conflictsResolved:true,confirmed:true}
    : {object:'',mechanism:'',method:'',outcome:'',context:'',years:'',languages:'',types:'',include:'',exclude:'',resources:'',conflictsResolved:false,confirmed:false}
  return {
    schema:PREVIEW_SCHEMA, projectId:project.id, stepStates:{...stepStates}, activeStep:project.demo?5:1,
    scope,
    suggestions:[{id:'kg-1',term:'脂质过氧化',source:'示例图谱候选',decision:'accepted'},{id:'ai-1',term:'SLC7A11',source:'示例AI候选',decision:project.demo?'accepted':'pending'},{id:'kg-2',term:'GPX4',source:'示例图谱候选',decision:'accepted'}],
    selectedPlatforms:project.demo?queryIds:[], queries:Object.fromEntries(queryIds.map(id=>[id,generateQuery(id,project.core_keywords)])), queryDirty:false,
    execution:{status:project.demo?'partial':'not_started',executedQuery:'',executedAt:'',hits:project.demo?1264:0,exported:project.demo?800:0,sort:project.demo?'相关性':'',filters:project.demo?'2020—2026；Article/Patent':'',truncated:Boolean(project.demo),file:null},
    seeds:{highlyCited:10,latestQ1:10,deduped:18,shortfall:'两篇同时属于高被引与一区最新，保留双标签。',concepts:['ferroptosis','脂质过氧化','GPX4','SLC7A11'],relations:6},
    evaluation:{validGold:50,positiveGold:34,negativeGold:16,unknownCount:0,tuningRecall:.91,tuningPrecision:.88,independentRecall:.86,independentPrecision:.8496,packageExposed:false,checks:{rules:true,syntax:true,semantic:true,execution:true,return:true,quality:false}},
    stopDecision:null,stopReason:'',corpusFrozen:false,corpusChecks:{inclusion:false,dedupe:false},history:[],
    corpus:{platformHits:1264,imported:800,deduped:742,included:618,analyzable:590},
    capabilities:[{name:'描述性统计',status:'enabled',connection:'尚未执行分析'},{name:'关键词共现',status:'exploratory_only',connection:'示例字段覆盖判定'},{name:'引文网络',status:'blocked',connection:'缺少真实CitationEdge'},{name:'PDF机制提取',status:'blocked',connection:'部分全文不允许外发'}]
  }
}

function key(projectId){return `ai4s-preview-v${PREVIEW_SCHEMA}:${projectId}`}
function validPreview(value,projectId){
  return value?.schema===PREVIEW_SCHEMA&&value.projectId===projectId&&
    value.scope&&value.stepStates&&value.execution&&value.seeds&&value.evaluation?.checks&&
    value.corpus&&value.corpusChecks&&Array.isArray(value.history)&&Array.isArray(value.selectedPlatforms)&&Array.isArray(value.suggestions)&&Array.isArray(value.capabilities)
}
export function loadPreview(project){
  try{
    const value=JSON.parse(sessionStorage.getItem(key(project.id)))
    if(validPreview(value,project.id)) return value
  }catch{}
  return initialPreview(project)
}
export function savePreview(value){try{sessionStorage.setItem(key(value.projectId),JSON.stringify(value));return true}catch{return false}}
export function clearPreview(project){sessionStorage.removeItem(key(project.id));return initialPreview(project)}
export function platformById(id){return platforms.find(item=>item.id===id)}
