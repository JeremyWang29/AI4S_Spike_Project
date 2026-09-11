<script setup>
import {ref} from 'vue'
const props=defineProps({busy:Boolean,error:Object})
const emit=defineEmits(['login','demo'])
const username=ref(''),password=ref('')
function submit(){emit('login',{username:username.value,password:password.value})}
</script>
<template>
  <div class="entry-screen">
    <section class="entry-copy"><span class="overline">AI4S / RESEARCH DECISION</span><h1>把研究方向变成<br>可验证的决策过程</h1><p>从范围收敛、可复现检索到语料和分析准入，每一步保留依据、版本和未决事项。</p><div class="entry-points"><span>01 范围可解释</span><span>02 检索可复现</span><span>03 证据可追溯</span></div></section>
    <section class="login-card"><span class="overline">受邀账号</span><h2>登录研究工作台</h2><p>使用管理员创建的本地测试账号。</p><form @submit.prevent="submit">
      <label>账号<input v-model="username" autocomplete="username" required></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" required></label>
      <div v-if="error" class="form-error" role="alert"><b>{{error.message}}</b><span>{{error.recovery}}</span></div>
      <button class="primary wide" :disabled="busy">{{busy?'正在登录…':'登录'}}</button>
    </form><div class="or"><span>或</span></div><button class="text-button wide" @click="emit('demo')">加载示例流程</button><small class="demo-note">示例不写入服务器，所有卡片均标记为交互预览。</small>
    </section>
  </div>
</template>
