<script setup>
import {ref,watch,onBeforeUnmount} from 'vue'
import {api} from '../api.js'
import {actionController} from '../m0Controllers.js'
const props=defineProps({session:Object,project:Object})
const emit=defineEmits(['revoked','updated'])
const username=ref(''),kind=ref('invite'),issued=ref(null),members=ref([]),userId=ref(''),role=ref('researcher'),taskId=ref(''),task=ref(null)
const controller=actionController({projectId:()=>props.project?.id,emit})
const {busy,error,run}=controller
onBeforeUnmount(controller.dispose)
watch(()=>props.project?.id,id=>{members.value=[];task.value=null;if(id&&props.project.role==='owner')run('members',{},()=>api.members(id),result=>{members.value=result.items})},{immediate:true})
function issue(){const body={username:username.value,kind:kind.value};run('issue',body,()=>api.issue(body),result=>{issued.value=result})}
function revoke(){run('revoke',{},()=>api.revoke(),()=>emit('revoked'))}
function member(){const id=props.project.id,body={user_id:Number(userId.value),role:role.value,expected_revision:props.project.revision};run('member',body,key=>api.memberCommand(id,body,key),async(result,current)=>{const list=await api.members(id);if(current())members.value=list.items})}
function rebuild(){const id=props.project.id,revision=props.project.revision;run('rebuild',{revision},key=>api.rebuild(id,revision,key))}
function inspect(){const id=props.project.id,target=taskId.value;run('inspect',{target},()=>api.task(id,target),result=>{task.value=result})}
function retry(){const id=props.project.id,target=taskId.value,revision=props.project.revision;run('retry',{target,revision},key=>api.retry(id,target,revision,key),result=>{task.value=result})}
</script>
<template><article class="card account-panel"><h3>账号与恢复</h3><p>账号ID：{{session.user_id}}</p><div v-if="error" class="form-error" role="alert">{{error.message}} · {{error.recovery}}</div><fieldset :disabled="busy"><button @click="revoke">撤销我的全部会话</button><template v-if="session.administrator"><h4>签发邀请或密码重置</h4><label>账号<input v-model="username" maxlength="150"></label><label>用途<select v-model="kind"><option value="invite">邀请（未激活账号可重发）</option><option value="reset">密码重置</option></select></label><button @click="issue">签发一次性令牌</button><p v-if="issued">请自行安全交付给用户；不会自动发送邮件。账号ID {{issued.user_id}}，截止 {{issued.expires_at}}<textarea readonly :value="issued.token"></textarea></p></template><template v-if="project?.role==='owner'"><h4>项目成员</h4><p v-for="item in members" :key="item.user_id">{{item.user__username}}（{{item.user_id}}）· {{item.role}}</p><label>账号ID<input v-model="userId" type="number" min="1"></label><label>角色<select v-model="role"><option value="researcher">研究者</option><option value="reviewer">审核者（只读分配项目）</option><option value="remove">移除成员</option></select></label><button @click="member">更新成员</button></template><template v-if="project&&project.role!=='reviewer'"><h4>项目恢复</h4><button @click="rebuild">重建工作流投影</button><label>任务ID<input v-model="taskId"></label><button @click="inspect">检查任务</button><p v-if="task">{{task.status}} · {{task.recovery}}</p><button v-if="task?.status==='failed'&&task?.recovery==='retry'" @click="retry">请求安全重试</button></template></fieldset></article></template>
<style scoped>fieldset{border:0;padding:0;min-width:0}select,input,textarea{max-width:100%}.account-panel{max-width:700px;margin:16px auto}button{margin:6px 0}</style>
