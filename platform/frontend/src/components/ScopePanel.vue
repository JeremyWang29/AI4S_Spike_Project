<script setup>
import {computed,watch,onBeforeUnmount,ref} from 'vue'
import {api} from '../api.js'
import {scopeController} from '../m0Controllers.js'
import FeedbackPanel from './FeedbackPanel.vue'
const props=defineProps({project:{type:Object,required:true},drafts:{type:Object,required:true}})
const emit=defineEmits(['saved'])
const controller=scopeController({api,project:()=>props.project,emit,drafts:props.drafts})
const {data,details,busy,error,dirty,saved,changed,load,command,suggestions,recommend,setExternal,selectOption}=controller
onBeforeUnmount(controller.dispose)
const labels={object:'研究对象',mechanism:'核心机制',method:'方法／干预',outcome:'主要结局',context:'场景／人群',years:'年份（2020—2026）',languages:'语言',types:'文献类型',include:'纳入标准',exclude:'排除标准',resources:'资源条件'}
const readonly=computed(()=>props.project.role==='reviewer'||data.value?.scope?.status==='confirmed')
watch(()=>props.project.id,async()=>{await load(true)},{immediate:true})
watch(()=>props.project.revision,controller.syncRevision)
function addCandidate(){details.value.candidates.push({id:crypto.randomUUID(),term:'',source:'manual',decision:'pending',replacement:'',relation:'related',parent_keyword:data.value.scope.core_keywords?.[0]||'',variant_selected:false});changed()}
function addConflict(){details.value.conflicts.push({id:crypto.randomUUID(),description:'',resolution:''});changed()}
const fields=['object','mechanism','method','outcome','context']
const relationLabels={original:'原始词',synonym:'同义词（并入原词组）',broader:'上位词（扩展变体）',narrower:'下位词（聚焦变体）',related:'相关词（仅补充检索）'}
const modelStatusLabels={AVAILABLE:'已生成',DENIED:'未授权',UNCONFIGURED:'未配置',FAILED:'调用失败',QUOTA_EXHAUSTED:'额度用尽，已保留图谱建议'}
const options={languages:{unlimited:'不限',zh:'中文',en:'英文',ja:'日文',de:'德文',fr:'法文',other:'其他'},literature_types:{unlimited:'不限',article:'研究论文',review:'综述',systematic_review:'系统综述',meta_analysis:'Meta分析',preprint:'预印本',conference:'会议论文',thesis:'学位论文',other:'其他'},patent_types:{unlimited:'不限',invention:'发明',utility_model:'实用新型',design:'外观设计',other:'其他'}}
function toggleBoundary(key,value,checked){let values=details.value.boundary[key];values=checked?(value==='unlimited'?['unlimited']:[...values.filter(v=>v!=='unlimited'),value]):values.filter(v=>v!==value);details.value.boundary[key]=values.length?values:['unlimited'];changed()}
function statusChanged(field){const value=details.value.research_fields[field];if(value.status!=='answered')value.selected=[];changed()}
const expanded=ref({})
const groups=computed(()=>{
  if(!data.value||!details.value)return []
  const keywords=data.value.scope.core_keywords
  return [...keywords.map(keyword=>({keyword,items:details.value.candidates.filter(item=>item.parent_keyword===keyword)})),
    {keyword:'历史或待调整关键词',items:details.value.candidates.filter(item=>!keywords.includes(item.parent_keyword))}].filter(group=>group.items.length)
})
function derived(group){const rank={synonym:0,narrower:1,broader:2,related:3,original:4};return group.items.filter(item=>item.source!=='project_keyword').sort((a,b)=>(rank[a.relation]??5)-(rank[b.relation]??5))}
function visible(group){return [...group.items.filter(item=>item.source==='project_keyword'),
  ...(expanded.value[group.keyword]?derived(group):derived(group).slice(0,5))]}
