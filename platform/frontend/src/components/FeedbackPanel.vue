<script setup>
import {ref,computed,watch,onBeforeUnmount} from 'vue'
import {api} from '../api.js'
import {feedbackController} from '../m0Controllers.js'
const props=defineProps({project:{type:Object,required:true},scopeId:{type:String,required:true}})
const emit=defineEmits(['saved'])
const controller=feedbackController({api,project:()=>props.project,emit})
const {data,busy,error,result,load,command}=controller
const csv=ref('title,abstract,doi,pmid,patent_number,publication_date,application_date\n'),platform=ref(''),task=ref(''),kind=ref('literature'),seed=ref('diagnostic20-v1')
const criteria=ref({include:'',exclude:'',exclude_terms:''}),impact=ref(null),draftLabels=ref({})
const items=computed(()=>data.value?.items||[])
const samples=computed(()=>items.value.filter(i=>i.kind==='sample'&&i.scope_id===props.scopeId))
const latestSample=computed(()=>samples.value.at(-1))
const records=computed(()=>items.value.filter(i=>i.kind==='record'))
const sampledRecords=computed(()=>records.value.filter(r=>samples.value.some(s=>s.record_ids.includes(r.id))))
function sampleForRecord(id){return samples.value.find(s=>s.record_ids.includes(id))}
const readonly=computed(()=>props.project.role==='reviewer')
watch(()=>[props.project.id,props.scopeId],()=>load(),{immediate:true})
watch(()=>props.project.revision,revision=>{if(data.value&&!busy.value)data.value.project_revision=revision})
watch(result,value=>{if(value?.criteria&&value.kind==='proposal'){for(const key of Object.keys(criteria.value))criteria.value[key]=value.criteria[key].join('\n');impact.value=null}if(value?.kind==='impact')impact.value=value})
watch(data,value=>{for(const record of value?.items.filter(i=>i.kind==='record')||[]){const old=value.items.filter(i=>i.kind==='label'&&i.scope_id===props.scopeId&&i.record_id===record.id).at(-1);draftLabels.value[record.id]={label:old?.label||'uncertain',reason:old?.reason||'',reason_code:old?.reason_code||'other'}}})
onBeforeUnmount(controller.dispose)
function rules(){return Object.fromEntries(Object.entries(criteria.value).map(([key,value])=>[key,value.split('\n').map(x=>x.trim()).filter(Boolean)]))}
async function fileChanged(event){const file=event.target.files?.[0];if(file){if(file.size>10000){error.value={message:'CSV超过10000字节，请分批导入'};return}csv.value=await file.text()}}
</script>
<template>
  <section class="card feedback"><h3>真实回传与纳排反馈</h3><p>诊断样本20仅用于完善范围，不是Gold，也不代表精度；正式评估仍未启用。原始回传和范围历史保留。</p>
    <p v-if="error" role="alert">{{error.message}} {{error.recovery}} <button @click="load">刷新服务器状态</button></p>
    <fieldset :disabled="busy||readonly"><legend>导入文献或专利真实记录</legend>
      <label>记录类型<select v-model="kind"><option value="literature">文献</option><option value="patent">专利</option></select></label>
      <label>来源平台<input v-model="platform" maxlength="100"></label><label>外部检索任务编号<input v-model="task" maxlength="160"></label>
      <p>CSV列：title, abstract, doi, pmid, patent_number, publication_date, application_date。标题必填；日期未知请留空，不能补造日期。</p>
      <input type="file" accept=".csv,text/csv" @change="fileChanged"><label>CSV内容<textarea v-model="csv" rows="5" maxlength="10000" /></label>
      <button @click="command({action:'import',record_kind:kind,platform,task_id:task,csv})">导入并在项目内去重</button>
    </fieldset>
    <p>已保存独立记录：{{records.length}}；导入批次：{{items.filter(i=>i.kind==='import').length}}</p>
    <fieldset :disabled="busy||readonly"><legend>固定诊断样本</legend><label>随机种子<input v-model="seed" maxlength="100"></label><button @click="command({action:'sample',seed})">建立首批样本20</button><button v-if="latestSample" @click="command({action:'sample',sample_id:latestSample.id})">追加不重复样本20</button></fieldset>
    <p v-if="latestSample">样本 {{latestSample.id}} · 实际{{latestSample.record_ids.length}}条 · 不足{{latestSample.shortfall}}条 · 总体指纹{{latestSample.population_fingerprint}} · 种子{{latestSample.seed}}</p>
    <details v-for="record in sampledRecords" :key="record.id"><summary>{{record.title}}</summary><p>{{record.abstract}}</p><p>标识：{{record.identifiers}} 来源：{{record.provenance}}</p><details v-if="record.source_variants?.length"><summary>查看各平台导出版本（{{record.source_variants.length}}）</summary><div v-for="(variant,index) in record.source_variants" :key="index"><b>{{variant.title}}</b><p>{{variant.abstract}}</p><small>{{variant.provenance}}</small></div></details>
      <fieldset v-if="draftLabels[record.id]" :disabled="busy||readonly"><label>人工判断<select v-model="draftLabels[record.id].label"><option value="relevant">相关</option><option value="irrelevant">不相关</option><option value="uncertain">不确定</option></select></label>
      <label>原因类别<select v-model="draftLabels[record.id].reason_code"><option v-for="(label,key) in {object:'研究对象',mechanism:'机制',method:'方法',outcome:'结局',context:'场景',date:'日期',type:'类型',language:'语言',insufficient:'信息不足',other:'其他'}" :key="key" :value="key">{{label}}</option></select></label>
      <label>理由<input v-model="draftLabels[record.id].reason" maxlength="2000"></label><button @click="command({action:'label',sample_id:sampleForRecord(record.id).id,record_id:record.id,...draftLabels[record.id]})">保存判断与理由</button></fieldset>
    </details>
    <fieldset :disabled="busy||readonly"><legend>从反馈形成纳排新版本</legend><button @click="command({action:'propose'})">根据已保存标注提出纳排草案</button>
      <p v-if="result?.kind==='proposal'&&result.unresolved_labels?.length">{{result.unresolved_labels.length}}条标注未写理由，草案未据此生成规则；请补充理由或手动编写纳排条件。</p>
      <label>纳入条件（每行一条）<textarea v-model="criteria.include" @input="impact=null" /></label><label>排除条件（每行一条）<textarea v-model="criteria.exclude" @input="impact=null" /></label><label>拟应用的标题／摘要排除关键词（每行一条）<textarea v-model="criteria.exclude_terms" @input="impact=null" /></label>
      <p>自动影响统计只检查标题／摘要排除关键词。文字纳排规则须人工逐条核对；此处不自动生成NOT检索。</p><button @click="command({action:'preview',criteria:rules()})">预览排除影响</button>
      <template v-if="impact"><p>已标相关且命中排除关键词：{{impact.affected_relevant_ids.length}}条（文字规则未自动判断）</p><ul><li v-for="id in impact.affected_relevant_ids" :key="id">{{records.find(r=>r.id===id)?.title||id}}</li></ul><button @click="command({action:'confirm',criteria:rules(),impact_id:impact.id,confirmed:true});impact=null">已审阅关键词命中与文字规则，明确确认新纳排与范围版本</button></template>
    </fieldset>
    <details><summary>已保存反馈与纳排历史</summary><pre>{{items.filter(i=>['criteria','label','sample'].includes(i.kind))}}</pre></details>
  </section>
</template>
<style scoped>.feedback{display:grid;gap:12px}fieldset{display:grid;gap:10px;min-width:0}textarea{width:100%;box-sizing:border-box}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{padding:10px;border:1px solid #ddd}</style>
