import test from 'node:test'
import assert from 'node:assert/strict'
import {demoProject,platforms,workflowSteps} from '../src/state.js'
import {PREVIEW_SCHEMA,clearPreview,creationAttempt,evaluateGate,explorationReady,generateQuery,initialPreview,invalidateAfter,loadPreview,normalizeKeywords,savePreview,scopeReady,snapshotReady,validateProject} from '../src/workflow.js'

class SessionStorageMock{
  constructor(){this.values=new Map()}
  getItem(key){return this.values.has(key)?this.values.get(key):null}
  setItem(key,value){this.values.set(key,String(value))}
  removeItem(key){this.values.delete(key)}
}
globalThis.sessionStorage=new SessionStorageMock()

const realProject={id:'project-1',name:'P',direction:'D',core_keywords:[' ferroptosis ','放疗','FERROPTOSIS'],revision:1,scope_version:1,workflow:{step_states:{project:'complete',scope:'current'}}}

test('canonical workflow has eight V0.11 steps including seeds and stop remains in evaluation',()=>{
  assert.equal(workflowSteps.length,8)
  assert.deepEqual(workflowSteps.map(item=>item.id),['project','scope','platforms','exploration','seeds','evaluation','corpus','analysis'])
  assert.equal(workflowSteps.some(item=>item.id==='stop'),false)
})

test('project input trims required fields and keeps stable keyword order',()=>{
  assert.deepEqual(normalizeKeywords(realProject.core_keywords),['ferroptosis','放疗'])
  const valid=validateProject({...realProject,name:'  P ',direction:' D '})
  assert.equal(valid.valid,true);assert.deepEqual(valid.keywords,['ferroptosis','放疗'])
  const invalid=validateProject({name:' ',direction:' ',core_keywords:[' ']})
  assert.equal(invalid.valid,false);assert.deepEqual(Object.keys(invalid.errors),['name','direction','core_keywords'])
})

test('project retry reuses its idempotency key until the submitted values change',()=>{
  let sequence=0;const makeKey=()=>`key-${++sequence}`,values={name:'P',direction:'D',core_keywords:['K']}
  const first=creationAttempt(null,values,makeKey)
  assert.equal(creationAttempt(first,{...values},makeKey).key,'key-1')
  assert.equal(creationAttempt(first,{...values,direction:'changed'},makeKey).key,'key-2')
})

test('scope, exploration and corpus guards reject incomplete confirmations',()=>{
  const preview=initialPreview(realProject)
  assert.equal(scopeReady(preview.scope,preview.suggestions),false)
  for(const key of Object.keys(preview.scope)) if(!['confirmed','conflictsResolved'].includes(key)) preview.scope[key]='value'
  preview.scope.conflictsResolved=true
  assert.equal(scopeReady(preview.scope,preview.suggestions),false)
  preview.suggestions.forEach(item=>item.decision='accepted')
  assert.equal(scopeReady(preview.scope,preview.suggestions),true)
  assert.equal(explorationReady(preview.execution),false)
  assert.equal(snapshotReady(preview),false)
  preview.stopDecision={type:'user_stopped'};preview.corpusChecks={inclusion:true,dedupe:true}
  assert.equal(snapshotReady(preview),true)
})

test('21 platform directory and four complete examples stay explicit',()=>{
  assert.equal(platforms.length,21)
  assert.deepEqual(platforms.filter(item=>item.full).map(item=>item.id),['cnki','wos','pubmed','patsnap'])
  assert.match(generateQuery('wos',['ferroptosis','radiotherapy resistance']),/^TS=/)
  assert.match(generateQuery('pubmed',['ferroptosis','radioresistance']),/Title\/Abstract/)
  assert.match(generateQuery('wos',['cell "death"','A AND B']),/"cell \\"death\\""/)
})

test('preview storage is project isolated, versioned and safely reset',()=>{
  const first=initialPreview(realProject)
  assert.equal(first.scope.object,'')
  assert.equal(first.scope.mechanism,'')
  assert.equal(first.scope.confirmed,false)
  first.scope.object='changed';savePreview(first)
  const second={...realProject,id:'project-2'}
  assert.equal(loadPreview(realProject).scope.object,'changed')
  assert.notEqual(loadPreview(second).scope.object,'changed')
  sessionStorage.setItem(`ai4s-preview-v${PREVIEW_SCHEMA}:project-2`,JSON.stringify({schema:0,projectId:'project-2',bad:true}))
  assert.equal(loadPreview(second).bad,undefined)
  sessionStorage.setItem(`ai4s-preview-v${PREVIEW_SCHEMA}:project-2`,JSON.stringify({schema:PREVIEW_SCHEMA,projectId:'project-2'}))
  assert.equal(loadPreview(second).scope.confirmed,false)
  assert.equal(clearPreview(realProject).scope.confirmed,false)
})

test('preview save reports unavailable session storage without throwing',()=>{
  const original=globalThis.sessionStorage
  globalThis.sessionStorage={setItem(){throw new Error('quota')}}
  try{assert.equal(savePreview(initialPreview(realProject)),false)}finally{globalThis.sessionStorage=original}
})

test('scope or query changes invalidate downstream decisions without changing history input',()=>{
  const preview=initialPreview(demoProject());preview.stopDecision={type:'validated'};preview.corpusFrozen=true
  const changed=invalidateAfter(preview,1)
  assert.equal(changed.stepStates.platforms,'needs_revalidation')
  assert.equal(changed.stepStates.analysis,'needs_revalidation')
  assert.equal(changed.stopDecision,null);assert.equal(changed.corpusFrozen,false)
  assert.equal(preview.stopDecision.type,'validated')
})

function eligible(){return {validGold:50,positiveGold:34,negativeGold:16,unknownCount:0,tuningRecall:.85,tuningPrecision:.85,independentRecall:.85,independentPrecision:.85,packageExposed:false,checks:{rules:true,syntax:true,semantic:true,execution:true,return:true,quality:true}}}

test('validation requires Gold eligibility, two-stage raw double-85 and all six checks',()=>{
  assert.equal(evaluateGate(eligible()).validated,true)
  for(const mutation of [
    {validGold:49,positiveGold:33},{positiveGold:0,negativeGold:50},{negativeGold:0,positiveGold:50},{unknownCount:1},{unknownCount:-1},{independentPrecision:.8496},{independentPrecision:NaN},{tuningRecall:.84},{tuningRecall:1.01},{validGold:50.5},{packageExposed:true},
  ]) assert.equal(evaluateGate({...eligible(),...mutation}).validated,false)
  assert.equal(evaluateGate({...eligible(),checks:{...eligible().checks,quality:false}}).validated,false)
  assert.equal(evaluateGate({...eligible(),checks:{a:true,b:true,c:true,d:true,e:true,f:true}}).validated,false)
})

test('demo covers return, seed, stop, corpus and analysis edge-state inputs without claiming completion',()=>{
  const preview=initialPreview(demoProject())
  assert.equal(preview.execution.status,'partial')
  assert.equal(preview.execution.truncated,true)
  assert.equal(preview.seeds.highlyCited,10);assert.equal(preview.seeds.latestQ1,10);assert.equal(preview.seeds.deduped,18)
  assert.equal(preview.stopDecision,null);assert.equal(preview.corpusFrozen,false)
  assert.deepEqual(preview.capabilities.map(item=>item.status),['enabled','exploratory_only','blocked','blocked'])
  assert.equal(evaluateGate(preview.evaluation).validated,false)
})
