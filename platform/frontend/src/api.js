function cookie(name){
  return document.cookie.split(';').map(value=>value.trim()).find(value=>value.startsWith(`${name}=`))?.split('=').slice(1).join('=')||''
}

async function request(path,{method='GET',body,form,idempotencyKey}={}){
  const headers={'Accept':'application/json'}
  if(method!=='GET') headers['X-CSRFToken']=decodeURIComponent(cookie('csrftoken'))
  if(idempotencyKey) headers['Idempotency-Key']=idempotencyKey
  let payload
  if(form){headers['Content-Type']='application/x-www-form-urlencoded';payload=new URLSearchParams(form)}
  else if(body!==undefined){headers['Content-Type']='application/json';payload=JSON.stringify(body)}
  let response
  try{response=await fetch(path,{method,headers,body:payload,credentials:'same-origin'})}
  catch{throw {code:'NETWORK_ERROR',message:'无法连接平台服务',recovery:'确认后端已启动后重试'}}
  const data=await response.json().catch(()=>({}))
  if(!response.ok) throw (data.error||{code:'REQUEST_FAILED',message:'请求失败',recovery:'稍后重试'})
  return data
}

export const api={
  session:()=>request('/api/v1/session/login'),
  login:(username,password)=>request('/api/v1/session/login',{method:'POST',form:{username,password}}),
  logout:()=>request('/api/v1/session/logout',{method:'POST'}),
  projects:()=>request('/api/v1/projects'),
  createProject:(input,key)=>request('/api/v1/projects',{method:'POST',body:{...input,expected_revision:0},idempotencyKey:key}),
}
