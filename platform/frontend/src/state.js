export const stages = [
  ['overview','项目'],['retrieval','检索工作台'],['gold','Gold 评估'],['navigation','研究导航'],
  ['evidence','证据与空白'],['decision','选题决策'],['assets','图谱后台'],['monitor','监测与任务']
]

export const workflowSteps = [
  {id:'project', number:1, label:'项目信息', short:'建项'},
  {id:'scope', number:2, label:'范围与概念', short:'范围'},
  {id:'platforms', number:3, label:'检索平台', short:'平台'},
  {id:'exploration', number:4, label:'探索检索', short:'探索'},
  {id:'seeds', number:5, label:'种子与知识构建', short:'知识'},
  {id:'evaluation', number:6, label:'Gold与正式检索', short:'评估'},
  {id:'corpus', number:7, label:'语料确认', short:'语料'},
  {id:'analysis', number:8, label:'统计与引文分析', short:'分析'},
]

export function statusLabel(value){return ({
  qualified:'已通过', blocked:'阻断', unconfigured:'待配置', unknown:'未核验', ready:'可继续',
  complete:'已完成', current:'当前步骤', locked:'待前序完成', needs_revalidation:'需重新验证',
  enabled:'预计可用', exploratory_only:'仅探索', validated:'双85%已验证', not_started:'未开始'
})[value]||value}

export function nextAction(item){return item.recovery||'查看依赖和核查记录'}

export const workAreas = {
  overview:{kicker:'PROJECT CONTROL',title:'项目依赖与版本',description:'从轻量建项进入八步研究流程。',actions:['新建项目','查看范围版本']},
  retrieval:{kicker:'REPRODUCIBLE RETRIEVAL',title:'规范逻辑树与人工执行',description:'选择平台规则，生成检索式并记录真实执行条件。',actions:['选择检索平台','登记人工执行']},
  gold:{kicker:'TWO-SOURCE EVALUATION',title:'Gold查全与结果集查准',description:'Gold正例衡量查全，实际结果样本衡量查准。',actions:['检查Gold资格','查看独立验收包']},
  navigation:{kicker:'FIXED CORPUS',title:'统计导航与独立切面',description:'报告绑定语料、字段、切面、方法和随机种子。',actions:['查看能力准入','查看分析说明']},
  evidence:{kicker:'TRACEABLE EVIDENCE',title:'证据与七类空白',description:'未检索到、不足和冲突分别保留依据。',actions:['查看证据状态','查看空白矩阵']},
  decision:{kicker:'VALIDATED CANDIDATES',title:'三关与决策包',description:'候选经补查、可行性及专家核查后进入定题。',actions:['比较候选','查看停止条件']},
  assets:{kicker:'CONTROLLED KNOWLEDGE',title:'图谱贡献与授权',description:'私人提取与共享资产保持权限隔离。',actions:['查看项目图谱','了解贡献规则']},
  monitor:{kicker:'RELIABLE EXECUTION',title:'任务与持续监测',description:'固定版本执行，失败与人工待办均可恢复。',actions:['查看任务状态','查看监测待办']}
}

const item = (id,name,group,full=false) => ({id,name,group,full,ruleState:full?'示例规则已成形，实际执行前仍需平台核对':'目录可选，规则待核对'})
export const platforms = [
  item('cnki','中国知网 CNKI','中文文献',true), item('wanfang','万方数据','中文文献'), item('cqvip','维普中文期刊','中文文献'),
  item('wos','Web of Science','综合外文',true), item('scopus','Scopus','综合外文'), item('proquest','ProQuest','综合外文'), item('ebsco','EBSCOhost','综合外文'), item('sciencedirect','ScienceDirect','综合外文'), item('springer','Springer Link','综合外文'), item('wiley','Wiley Online','综合外文'), item('arxiv','arXiv','综合外文'),
  item('pubmed','PubMed','医学/生物',true), item('embase','Embase','医学/生物'),
  item('ieee','IEEE Xplore','工程/计算机/电子'), item('acm','ACM Digital Library','工程/计算机/电子'), item('spie','SPIE','工程/计算机/电子'),
  item('jstor','JSTOR','人文社科'), item('muse','Project MUSE','人文社科'), item('sage','SAGE','人文社科'), item('taylor-francis','Taylor & Francis','人文社科'),
  item('patsnap','智慧芽','专利',true)
]

export const evidenceStates = [
  {id:'not_retrieved',label:'尚未检索到证据',detail:'在已记录范围和覆盖内未检索到，不能解释为不存在。'},
  {id:'insufficient',label:'证据不足',detail:'已有材料无法支持稳定判断，需要补充数据或验证。'},
  {id:'conflicting',label:'证据相互冲突',detail:'不同研究给出不一致结果，需要分析条件差异。'},
]

export function demoProject(){
  return {
    id:'demo-ferroptosis', name:'铁死亡介导癌症放疗抵抗', direction:'铁死亡与肿瘤放疗抵抗的机制及干预',
    core_keywords:['铁死亡','ferroptosis','放疗抵抗','radioresistance'], revision:1, scope_version:1, scope_status:'draft', demo:true,
    workflow:{current_step:'evaluation',step_states:{project:'complete',scope:'complete',platforms:'complete',exploration:'complete',seeds:'complete',evaluation:'current',corpus:'locked',analysis:'locked'},blocking_items:[{code:'INDEPENDENT_PRECISION_LOW',message:'独立验收查准率为84.96%',recovery:'检查误检记录并建立新查询版本'}]}
  }
}
