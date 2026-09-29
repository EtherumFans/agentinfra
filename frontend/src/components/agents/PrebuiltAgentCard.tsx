import {Bot, FileText, ShieldCheck, Stethoscope, Loader2, ArrowUpRight} from 'lucide-react';
import type {HubCard} from '../../services/agentHubApi';
import './PrebuiltAgentCard.css';

// Product summaries describe the existing capabilities without exposing runtime metadata.
export const summaries:Record<string,string>={
 'medical-coding-agent':'根据病历生成诊断与手术编码建议，附上依据和待核对事项。',
 'clinical-documentation-improvement-agent':'找出病历中需要澄清的内容，整理给医生确认的问题。',
 'note-completeness-agent':'检查入院记录的必填章节，列出缺失或未填写的内容。',
 'diagnosis-extractor':'从病历中提取已记录的诊断，并标明疑似、否定或既往状态。',
 'procedure-extractor':'提取病历中的手术与操作，区分已完成、计划和取消等状态。',
 'code-validation-agent':'对照本地编码目录，检查诊断与手术编码是否存在、能否选用。',
 'compliance-guardrail-agent':'检查编码中的规则冲突，整理需要复核的问题。',
 'principal-diagnosis-review':'核对主诊断初稿、候选编码与病历依据是否完整对应。',
 'drg-analyzer':'检查已有编码中的 DRG/DIP 规则风险，供人工复核。',
 'icd10-navigator':'按关键词查找 ICD-10 编码，浏览相关目录条目。',
 'rule-explainer':'查看编码的名称、所属章节和层级，了解目录中的含义。',
 'evidence-extractor':'在病历原文中定位候选编码或对应术语，方便回查。',
 'evidence-ranker':'按来源和原文位置整理证据，方便逐项查阅。',
 'claim-check':'汇总结算资料、病历依据和支付政策，准备提交前核查材料。',
 'denial-appeals':'根据拒付记录和已有资料，整理申诉草案或更正清单。',
 'prior-auth':'汇总申请项目、病历依据和支付政策，准备预授权材料。',
 'discharge-summary-structuring':'按已有章节整理出院小结，便于查阅和后续处理。',
 'discharge-edu':'整理已记录的出院事项，形成便于核对的宣教内容。',
 'icu-summary':'汇总已记录的 ICU 入院信息，便于快速查阅。',
 'nursing-handoff':'整理护理交班信息，突出待办事项和已记录的安全提醒。',
 'med-reconciliation':'对照入院、住院和出院用药记录，列出药物与用法差异。',
 'referral-gen':'根据已有转诊资料，整理供医师核对的转诊信草稿。',
 'clinical-education':'从医院批准的资料中整理教学要点和知识检查问题。',
 'clinical-guidelines':'对照医院批准的指南条款，逐项核对已记录的病例信息。',
 'surgical-registry':'从手术记录中整理外科质控登记所需的信息。',
 'triage':'核对急诊分诊问卷的回答与原文依据，检查问卷分支路径。',
};

export default function PrebuiltAgentCard({card,locale,cloning,onUse,onDetails}:{card:HubCard;locale:string;cloning:boolean;onUse:()=>void;onDetails:()=>void}){
 const zh=locale==='zh-CN';
 const id=card.agent_id||card.agent_ref.split('/').pop()?.split('@')[0]||'';
 const name=zh?card.name.replace(/智能体\s*/g,'').trim():card.name;
 const description=zh?(summaries[id]||'查看用途与所需资料，选择适合当前任务的智能体。'):card.description.split(/[.!]\s/)[0];
 const ready=card.runnable&&card.runtime_readiness?.run_action_enabled===true&&!['coming_soon','deprecated'].includes(card.display_status);
 const status=card.display_status==='deprecated'?(zh?'已停用':'Retired'):card.display_status==='coming_soon'?(zh?'即将推出':'Coming soon'):(zh?'暂不可用':'Unavailable');
 const Icon=/coding|diagnosis|procedure|icd10/.test(id)?Stethoscope:/check|review|validation|guardrail|triage/.test(id)?ShieldCheck:/summary|documentation|note|discharge|referral/.test(id)?FileText:Bot;
 return <article className="prebuilt-agent-card" aria-label={name}>
   <div className="prebuilt-agent-card-top"><span className="prebuilt-agent-icon"><Icon size={22} strokeWidth={1.6}/></span>{!ready&&<span className="prebuilt-agent-status">{status}</span>}</div>
   <h3>{name}</h3><p className="prebuilt-agent-description">{description}</p>
   <div className="prebuilt-agent-actions">
     <button className="prebuilt-agent-use" disabled={!ready||cloning} onClick={onUse}>{cloning?<><Loader2 size={14} className="animate-spin"/>{zh?'准备中…':'Preparing…'}</>:zh?'使用':'Use'}</button>
     <button className="prebuilt-agent-details" onClick={onDetails}>{zh?'查看详情':'Details'}<ArrowUpRight size={14}/></button>
   </div>
 </article>;
}
