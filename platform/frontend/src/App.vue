<script setup>
import {computed,onMounted,ref,watch} from 'vue'
import {api} from './api.js'
import {demoProject,evidenceStates,platforms,stages,statusLabel,workflowSteps} from './state.js'
import {clearPreview,creationAttempt,evaluateGate,explorationReady,generateQuery,initialPreview,invalidateAfter,loadPreview,platformById,savePreview,scopeReady,snapshotReady} from './workflow.js'
import LoginPanel from './components/LoginPanel.vue'
import PreviewBadge from './components/PreviewBadge.vue'
import ProjectForm from './components/ProjectForm.vue'
import WorkflowStepper from './components/WorkflowStepper.vue'
import ScopePanel from './components/ScopePanel.vue'
import AccountPanel from './components/AccountPanel.vue'

const session=ref({authenticated:false,username:null}),projects=ref([]),selected=ref(null),preview=ref(null),pendingCreate=ref(null)
const booting=ref(true),busy=ref(false),error=ref(null),showCreate=ref(false),moduleArea=ref('overview'),demoMode=ref(false)
const showAccount=ref(false),scopeDrafts=ref({})
const scopeGroups=[
  {title:'对象与机制',fields:[['object','研究对象'],['mechanism','核心机制']]},
  {title:'方法与结局',fields:[['method','方法／干预'],['outcome','主要结局']]},
  {title:'场景与文献边界',fields:[['context','场景／人群'],['years','年份'],['languages','语言'],['types','文献类型']]},
  {title:'纳排与资源条件',fields:[['include','纳入标准'],['exclude','排除标准'],['resources','资源条件']]},
]
const groupedPlatforms=computed(()=>platforms.reduce((groups,item)=>{(groups[item.group]??=[]).push(item);return groups},{}))
const gate=computed(()=>preview.value?evaluateGate(preview.value.evaluation):{validated:false,blockers:[]})
const scopeComplete=computed(()=>preview.value&&scopeReady(preview.value.scope,preview.value.suggestions))
const activeStep=computed(()=>preview.value?.activeStep||0)
const currentStep=computed(()=>workflowSteps[activeStep.value])
const operationBlocked=computed(()=>workflowSteps.slice(0,activeStep.value).some(step=>preview.value?.stepStates?.[step.id]!=='complete'))
const executionReady=computed(()=>explorationReady(preview.value?.execution))
const corpusReady=computed(()=>snapshotReady(preview.value))
const sideBlockers=computed(()=>{
  if(!preview.value)return[]
  if(operationBlocked.value) return [{code:'PREDECESSOR_REQUIRED',message:'前序步骤尚未完成',recovery:'按顶部流程从最早未完成步骤继续'}]
  if(currentStep.value.id==='evaluation') return gate.value.blockers.map((message,index)=>({code:`EVAL_${index+1}`,message,recovery:'展开评估详情并修正后重新计算'}))
  if(currentStep.value.id==='scope'&&!preview.value.scope.confirmed) return [{code:'SCOPE_CONFIRMATION_REQUIRED',message:'请完成范围访谈并确认',recovery:'填写所有范围字段并逐条处理候选词'}]
  if(currentStep.value.id==='platforms'&&!preview.value.selectedPlatforms.length) return [{code:'PLATFORM_REQUIRED',message:'尚未选择检索平台',recovery:'至少选择一个平台并核对生成式'}]
  if(currentStep.value.id==='corpus'&&!preview.value.stopDecision) return [{code:'STOP_DECISION_REQUIRED',message:'尚未记录本轮检索停止决定',recovery:'返回Gold与正式检索步骤'}]
  if(currentStep.value.id==='analysis'&&!preview.value.corpusFrozen) return [{code:'DATASET_SNAPSHOT_REQUIRED',message:'尚未冻结语料快照',recovery:'完成语料口径确认后冻结快照'}]
  return []
})

