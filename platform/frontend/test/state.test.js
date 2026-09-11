import test from 'node:test'; import assert from 'node:assert/strict'; import {stages,statusLabel,nextAction,workAreas} from '../src/state.js'
test('all required work areas remain reachable',()=>{assert.equal(stages.length,8); assert.ok(stages.some(x=>x[0]==='gold')); assert.ok(stages.some(x=>x[0]==='monitor'))})
test('unknown and unconfigured are explicit',()=>{assert.equal(statusLabel('unknown'),'未核验'); assert.equal(statusLabel('unconfigured'),'待配置')})
test('blocker exposes recovery',()=>assert.equal(nextAction({recovery:'补齐依赖'}),'补齐依赖'))
test('every navigation area is distinct and actionable',()=>{const keys=stages.map(x=>x[0]); assert.deepEqual(Object.keys(workAreas),keys); assert.equal(new Set(keys.map(k=>workAreas[k].title)).size,keys.length); for(const area of Object.values(workAreas)) assert.ok(area.actions.length>=2)})
