<script setup>
import {reactive,ref} from 'vue'
import {validateProject} from '../workflow.js'
const props=defineProps({busy:Boolean,serverError:Object})
const emit=defineEmits(['submit','cancel'])
const form=reactive({name:'',direction:'',core_keywords:''}),errors=ref({})
function submit(){const result=validateProject(form);errors.value=result.errors;if(result.valid)emit('submit',{name:form.name.trim(),direction:form.direction.trim(),core_keywords:result.keywords})}
</script>
<template><form class="project-form" @submit.prevent="submit" novalidate>
  <div class="form-heading"><div><span class="overline">NEW PROJECT</span><h2>建立研究项目</h2></div><button type="button" class="icon-button" @click="emit('cancel')" aria-label="关闭">×</button></div>
  <p>先填写最小信息，其他边界将在下一步逐项确认。</p>
  <label>项目名称 <em>必填</em><input v-model="form.name" :aria-invalid="Boolean(errors.name)"><small v-if="errors.name" class="field-error">{{errors.name}}</small></label>
  <label>研究方向 <em>必填</em><textarea v-model="form.direction" rows="3" :aria-invalid="Boolean(errors.direction)"></textarea><small v-if="errors.direction" class="field-error">{{errors.direction}}</small></label>
  <label>核心关键词 <em>必填</em><input v-model="form.core_keywords" placeholder="使用逗号分隔，例如：铁死亡，放疗抵抗" :aria-invalid="Boolean(errors.core_keywords)"><small>自动去空白、去重并保留顺序。</small><small v-if="errors.core_keywords" class="field-error">{{errors.core_keywords}}</small></label>
  <div v-if="serverError" class="form-error" role="alert"><b>{{serverError.message}}</b><span>{{serverError.recovery}}</span></div>
  <div class="form-actions"><button type="button" class="secondary" @click="emit('cancel')">取消</button><button class="primary" :disabled="busy">{{busy?'正在创建…':'创建并进入范围确认'}}</button></div>
</form></template>