function changeKeywords(event){data.value.scope.core_keywords=event.target.value.split(/[,，;；\n]/).map(x=>x.trim()).filter(Boolean);changed()}
</script>
<template>
  <div class="panel-stack">
    <p class="callout">保存五项研究状态后，可主动生成图谱和模型候选词。仅已回答内容用于建议；机制仍是待验证假设。每个派生词须逐条审核。</p>
    <div v-if="data?.scope?.status==='draft'&&project.role!=='reviewer'"><p>图谱：{{data.providers.knowledge_graph==='AVAILABLE'?'本项目有可用术语':'当前关键词无覆盖'}}；外部模型：{{data.external_processing_allowed?'已允许':'未允许'}}。</p><button :disabled="busy||dirty" @click="setExternal(!data.external_processing_allowed)">{{data.external_processing_allowed?'撤回外部处理许可':'允许外部模型处理本项目已保存的研究内容'}}</button></div>
    <p v-if="suggestions" role="status">建议状态：{{({ready:'可选建议已准备',UNCONFIGURED:'模型未配置，可人工填写',DENIED:'项目未允许外部处理，可人工填写',failed:'模型调用失败，可人工填写或明确重试',pending:'相同请求处理中',stale:'项目已变化，建议已作废',QUOTA_EXHAUSTED:'调用额度已用完'})[suggestions.status]||suggestions.status}}</p>
    <button v-if="!readonly" :disabled="busy||dirty" @click="recommend(false)">根据已保存范围生成候选词</button>
    <button v-if="!readonly&&suggestions" :disabled="busy||dirty" @click="recommend(true)">明确重新生成／重试（模型调用可能消耗额度）</button>
    <button v-if="!readonly&&suggestions?.status==='pending'" :disabled="busy" @click="recommend()">检查已有建议是否完成（不产生新调用）</button>
    <div v-if="error" class="form-error" role="alert"><b>{{error.message}}</b><span>{{error.recovery}}</span><p v-if="error.code==='REVISION_CONFLICT'">本地编辑仍保留。可先复制文本，再载入服务器最新版本重新合并。</p><button :disabled="busy" @click="load(false)">载入服务器版本（覆盖本地编辑）</button></div>
    <p role="status">{{busy?'正在与服务器同步…':dirty?'有未保存的编辑':saved?'已从服务器恢复／保存':'尚未保存'}}</p>
    <template v-if="data&&details">
      <fieldset :disabled="busy||readonly" class="scope-fields">
        <article class="card"><h3>原始关键词</h3><p>修改关键词后先保存草稿；既有决定保留并标为待复核。</p><textarea :value="data.scope.core_keywords.join('，')" @change="changeKeywords" /></article>
        <template v-if="details.schema_version===2">
          <article class="card" v-for="field in fields" :key="field"><h3>{{labels[field]}}</h3>
            <p v-if="field==='mechanism'">以下均为机制假设，不能视为已证实事实。</p>
            <label>回答状态<select v-model="details.research_fields[field].status" @change="statusChanged(field)"><option value="unanswered">待回答</option><option value="answered">已回答</option><option value="not_applicable">不适用</option><option value="exploratory">暂未确定，探索中</option></select></label>
            <template v-if="suggestions?.status==='ready'"><p>{{suggestions.result.fields[field].question}}</p><label v-for="option in suggestions.result.fields[field].options" :key="option.id"><input type="checkbox" :checked="details.research_fields[field].selected.includes(option.id)" @change="selectOption(field,option,$event.target.checked)">{{option.text}}<small>理由：{{option.reason}} · 来源：本项目模型建议</small></label></template>
            <label>填写或编辑答案<textarea v-model="details.research_fields[field].text" maxlength="2000" @input="changed" /></label>
            <label v-if="details.research_fields[field].review_required"><input type="checkbox" @change="details.research_fields[field].review_required=false;changed()">已复核上一版本答案</label>
          </article>
          <article class="card"><h3>时间与类型边界</h3><p>默认不限；自定义起止日期包含当日。文献按发表日期；未知日期或日期精度不足的记录需要人工核对。</p>
            <label>起始日期<input type="date" :value="details.boundary.start||''" @input="details.boundary.start=$event.target.value||null;changed()"></label><label>结束日期<input type="date" :value="details.boundary.end||''" @input="details.boundary.end=$event.target.value||null;changed()"></label>
            <button @click="details.boundary.start=null;details.boundary.end=null;changed()">日期不限</button>
            <label>专利日期依据<select v-model="details.boundary.patent_date" @change="changed"><option value="publication">公开日期</option><option value="application">申请日期</option></select></label>
            <div v-for="(choices,key) in options" :key="key"><h4>{{({languages:'语言',literature_types:'文献类型',patent_types:'专利类型'})[key]}}</h4><label v-for="(label,value) in choices" :key="value"><input type="checkbox" :checked="details.boundary[key].includes(value)" @change="toggleBoundary(key,value,$event.target.checked)">{{label}}</label></div>
            <div v-if="details.legacy_boundary"><p>历史边界：{{details.legacy_boundary}}</p><label><input type="checkbox" v-model="details.legacy_boundary_reviewed" @change="changed">已核对历史文字与当前边界，无意外缩窄</label></div>
          </article>
          <article class="card"><h3>其他说明（首轮纳排可留空）</h3><label v-for="field in ['include','exclude','resources']" :key="field">{{labels[field]}}<input v-model="details.answers[field]" maxlength="2000" @input="changed"></label></article>
        </template>
        <article v-for="group in (details.schema_version===2?[]:data.groups)" :key="group.id" class="card"><h3>{{group.title}}</h3><div class="form-grid"><label v-for="field in group.fields" :key="field">{{labels[field]}}<input v-model="details.answers[field]" maxlength="2000" @input="changed"></label></div></article>
        <article class="card"><h3>按原关键词审核候选词</h3><p v-if="suggestions?.status==='ready'">图谱：{{suggestions.result.graph_status==='AVAILABLE'?'已查询':'无覆盖'}}；模型：{{modelStatusLabels[suggestions.result.model_status]||suggestions.result.model_status}}。同形异义与关系冲突须人工核查。</p><section v-for="group in groups" :key="group.keyword"><h4>{{group.keyword}}（{{group.items.length}}）</h4><div v-for="item in visible(group)" :key="item.id" class="scope-candidate"><label>候选词<input v-model="item.term" :readonly="item.source!=='manual'||data.scope.details.candidates.some(old=>old.id===item.id)" maxlength="200" @input="changed"></label><small>来源：{{({project_keyword:'项目关键词',graph:'知识图谱',model:'模型建议',manual:'人工输入'})[item.source]}} · {{relationLabels[item.relation]}}</small><small v-if="item.source==='graph'">概念：{{item.concept_id}} · 版本：{{item.graph_version}} · 许可：{{item.license}}</small><small v-if="item.source_position">来源定位：{{item.source_position}}</small><p v-if="item.definition">定义：{{item.definition}}</p><p v-if="item.reason">理由：{{item.reason}}</p><p v-if="item.conflict">⚠ 同形异义或来源关系冲突：须核查关系</p><label v-if="item.conflict"><input type="checkbox" v-model="item.relation_reviewed" @change="changed">已人工核查该词关系</label><label v-if="item.conflict&&item.relation_reviewed">关系核查理由<textarea v-model="item.relation_review_reason" maxlength="2000" @input="changed" /></label><label v-if="item.review_required"><input type="checkbox" @change="item.review_required=false;changed()">已复核范围、图谱或权限变化</label><label>关系<select v-model="item.relation" :disabled="item.source!=='manual'||data.scope.details.candidates.some(old=>old.id===item.id)" @change="changed"><option v-for="(label,key) in relationLabels" :key="key" :value="key">{{label}}</option></select></label><label>所属关键词<input v-model="item.parent_keyword" :readonly="item.source!=='manual'||data.scope.details.candidates.some(old=>old.id===item.id)" @input="changed"></label><label v-if="['broader','narrower'].includes(item.relation)"><input type="checkbox" v-model="item.variant_selected" @change="changed">明确选择独立扩展／聚焦变体（不改变主检索组）</label><label>决定<select v-model="item.decision" @change="changed"><option value="pending">待处理</option><option value="accepted">接受</option><option v-if="item.source!=='project_keyword'" value="replaced">替换后接受</option><option value="rejected">拒绝</option></select></label><label v-if="item.decision==='replaced'">替代词<input v-model="item.replacement" maxlength="200" @input="changed"></label></div><button v-if="derived(group).length>5" @click="expanded[group.keyword]=!expanded[group.keyword]">{{expanded[group.keyword]?'收起':'显示其余 '+(derived(group).length-5)+' 项'}}</button></section><button @click="addCandidate">添加人工候选词</button></article>
        <article class="card"><h3>矛盾与人工语义核查</h3><div v-for="item in details.conflicts" :key="item.id"><label>矛盾说明<textarea v-model="item.description" :readonly="data.scope.details.conflicts.some(old=>old.id===item.id)" @input="changed"></textarea></label><label>解决说明<textarea v-model="item.resolution" @input="changed"></textarea></label></div><button @click="addConflict">记录一项矛盾</button><label>人工核查结论（确认时必填）<textarea v-model="details.semantic_review" placeholder="说明年份、纳排条件与候选词的核查结果；这不是AI确定性判断" @input="changed"></textarea></label></article>
      </fieldset>
      <div class="sticky-actions"><span>范围 V{{data.scope.version}} · {{data.scope.status==='confirmed'?'已确认，历史内容不可改写':'草稿'}}</span><template v-if="project.role!=='reviewer'"><button v-if="data.scope.status==='confirmed'" :disabled="busy" @click="command('edit')">创建后续草稿</button><template v-else><button :disabled="busy" @click="command('save')">保存草稿</button><button class="primary" :disabled="busy" @click="command('confirm')">明确确认并冻结版本</button></template></template></div>
      <FeedbackPanel v-if="data.scope.status==='confirmed'" :project="project" :scope-id="data.scope.id" @saved="emit('saved',$event);load(false)" />
      <article class="card"><h3>服务器版本历史</h3><details v-for="version in data.history" :key="version.id"><summary>V{{version.version}} · {{version.status==='confirmed'?'已确认':'草稿'}} {{version.confirmed_at||''}}</summary><dl><div v-for="(value,key) in version.details.answers" :key="key"><dt>{{labels[key]}}</dt><dd>{{value}}</dd></div></dl><p>候选决定：{{version.details.candidates}}</p><p>核查：{{version.details.semantic_review}}</p></details></article>
    </template>
  </div>
</template>
<style scoped>.scope-fields{border:0;padding:0;margin:0;display:grid;gap:16px;min-width:0}.scope-candidate{display:grid;gap:8px;border-bottom:1px solid #ddd;padding:12px 0}select{max-width:100%;padding:8px}dd{overflow-wrap:anywhere}button{white-space:normal}</style>