onMounted(async()=>{try{session.value=await api.session();if(session.value.authenticated)await refreshProjects()}catch(e){error.value=e}finally{booting.value=false}})
watch(preview,value=>{if(value&&selected.value?.demo)savePreview(value)},{deep:true})
function scopeSaved(result){if(!selected.value||selected.value.demo||result.project_id!==selected.value.id)return;selected.value.revision=result.project_revision;selected.value.scope_version=result.scope.version;selected.value.scope_status=result.scope.status;selected.value.direction=result.scope.direction;projects.value=projects.value.map(project=>project.id===selected.value.id?{...selected.value}:project);preview.value.scope.confirmed=result.scope.status==='confirmed';preview.value.stepStates.scope=result.scope.status==='confirmed'?'complete':'current'}
function revisionUpdated(result){if(selected.value&&result.project_id===selected.value.id){selected.value.revision=result.project_revision;projects.value=projects.value.map(project=>project.id===selected.value.id?{...selected.value}:project)}}

async function login(values){busy.value=true;error.value=null;try{session.value=await api.login(values.username,values.password);await refreshProjects()}catch(e){error.value=e}finally{busy.value=false}}
async function logout(){scopeDrafts.value={};try{await api.logout()}finally{session.value={authenticated:false,username:null};projects.value=[];selected.value=null;preview.value=null;demoMode.value=false}}
async function refreshProjects(){projects.value=(await api.projects()).items;if(projects.value.length)selectProject(projects.value[0])}
function selectProject(project){selected.value={...project,role:project.role||'owner'};preview.value=loadPreview(project);demoMode.value=Boolean(project.demo);showCreate.value=false}
function loadDemo(){const project=demoProject();demoMode.value=true;session.value={authenticated:false,username:'示例访客'};projects.value=[project];selectProject(project)}
async function createProject(values){busy.value=true;error.value=null;pendingCreate.value=creationAttempt(pendingCreate.value,values);try{const project=await api.createProject(values,pendingCreate.value.key);pendingCreate.value=null;projects.value=[project,...projects.value.filter(item=>item.id!==project.id)];selectProject(project);preview.value.activeStep=1}catch(e){error.value=e}finally{busy.value=false}}
function chooseStep(index){preview.value.activeStep=index}
function archiveAndInvalidate(stepIndex){const previous=preview.value;const meaningful=previous.execution.status!=='not_started'||previous.stopDecision||previous.corpusFrozen;if(meaningful){previous.history??=[];previous.history.push({invalidatedAt:new Date().toISOString(),execution:previous.execution,seeds:previous.seeds,evaluation:previous.evaluation,stopDecision:previous.stopDecision,corpus:previous.corpus});previous.history=previous.history.slice(-5)}const next=invalidateAfter(previous,stepIndex);if(stepIndex<=2){next.execution={status:'not_started',executedQuery:'',executedAt:'',hits:0,exported:0,sort:'',filters:'',truncated:false,file:null};next.seeds={highlyCited:0,latestQ1:0,deduped:0,shortfall:'等待新一轮探索回传。',concepts:[],relations:0};Object.assign(next.evaluation,{validGold:0,positiveGold:0,negativeGold:0,unknownCount:0,tuningRecall:0,tuningPrecision:0,independentRecall:0,independentPrecision:0,packageExposed:false});for(const key of Object.keys(next.evaluation.checks))next.evaluation.checks[key]=false;next.corpus={platformHits:0,imported:0,deduped:0,included:0,analyzable:0};next.corpusChecks={inclusion:false,dedupe:false}}preview.value=next}
function updateScope(){archiveAndInvalidate(1);preview.value.scope.confirmed=false;preview.value.stepStates.scope='current'}
function confirmScope(){if(!scopeComplete.value)return;preview.value.scope.confirmed=true;preview.value.stepStates.scope='complete';preview.value.stepStates.platforms='current';preview.value.activeStep=2}
function setSuggestion(item,decision){item.decision=decision;updateScope()}
function togglePlatform(id){const list=preview.value.selectedPlatforms,index=list.indexOf(id);index>=0?list.splice(index,1):list.push(id);preview.value.queries[id]=generateQuery(id,selected.value.core_keywords);archiveAndInvalidate(2);preview.value.stepStates.platforms='current'}
function queryChanged(){preview.value.queryDirty=true;archiveAndInvalidate(2);preview.value.stepStates.platforms='current'}
function confirmPlatforms(){if(!preview.value.selectedPlatforms.length)return;preview.value.queryDirty=false;preview.value.stepStates.platforms='complete';preview.value.stepStates.exploration='current';preview.value.activeStep=3}
function fileChosen(event){const file=event.target.files?.[0];preview.value.execution.file=file?{name:file.name,size:file.size,type:file.type||'未知类型'}:null}
function recordExploration(){if(!executionReady.value)return;preview.value.execution.status=preview.value.execution.truncated?'partial':'complete';preview.value.stepStates.exploration='complete';preview.value.stepStates.seeds='current';preview.value.activeStep=4}
function confirmSeeds(){preview.value.stepStates.seeds='complete';preview.value.stepStates.evaluation='current';preview.value.activeStep=5}
function evaluationChanged(){preview.value.stopDecision=null;preview.value.corpusFrozen=false;preview.value.stepStates.evaluation='current';preview.value.stepStates.corpus='needs_revalidation';preview.value.stepStates.analysis='needs_revalidation'}
function repairEvaluation(){Object.assign(preview.value.evaluation,{independentPrecision:.87,unknownCount:0,packageExposed:false});for(const key of Object.keys(preview.value.evaluation.checks))preview.value.evaluation.checks[key]=true;evaluationChanged()}
function exposePackage(){preview.value.evaluation.packageExposed=true;evaluationChanged()}
function stop(type){if(type==='validated'&&!gate.value.validated)return;if(type!=='validated'&&!preview.value.stopReason.trim())return;preview.value.stopDecision={type,reason:type==='validated'?'调优与独立验收均满足双85%':preview.value.stopReason,metrics:{...preview.value.evaluation},decidedAt:new Date().toISOString()};preview.value.stepStates.evaluation='complete';preview.value.stepStates.corpus='current';preview.value.activeStep=6}
function freezeCorpus(){if(!corpusReady.value)return;preview.value.corpusFrozen=true;preview.value.stepStates.corpus='complete';preview.value.stepStates.analysis='current';preview.value.activeStep=7}
function resetPreview(){preview.value=clearPreview(selected.value)}
function copyQuery(value){navigator.clipboard?.writeText(value)}
const percent=value=>`${(Number(value)*100).toFixed(1)}%`
</script>

