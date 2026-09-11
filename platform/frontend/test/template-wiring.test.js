import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const source=readFileSync(new URL('../src/App.vue',import.meta.url),'utf8')

test('live workbench controls retain invalidation and progression bindings',()=>{
  for(const binding of ['@change="updateScope"','@input="queryChanged"','@change="evaluationChanged"']) assert.match(source,new RegExp(binding.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')))
  assert.match(source,/function updateScope\(\).*scope\.confirmed=false/)
  assert.match(source,/function queryChanged\(\).*archiveAndInvalidate\(2\)/)
  assert.match(source,/function evaluationChanged\(\).*stopDecision=null/)
  assert.match(source,/:inert="operationBlocked\|\|undefined"/)
})
