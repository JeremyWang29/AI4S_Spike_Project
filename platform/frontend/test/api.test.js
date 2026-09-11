import test from 'node:test'
import assert from 'node:assert/strict'
import {api} from '../src/api.js'

test('browser adapter carries CSRF, session credentials and project idempotency contract',async()=>{
  const originalDocument=globalThis.document,originalFetch=globalThis.fetch
  const calls=[]
  globalThis.document={cookie:'theme=green; csrftoken=token%20value'}
  globalThis.fetch=async(path,options={})=>{
    calls.push({path,options})
    if(path.endsWith('/projects')&&options.method==='POST') return new Response(JSON.stringify({id:'p1'}),{status:201,headers:{'Content-Type':'application/json'}})
    return new Response(JSON.stringify({authenticated:true,items:[]}),{status:200,headers:{'Content-Type':'application/json'}})
  }
  try{
    await api.session()
    await api.login('researcher','secret')
    await api.projects()
    await api.createProject({name:'P',direction:'D',core_keywords:['K']},'stable-key')
  }finally{globalThis.document=originalDocument;globalThis.fetch=originalFetch}

  assert.deepEqual(calls.map(call=>[call.path,call.options.method||'GET']),[
    ['/api/v1/session/login','GET'],['/api/v1/session/login','POST'],['/api/v1/projects','GET'],['/api/v1/projects','POST'],
  ])
  assert.equal(calls.every(call=>call.options.credentials==='same-origin'),true)
  assert.equal(calls[1].options.headers['X-CSRFToken'],'token value')
  assert.equal(calls[1].options.headers['Content-Type'],'application/x-www-form-urlencoded')
  assert.equal(String(calls[1].options.body),'username=researcher&password=secret')
  assert.equal(calls[3].options.headers['Idempotency-Key'],'stable-key')
  assert.deepEqual(JSON.parse(calls[3].options.body),{name:'P',direction:'D',core_keywords:['K'],expected_revision:0})
})
