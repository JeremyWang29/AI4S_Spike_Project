<script setup>
import {ref} from 'vue'
import {api} from '../api.js'
const props=defineProps({busy:Boolean,error:Object})
const emit=defineEmits(['login','demo'])
const username=ref(''),password=ref('')
const redeemMode=ref(false),token=ref(''),newPassword=ref(''),redeemBusy=ref(false),redeemError=ref(null),redeemed=ref(false)
async function redeem(){redeemBusy.value=true;redeemError.value=null;try{await api.redeem({token:token.value,password:newPassword.value});token.value='';newPassword.value='';redeemed.value=true;redeemMode.value=false}catch(e){redeemError.value=e}finally{redeemBusy.value=false}}
function submit(){emit('login',{username:username.value,password:password.value})}
</script>
<template>
  <div class="entry-screen">
    <section class="entry-copy"><span class="overline">AI4S / RESEARCH DECISION</span><h1>把研究方向变成<br>可验证的决策过程</h1><p>从范围收敛、可复现检索到语料和分析准入，每一步保留依据、版本和未决事项。</p><div class="entry-points"><span>01 范围可解释</span><span>02 检索可复现</span><span>03 证据可追溯</span></div></section>
    <section class="login-card"><span class="overline">受邀账号</span><h2>登录研究工作台</h2><p>使用已激活的邀请账号。</p><p v-if="redeemed" role="status">密码已设置，请登录。</p><div v-if="redeemError" class="form-error" role="alert">{{redeemError.message}}</div><form v-if="redeemMode" @submit.prevent="redeem"><label>邀请／重置令牌<input v-model="token" required autocomplete="off"></label><label>新密码（至少12字符）<input v-model="newPassword" type="password" minlength="12" required autocomplete="new-password"></label><button class="primary" :disabled="redeemBusy">设置密码</button></form><form v-else @submit.prevent="submit">
      <label>账号<input v-model="username" autocomplete="username" required></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" required></label>
      <div v-if="error" class="form-error" role="alert"><b>{{error.message}}</b><span>{{error.recovery}}</span></div>
      <button class="primary wide" :disabled="busy">{{busy?'正在登录…':'登录'}}</button>
    </form><button class="text-button wide" @click="redeemMode=!redeemMode">{{redeemMode?'返回登录':'兑换邀请／重置密码'}}</button><div class="or"><span>或</span></div><button class="text-button wide" @click="emit('demo')">加载示例流程</button><small class="demo-note">示例不写入服务器，所有卡片均标记为交互预览。</small>
    </section>
  </div>
</template>
