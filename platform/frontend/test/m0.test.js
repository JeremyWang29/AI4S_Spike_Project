import test from 'node:test'
import assert from 'node:assert/strict'
import {latestRequest,creationAttempt,loadPreview,initialPreview} from '../src/workflow.js'
import {reactive} from 'vue'

test('stale project responses and prior reloads cannot commit',()=>{
  const gate=latestRequest(),a=gate.begin('a'),b=gate.begin('b')
  assert.equal(gate.current(a,'b'),false)
  assert.equal(gate.current(b,'b'),true)
  const newer=gate.begin('b')
  assert.equal(gate.current(b,'b'),false)
  assert.equal(gate.current(newer,'b'),true)
})

test('real scope never restores browser preview and reactive edits serialize for API',()=>{
  const project={id:'real',name:'P',core_keywords:['K']}
  globalThis.sessionStorage={getItem:()=>JSON.stringify({...initialPreview(project),scope:{confirmed:true,object:'forged'}})}
  assert.equal(loadPreview(project).scope.confirmed,false)
  const details=reactive({answers:{object:'new'},candidates:[{decision:'replaced',replacement:'term'}]})
  const plain=JSON.parse(JSON.stringify(details))
  const first=creationAttempt(null,{details:plain},()=> 'key')
  assert.equal(creationAttempt(first,{details:plain},()=> 'unused').key,'key')
  assert.equal(plain.candidates[0].replacement,'term')
})

test('real confirmed status comes from server metadata on load and reset',()=>{
 const confirmed={id:'server-confirmed',scope_status:'confirmed'}
 assert.equal(initialPreview(confirmed).scope.confirmed,true)
 assert.equal(loadPreview(confirmed).scope.confirmed,true)
})
