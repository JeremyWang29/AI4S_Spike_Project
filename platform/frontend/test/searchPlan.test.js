import test from 'node:test'
import assert from 'node:assert/strict'
import {searchPlanController} from '../src/searchPlanController.js'
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}}
const response=items=>({items,inputs:{scope_ref:{id:'scope'},concept_ref:{id:'concept'}},blocker:null})
test('plan retry reuses key and reads current applicability after receipt replay',async()=>{
 const keys=[];let fail=true
 const c=searchPlanController({project:()=>({id:'a'}),api:{searchPlans:async()=>response([{id:'saved',applicability:'needs_revalidation'}]),createSearchPlan:async(id,body,key)=>{keys.push(key);if(fail)throw Error('lost response');return {id:'saved',applicability:'current'}}}})
 await c.load();await c.create();fail=false;await c.create()
 assert.equal(keys[0],keys[1]);assert.equal(c.plans.value[0].applicability,'needs_revalidation')
})
test('project switch clears title and late responses cannot replace current project',async()=>{
 const pending=deferred();let project={id:'a'}
 const c=searchPlanController({project:()=>project,api:{searchPlans:id=>id==='a'?pending.promise:Promise.resolve(response([{id:'b-plan'}]))}})
 const first=c.load();c.title.value='previous topic';project={id:'b'};await c.reset();pending.resolve(response([{id:'a-plan'}]));await first
 assert.equal(c.title.value,'');assert.equal(c.plans.value[0].id,'b-plan')
})
test('unmount fences a late read',async()=>{
 const pending=deferred();const c=searchPlanController({project:()=>({id:'a'}),api:{searchPlans:()=>pending.promise}})
 const work=c.load();c.dispose();pending.resolve(response([{id:'late'}]));await work;assert.deepEqual(c.plans.value,[])
})
