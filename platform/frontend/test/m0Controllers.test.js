import test from 'node:test'
import assert from 'node:assert/strict'
import {scopeController,actionController} from '../src/m0Controllers.js'
const result=revision=>({project_id:'a',project_revision:revision,scope:{status:'draft',details:{answers:{object:'server'},candidates:[],conflicts:[]}}})
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
test('failed production scope save retains edit and reuses receipt key',async()=>{
 const keys=[],events=[];let fail=true
 const c=scopeController({api:{scope:async()=>result(1),scopeCommand:async(id,body,key)=>{keys.push(key);if(fail)throw Error('network');return {...result(2),scope:{details:body.details}}}},project:()=>({id:'a'}),emit:(...args)=>events.push(args)})
 await c.load();c.details.value.answers.object='local';c.changed();await c.command('save')
 assert.equal(c.busy.value,false);assert.equal(c.saved.value,false);assert.equal(c.details.value.answers.object,'local');assert.equal(events.length,1)
 fail=false;await c.command('save');assert.equal(keys[0],keys[1]);assert.equal(c.saved.value,true)
})
test('scope draft survives disposal and detects server revision changes',async()=>{
 const drafts={},api={scope:async()=>result(1)},project=()=>({id:'a'})
 const c=scopeController({api,project,drafts,emit:()=>{}});await c.load();c.details.value.answers.object='unsaved';c.changed();c.dispose()
 const d=scopeController({api:{scope:async()=>result(2)},project,drafts,emit:()=>{}});await d.load(true)
 assert.equal(d.details.value.answers.object,'unsaved');assert.equal(d.error.value.code,'REVISION_CONFLICT');assert.equal(d.saved.value,false)
})
test('late scope completion after leaving cannot emit or discard draft',async()=>{
 const pending=deferred(),events=[],drafts={}
 const c=scopeController({api:{scope:async()=>result(1),scopeCommand:()=>pending.promise},project:()=>({id:'a'}),drafts,emit:(...args)=>events.push(args)})
 await c.load();c.details.value.answers.object='edit';c.changed();const work=c.command('save');c.dispose();pending.resolve(result(2));await work
 assert.equal(events.length,1);assert.equal(drafts.a.details.answers.object,'edit')
})
test('known same-project revision updates next scope command',async()=>{
 let body
 const c=scopeController({api:{scope:async()=>result(1),scopeCommand:async(id,input)=>{body=input;return result(3)}},project:()=>({id:'a'}),emit:()=>{}})
 await c.load();c.syncRevision(2);await c.command('save');assert.equal(body.expected_revision,2)
})
test('account disposal fences late membership and revision callbacks',async()=>{
 const pending=deferred(),events=[];let applied=false
 const c=actionController({projectId:()=> 'a',emit:(...args)=>events.push(args)})
 const work=c.run('member',{},()=>pending.promise,()=>{applied=true});c.dispose();pending.resolve({project_revision:2});await work
 assert.deepEqual(events,[]);assert.equal(applied,false)
})
test('account uncertain retry retains key even after an unrelated read',async()=>{
 const keys=[],events=[],c=actionController({projectId:()=> 'a',emit:(...args)=>events.push(args)})
 await c.run('member',{revision:1},async key=>{keys.push(key);throw Error('lost response')})
 await c.run('inspect',{},async()=>({}))
 await c.run('member',{revision:1},async key=>{keys.push(key);return {project_revision:2}})
 assert.equal(keys[0],keys[1]);assert.deepEqual(events,[['updated',{project_id:'a',project_revision:2}]])
})
