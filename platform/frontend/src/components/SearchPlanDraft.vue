<script setup>
import {watch,onBeforeUnmount} from 'vue'
import {searchPlanController} from '../searchPlanController.js'
import {api} from '../api.js'
const props=defineProps({project:{type:Object,required:true}})
const {plans,inputs,error,busy,title,load,create,reset,dispose}=searchPlanController({api,project:()=>props.project})
function logic(node){return node.type==='block'?node.ref:`(${node.children.map(logic).join(` ${node.op} `)})`}
watch(()=>[props.project.id,props.project.scope_version,props.project.scope_status],(next,previous)=>{if(!previous||next[0]!==previous[0])reset();else load()},{immediate:true})
onBeforeUnmount(dispose)
</script>

<template>
  <section class="card search-plan-draft" aria-label="2B检索方案草稿">
    <span class="overline">2B · SEARCH PLAN DRAFT</span><h3>检索块与方案草稿</h3>
    <p><strong>待追问／待确认／不可执行</strong> · 当前仅保存拆分建议，尚未批准方案或执行检索。</p>
    <p v-if="error" role="alert">{{error.message}} · {{error.recovery}}</p>
    <label>研究题目（可选；默认使用项目名称）<input v-model="title" maxlength="2000" :placeholder="project.name"></label>
    <div class="card-actions"><button @click="load" :disabled="busy">刷新服务端草稿</button><button @click="create" :disabled="busy||!inputs||project.role==='reviewer'">{{busy?'读取／保存中…':'生成并保存草稿'}}</button></div>
    <p v-if="!plans.length&&!busy">尚无服务端方案草稿。先确认2A范围与概念，再生成2B草稿。</p>
    <article v-for="plan in plans" :key="plan.id">
      <h4>草稿 V{{plan.version}} · {{plan.applicability==='current'?'当前输入适用':'输入已变化，需重新核查'}}</h4>
      <p>服务器保存 · 范围 V{{plan.scope_version}} · 概念 V{{plan.concept_version}} · 模板 {{plan.template_id}} V{{plan.template_version}}</p>
      <p>原始题目：{{plan.input_snapshot.research_title}}（{{plan.input_snapshot.title_source}}）</p>
      <details v-for="block in plan.blocks" :key="block.block_key"><summary>{{block.block_key}} · {{block.label}}（{{block.facet_type}}）</summary>
        <ul><li v-for="(span,index) in block.source_spans" :key="index">{{span.source}}：「{{span.fragment}}」</li></ul>
        <ul><li v-for="(term,index) in block.term_refs" :key="index">{{term.term}} · {{term.origin}} · {{term.relation}} <span v-if="term.subclass">· {{term.subclass==='resistance'?'抵抗子类':'敏感性子类'}}</span></li></ul>
        <p v-if="block.relation_hypotheses.length">关系待核查：{{block.relation_hypotheses.map(h=>h.marker).join('、')}}；不代表已证实机制或复合体。</p>
      </details>
      <h4>任务矩阵（块内 OR；可选词不得隐性 AND）</h4>
      <ul><li v-for="task in plan.tasks" :key="task.task_key"><b>{{task.task_key}} · {{task.purpose}}</b><p>{{logic(task.logical_ast)}} · {{task.output_partition==='target_disease_main'?'目标疾病主集':'跨疾病补充集'}}</p><p v-if="task.expansion_conditions.length">条件：{{task.expansion_conditions.join('；')}}</p></li></ul>
      <h4>方案执行批次</h4>
      <ul><li v-for="batch in plan.batches" :key="batch.batch_key">{{batch.batch_key==='initial'?'首批（计划中）':'后续条件批次（计划中）'}}：{{batch.task_refs.join('、')}} · {{batch.activation_conditions.join('；')}}</li></ul>
      <h4>未决项</h4><ul><li v-for="(item,index) in plan.unresolved_items" :key="index">{{item.message}}<span v-if="item.marker">（{{item.marker}}）</span></li></ul>
    </article>
  </section>
</template>