<template>
  <div v-if="booting" class="loading-screen">正在连接研究工作台…</div>
  <LoginPanel v-else-if="!session.authenticated&&!demoMode" :busy="busy" :error="error" @login="login" @demo="loadDemo"/>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand"><b>AI4S</b><span>Research Decision</span></div>
      <section class="project-switcher"><span class="overline light">PROJECTS</span><button v-for="project in projects" :key="project.id" :class="['project-option',{active:selected?.id===project.id}]" @click="selectProject(project)"><b>{{project.name}}</b><small>{{project.demo?'示例项目':'真实项目 · V'+project.revision}}</small></button><button v-if="session.authenticated" class="new-project" @click="showCreate=true">＋ 新建项目</button></section>
      <nav class="module-nav" aria-label="平台模块"><button v-for="area in stages" :key="area[0]" :class="{active:moduleArea===area[0]}" @click="moduleArea=area[0]">{{area[1]}}</button></nav>
      <div class="account"><b>{{session.username}}</b><small>{{demoMode?'身份与权限预览':'受邀账号 · 同域会话'}}</small><button v-if="session.authenticated" @click="showAccount=!showAccount">账号与成员／恢复</button><button v-if="session.authenticated" @click="logout">退出登录</button><button v-else @click="demoMode=false;selected=null;preview=null">退出示例</button></div>
    </aside>

    <main v-if="selected&&preview" class="main-area">
      <header class="topbar"><div><span class="overline">PROJECT / {{selected.demo?'DEMO':'V'+selected.revision}}</span><h1>{{selected.name}}</h1><p>{{selected.direction}}</p></div><div class="header-actions"><PreviewBadge v-if="selected.demo"/><button class="secondary" @click="resetPreview">清除本次预览</button><button v-if="session.authenticated" class="primary" @click="showCreate=true">＋ 新建项目</button></div></header>
      <div class="preview-banner"><b>{{selected.demo?'示例流程':'M0 入口与范围'}}</b><span>{{selected.demo?'所有产物仅供交互预览。':'账号、项目和范围版本保存在服务器。后续阶段为交互预览，尚未启用正式业务。'}}</span></div>
      <AccountPanel v-if="showAccount&&session.authenticated" :key="selected.id" :session="session" :project="selected" @revoked="logout" @updated="revisionUpdated"/>
      <WorkflowStepper :active="activeStep" :states="preview.stepStates" @select="chooseStep"/>

      <div class="content-grid">
        <section class="workbench">
          <div class="section-heading"><div><span class="overline">STEP {{currentStep.number}} / 8</span><h2>{{currentStep.label}}</h2></div><span :class="['status-pill',preview.stepStates[currentStep.id]]">{{statusLabel(preview.stepStates[currentStep.id])}}</span></div>
          <p v-if="operationBlocked" class="locked-notice">可查看本步预览；完成前序步骤后才能操作。</p>
          <div :class="{'locked-panel':operationBlocked}" :inert="operationBlocked||undefined">

          <div v-if="currentStep.id==='project'" class="panel-stack">
            <article class="card"><span class="overline">PROJECT BRIEF</span><h3>{{selected.name}}</h3><p>{{selected.direction}}</p><div class="tag-row"><span v-for="term in selected.core_keywords" :key="term" class="tag">{{term}}</span></div><dl class="facts"><div><dt>项目版本</dt><dd>V{{selected.revision}}</dd></div><div><dt>范围版本</dt><dd>草稿 V{{selected.scope_version||1}}</dd></div><div><dt>数据位置</dt><dd>{{selected.demo?'示例命名空间':'服务器项目'}}</dd></div></dl></article>
            <article class="card source-card"><PreviewBadge :label="selected.demo?'示例项目 · 非服务器数据':'真实项目元数据 · 后续步骤为交互预览'"/><h3>下一步：确认研究边界</h3><p>核心关键词只是范围访谈的起点，不会自动成为因果结论或已执行检索式。</p><button class="primary" @click="chooseStep(1)">进入范围与概念 →</button></article>
          </div>

          <ScopePanel v-else-if="currentStep.id==='scope'&&!selected.demo" :key="selected.id" :project="selected" :drafts="scopeDrafts" @saved="scopeSaved"/>
          <div v-else-if="currentStep.id==='scope'" class="panel-stack">
            <article v-for="group in scopeGroups" :key="group.title" class="card"><div class="card-title"><span class="overline">SCOPE INTERVIEW</span><PreviewBadge label="浏览器范围草稿 · 未写入服务器"/></div><h3>{{group.title}}</h3><div class="form-grid"><label v-for="field in group.fields" :key="field[0]">{{field[1]}}<input v-model="preview.scope[field[0]]" @change="updateScope"></label></div></article>
            <article class="card"><div class="card-title"><div><span class="overline">CONCEPT CANDIDATES</span><h3>候选词逐条决定</h3></div><PreviewBadge/></div><div class="suggestion" v-for="item in preview.suggestions" :key="item.id"><div><b>{{item.term}}</b><small>{{item.source}}</small></div><div><button :class="{chosen:item.decision==='accepted'}" @click="setSuggestion(item,'accepted')">接受</button><button :class="{chosen:item.decision==='modified'}" @click="setSuggestion(item,'modified')">修改后接受</button><button :class="{chosen:item.decision==='rejected'}" @click="setSuggestion(item,'rejected')">拒绝</button></div></div><label class="check-line"><input v-model="preview.scope.conflictsResolved" type="checkbox" @change="updateScope"> 已人工检查年份、类型和纳排条件，当前无未处理矛盾</label><div class="card-actions"><span>{{preview.scope.confirmed?'范围已确认；修改会使下游需重新验证。':scopeComplete?'必填范围已完整，请人工确认。':'请补全范围、处理所有候选词并确认无矛盾。'}}</span><button class="primary" :disabled="!scopeComplete" @click="confirmScope">确认范围 V{{(selected.scope_version||1)+(preview.scope.confirmed?1:0)}}</button></div></article>
          </div>

          <div v-else-if="currentStep.id==='platforms'" class="panel-stack">
            <article class="card"><div class="card-title"><div><span class="overline">PLATFORM CATALOG</span><h3>选择一个或多个检索目标</h3></div><span class="count-badge">21个平台</span></div><details v-for="(items,group) in groupedPlatforms" :key="group" :open="['中文文献','医学/生物','专利'].includes(group)"><summary>{{group}} <small>{{items.length}}</small></summary><div class="platform-grid"><label v-for="item in items" :key="item.id" :class="['platform-option',{selected:preview.selectedPlatforms.includes(item.id)}]"><input type="checkbox" :checked="preview.selectedPlatforms.includes(item.id)" @change="togglePlatform(item.id)"><span><b>{{item.name}}</b><small>{{item.ruleState}}</small></span><i>{{item.full?'完整示例':'目录'}}</i></label></div></details></article>
            <article v-for="id in preview.selectedPlatforms" :key="id" class="card query-card"><div class="card-title"><div><span class="overline">{{platformById(id).name}}</span><h3>{{platformById(id).full?'平台检索式示例':'规范逻辑草稿'}}</h3></div><PreviewBadge :label="platformById(id).full?'示例规则 · 执行前核对':'规则待核对 · 不可执行'"/></div><div class="target-meta"><span>子库：{{id==='wos'?'Core Collection':'默认集合待确认'}}</span><span>入口：高级检索</span><span>合并：平台内OR，平台间并集</span><span>规则：Preview-1</span></div><textarea v-model="preview.queries[id]" rows="3" @input="queryChanged"></textarea><div class="six-checks"><span v-for="label in ['平台规则','语法能力','语义一致','实际执行','回传完整','Gold/查准']" :key="label" :class="platformById(id).full&&label!=='实际执行'?'pass':'pending'">{{label}}</span></div><button class="text-button" @click="copyQuery(preview.queries[id])">复制检索式</button></article>
            <div class="sticky-actions"><span v-if="!preview.selectedPlatforms.length">至少选择一个平台。</span><span v-else-if="preview.queryDirty">检索式已修改，旧检查与执行状态已失效；已保留 {{preview.history.length}} 条只读历史。</span><span v-else>已选择 {{preview.selectedPlatforms.length}} 个目标。</span><button class="primary" :disabled="!preview.selectedPlatforms.length" @click="confirmPlatforms">确认平台目标 →</button></div>
          </div>

          <div v-else-if="currentStep.id==='exploration'" class="panel-stack">
            <article class="card"><div class="card-title"><div><span class="overline">EXTERNAL EXECUTION</span><h3>登记外部平台实际操作</h3></div><PreviewBadge/></div><div class="form-grid"><label>原样执行式<textarea v-model="preview.execution.executedQuery" rows="3" placeholder="粘贴平台实际接受或改写后的表达式"></textarea></label><label>执行时间<input v-model="preview.execution.executedAt" type="datetime-local"></label><label>平台命中量<input v-model.number="preview.execution.hits" type="number" min="0"></label><label>实际导出量<input v-model.number="preview.execution.exported" type="number" min="0"></label><label>排序方式<input v-model="preview.execution.sort"></label><label>过滤条件<input v-model="preview.execution.filters"></label></div><label class="check-line"><input v-model="preview.execution.truncated" type="checkbox"> 导出被截断或不是全部结果</label></article>
            <article class="card upload-card"><span class="overline">LOCAL FILE METADATA</span><h3>选择回传文件</h3><input type="file" accept=".csv,.json,.ris,.bib,.txt" @change="fileChosen"><div v-if="preview.execution.file" class="file-meta"><b>{{preview.execution.file.name}}</b><span>{{preview.execution.file.size}} bytes · {{preview.execution.file.type}}</span><PreviewBadge label="仅读取名称、大小和类型 · 未上传、未解析"/></div><p v-else>选择文件只用于体验界面，不读取正文或题录内容。</p></article>
            <div class="sticky-actions"><span>{{executionReady?(preview.execution.truncated?'当前为部分回传，不能证明未命中或正式查准。':'完整性仍需服务器解析后核验。'):'需填写执行式、时间、有效数量并选择回传文件。'}}</span><button class="primary" :disabled="!executionReady" @click="recordExploration">记录示例回传 →</button></div>
          </div>

          <div v-else-if="currentStep.id==='seeds'" class="panel-stack">
            <div class="metric-grid"><article class="metric"><PreviewBadge/><span>高被引种子</span><b>{{preview.seeds.highlyCited}}</b><small>引用来源与日期待真实导入</small></article><article class="metric"><PreviewBadge/><span>一区最新种子</span><b>{{preview.seeds.latestQ1}}</b><small>分区体系与年度待核对</small></article><article class="metric"><PreviewBadge/><span>去重后记录</span><b>{{preview.seeds.deduped}}</b><small>双标签保留</small></article></div>
            <article class="card"><span class="overline">SEED TRACEABILITY</span><h3>缺额与重叠说明</h3><p>{{preview.seeds.shortfall}}</p><div class="knowledge-preview"><div><h4>概念词表</h4><div class="tag-row"><span v-for="term in preview.seeds.concepts" :key="term" class="tag accepted">{{term}}</span></div></div><div class="mini-graph" aria-label="基础知识关系示意"><span>铁死亡</span><i>脂质过氧化</i><b>GPX4</b><em>SLC7A11</em></div></div><PreviewBadge label="示例词表与关系 · 未调用图谱或模型"/></article>
            <div class="sticky-actions"><span>种子用于知识启动，不代表领域统计总体。</span><button class="primary" @click="confirmSeeds">确认示例种子与知识 →</button></div>
          </div>

          <div v-else-if="currentStep.id==='evaluation'" class="panel-stack">
            <article class="card"><div class="card-title"><div><span class="overline">EVALUATION PACKAGE</span><h3>调优包与独立验收包</h3></div><PreviewBadge/></div><div class="gold-counts"><label>有效Gold<input v-model.number="preview.evaluation.validGold" type="number" @change="evaluationChanged"></label><label>正例<input v-model.number="preview.evaluation.positiveGold" type="number" @change="evaluationChanged"></label><label>负例回归<input v-model.number="preview.evaluation.negativeGold" type="number" @change="evaluationChanged"></label><label>unknown<input v-model.number="preview.evaluation.unknownCount" type="number" @change="evaluationChanged"></label></div><p class="callout">Gold负例只检查误检回归，不进入实际结果集查准率分母。20篇反馈是固定随机种子的调优诊断，也不代替正式查准样本。</p></article>
            <div class="evaluation-grid"><article class="card"><span class="overline">TUNING</span><h3>调优阶段</h3><label>Gold正例查全率 <input v-model.number="preview.evaluation.tuningRecall" type="number" step="0.0001" min="0" max="1" @change="evaluationChanged"></label><label>实际结果查准率 <input v-model.number="preview.evaluation.tuningPrecision" type="number" step="0.0001" min="0" max="1" @change="evaluationChanged"></label><div class="metric-line"><b>{{percent(preview.evaluation.tuningRecall)}}</b><b>{{percent(preview.evaluation.tuningPrecision)}}</b></div></article><article class="card"><span class="overline">INDEPENDENT</span><h3>独立验收阶段</h3><label>Gold正例查全率 <input v-model.number="preview.evaluation.independentRecall" type="number" step="0.0001" min="0" max="1" @change="evaluationChanged"></label><label>分层样本查准率 <input v-model.number="preview.evaluation.independentPrecision" type="number" step="0.0001" min="0" max="1" @change="evaluationChanged"></label><div class="metric-line"><b>{{percent(preview.evaluation.independentRecall)}}</b><b class="danger">{{percent(preview.evaluation.independentPrecision)}}</b></div><small>总体800条 · 固定样本120条 · seed 20260911 · 95% CI待真实计算</small></article></div>
            <article class="card"><div class="card-title"><div><span class="overline">SIX GATES</span><h3>六类检查</h3></div><span :class="['status-pill',gate.validated?'complete':'blocked']">{{gate.validated?'全部合格':'存在阻断'}}</span></div><div class="check-grid"><label v-for="(value,key) in preview.evaluation.checks" :key="key"><input v-model="preview.evaluation.checks[key]" type="checkbox" @change="evaluationChanged"> {{({rules:'平台规则',syntax:'语法能力',semantic:'语义一致',execution:'实际执行',return:'回传完整',quality:'Gold/查准质量'})[key]}}</label></div><ul class="blocker-list"><li v-for="item in gate.blockers" :key="item">{{item}}</li></ul><div class="button-row"><button class="secondary" @click="repairEvaluation">应用合格边界示例</button><button class="secondary" @click="exposePackage">模拟验收包暴露</button></div></article>
            <article class="card"><span class="overline">SEARCH STOP DECISION</span><h3>停止本轮检索</h3><label>非通过停止原因<textarea v-model="preview.stopReason" rows="2" placeholder="说明覆盖限制和下一动作"></textarea></label><div class="stop-grid"><button class="primary" :disabled="!gate.validated" @click="stop('validated')">验证通过</button><button :disabled="!preview.stopReason.trim()" @click="stop('user_stopped')">用户提前停止</button><button :disabled="!preview.stopReason.trim()" @click="stop('externally_blocked')">外部条件阻断</button><button :disabled="!preview.stopReason.trim()" @click="stop('scope_superseded')">范围调整后终止</button></div></article>
          </div>

          <div v-else-if="currentStep.id==='corpus'" class="panel-stack">
            <article class="card"><div class="card-title"><div><span class="overline">DATASET SNAPSHOT</span><h3>语料口径确认</h3></div><PreviewBadge/></div><div class="funnel"><div v-for="(value,key) in preview.corpus" :key="key"><b>{{value}}</b><span>{{({platformHits:'平台命中',imported:'实际导入',deduped:'跨平台去重',included:'用户纳入',analyzable:'当前可分析'})[key]}}</span></div></div><p class="callout">停止决定：{{preview.stopDecision?.type||'尚未记录'}}。停止检索不会自动生成语料快照；部分回传仍需补充题录或保留覆盖限制。</p><label class="check-line"><input v-model="preview.corpusChecks.inclusion" type="checkbox"> 纳排口径已人工确认</label><label class="check-line"><input v-model="preview.corpusChecks.dedupe" type="checkbox"> 去重结果已人工确认</label></article><div class="sticky-actions"><span>{{preview.corpusFrozen?'快照预览已冻结，历史停止决定保持不变。':corpusReady?'人工口径已确认，可冻结预览。':'需先记录停止决定并确认纳排与去重口径。'}}</span><button class="primary" :disabled="!corpusReady" @click="freezeCorpus">冻结语料预览 →</button></div>
          </div>

          <div v-else class="panel-stack">
            <article class="card"><div class="card-title"><div><span class="overline">CAPABILITY ASSESSMENT</span><h3>逐模块分析准入</h3></div><PreviewBadge/></div><div class="capability-list"><div v-for="item in preview.capabilities" :key="item.name" class="capability"><div><b>{{item.name}}</b><small>{{item.connection}}</small></div><span :class="['status-pill',item.status]">{{statusLabel(item.status)}}</span></div></div><p class="callout">即使显示“预计可用”，也只代表示例条件判断；当前没有执行统计、引文或PDF分析。</p></article>
            <article class="card"><span class="overline">EVIDENCE STATES</span><h3>证据状态分别表达</h3><div class="evidence-grid"><div v-for="state in evidenceStates" :key="state.id"><b>{{state.label}}</b><p>{{state.detail}}</p><PreviewBadge label="状态解释示例"/></div></div></article>
          </div>
          </div>
        </section>

        <aside class="context-panel"><span class="overline">CURRENT CONTEXT</span><h3>当前步骤摘要</h3><dl><div><dt>范围版本</dt><dd>V{{selected.scope_version||1}}</dd></div><div><dt>当前产物</dt><dd>{{currentStep.label}}</dd></div><div><dt>保存位置</dt><dd>{{['project','scope'].includes(currentStep.id)&&!selected.demo?'服务器（编辑须保存）':'本标签页预览'}}</dd></div></dl><h4>阻断与恢复</h4><div v-if="sideBlockers.length" class="mini-blocker" v-for="item in sideBlockers" :key="item.code"><b>{{item.message}}</b><small>{{item.recovery}}</small><code>{{item.code}}</code></div><p v-else class="empty-note">本步骤没有已知阻断。</p><details><summary>科研规则详情</summary><p>页面状态是流程投影。正式判断仍由对应范围、平台执行、评估包、语料快照和分析能力对象决定。</p></details></aside>
      </div>
    </main>

    <div v-else class="empty-project"><div><span class="overline">NO PROJECT YET</span><h1>从一个研究方向开始</h1><p>创建项目只需要名称、研究方向和至少一个核心关键词。</p><button class="primary" @click="showCreate=true">＋ 新建项目</button><button class="text-button" @click="loadDemo">加载示例流程</button></div></div>
    <AccountPanel v-if="showAccount&&session.authenticated&&!selected" :session="session" @revoked="logout"/>
    <div v-if="showCreate" class="modal" @click.self="showCreate=false"><ProjectForm :busy="busy" :server-error="error" @submit="createProject" @cancel="showCreate=false"/></div>
  </div>
</template>
