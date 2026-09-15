<script setup>
import {computed,watch,onBeforeUnmount} from 'vue'
import {api} from '../api.js'
import {scopeController} from '../m0Controllers.js'
const props=defineProps({project:{type:Object,required:true},drafts:{type:Object,required:true}})
const emit=defineEmits(['saved'])
const controller=scopeController({api,project:()=>props.project,emit,drafts:props.drafts})
const {data,details,busy,error,dirty,saved,changed,load,command}=controller
onBeforeUnmount(controller.dispose)
const labels={object:'研究对象',mechanism:'核心机制',method:'方法／干预',outcome:'主要结局',context:'场景／人群',years:'年份（2020—2026）',languages:'语言',types:'文献类型',include:'纳入标准',exclude:'排除标准',resources:'资源条件'}
const readonly=computed(()=>props.project.role==='reviewer'||data.value?.scope?.status==='confirmed')
watch(()=>props.project.id,()=>load(true),{immediate:true})
watch(()=>props.project.revision,controller.syncRevision)
function addCandidate(){details.value.candidates.push({id:crypto.randomUUID(),term:'',source:'manual',decision:'pending',replacement:''});changed()}
function addConflict(){details.value.conflicts.push({id:crypto.randomUUID(),description:'',resolution:''});changed()}
</script>
<template>
  <div class="panel-stack">
    <p class="callout">AI追问与知识图谱候选提供方未配置。当前使用四组固定问题；语义核查由人工记录。</p>
    <div v-if="error" class="form-error" role="alert"><b>{{error.message}}</b><span>{{error.recovery}}</span><p v-if="error.code==='REVISION_CONFLICT'">本地编辑仍保留。可先复制文本，再载入服务器最新版本重新合并。</p><button :disabled="busy" @click="load(false)">载入服务器版本（覆盖本地编辑）</button></div>
    <p role="status">{{busy?'正在与服务器同步…':dirty?'有未保存的编辑':saved?'已从服务器恢复／保存':'尚未保存'}}</p>
    <template v-if="data&&details">
      <fieldset :disabled="busy||readonly" class="scope-fields">
        <article v-for="group in data.groups" :key="group.id" class="card"><h3>{{group.title}}</h3><div class="form-grid"><label v-for="field in group.fields" :key="field">{{labels[field]}}<input v-model="details.answers[field]" maxlength="2000" @input="changed"></label></div></article>
        <article class="card"><h3>候选词逐条决定</h3><div v-for="item in details.candidates" :key="item.id" class="scope-candidate"><label>候选词<input v-model="item.term" :readonly="item.source!=='manual'||data.scope.details.candidates.some(old=>old.id===item.id)" maxlength="200" @input="changed"></label><small>来源：{{item.source==='project_keyword'?'项目关键词':'人工输入'}}</small><label>决定<select v-model="item.decision" @change="changed"><option value="pending">待处理</option><option value="accepted">接受</option><option value="replaced">替换后接受</option><option value="rejected">拒绝</option></select></label><label v-if="item.decision==='replaced'">替代词<input v-model="item.replacement" maxlength="200" @input="changed"></label></div><button @click="addCandidate">添加人工候选词</button></article>
        <article class="card"><h3>矛盾与人工语义核查</h3><div v-for="item in details.conflicts" :key="item.id"><label>矛盾说明<textarea v-model="item.description" :readonly="data.scope.details.conflicts.some(old=>old.id===item.id)" @input="changed"></textarea></label><label>解决说明<textarea v-model="item.resolution" @input="changed"></textarea></label></div><button @click="addConflict">记录一项矛盾</button><label>人工核查结论（确认时必填）<textarea v-model="details.semantic_review" placeholder="说明年份、纳排条件与候选词的核查结果；这不是AI确定性判断" @input="changed"></textarea></label></article>
      </fieldset>
      <div class="sticky-actions"><span>范围 V{{data.scope.version}} · {{data.scope.status==='confirmed'?'已确认，历史内容不可改写':'草稿'}}</span><template v-if="project.role!=='reviewer'"><button v-if="data.scope.status==='confirmed'" :disabled="busy" @click="command('edit')">创建后续草稿</button><template v-else><button :disabled="busy" @click="command('save')">保存草稿</button><button class="primary" :disabled="busy" @click="command('confirm')">明确确认并冻结版本</button></template></template></div>
      <article class="card"><h3>服务器版本历史</h3><details v-for="version in data.history" :key="version.id"><summary>V{{version.version}} · {{version.status==='confirmed'?'已确认':'草稿'}} {{version.confirmed_at||''}}</summary><dl><div v-for="(value,key) in version.details.answers" :key="key"><dt>{{labels[key]}}</dt><dd>{{value}}</dd></div></dl><p>候选决定：{{version.details.candidates}}</p><p>核查：{{version.details.semantic_review}}</p></details></article>
    </template>
  </div>
</template>
<style scoped>.scope-fields{border:0;padding:0;margin:0;display:grid;gap:16px;min-width:0}.scope-candidate{display:grid;gap:8px;border-bottom:1px solid #ddd;padding:12px 0}select{max-width:100%;padding:8px}dd{overflow-wrap:anywhere}button{white-space:normal}</style>
