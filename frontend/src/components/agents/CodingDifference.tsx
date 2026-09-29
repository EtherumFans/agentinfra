import {useState} from 'react';
import './CodingDifference.css';
const fields:Record<string,string>={primary_diagnosis_code:'主要诊断',other_diagnosis_codes:'其他诊断',primary_procedure_code:'主要手术',other_procedure_codes:'其他手术'};
const labels:Record<string,string>={possible_role:'疑似主次位置不同',missing_field:'缺少字段',type_mismatch:'格式类型不同',order_only:'仅顺序不同',missing_codes:'有漏码',extra_codes:'有多码',possible_extension:'疑似扩展位差异'};
export default function CodingDifference({checks=[]}:{checks:any[]}){
 const [onlyFailed,setOnlyFailed]=useState(true);
 const rows=checks.filter(c=>fields[c.path]);
 if(!rows.length)return null;
 return <section className="coding-difference" aria-label="编码差异分析"><header><h3>编码对照</h3><label><input type="checkbox" checked={onlyFailed} onChange={e=>setOnlyFailed(e.target.checked)}/>仅看差异</label></header>
 <p>严格匹配 {rows.filter(c=>c.passed).length}/{rows.length} 项。差异提示用于定位问题，不改变评分。</p>
 {onlyFailed&&rows.every(c=>c.passed)&&<p>编码字段均严格匹配。</p>}
 {rows.filter(c=>!onlyFailed||!c.passed).map((c,index)=>{const d=c.coding_comparison;return <article key={c.path+index}><h4>{fields[c.path]} <small>{c.passed?'匹配':'未匹配'}</small></h4>{!d?.available?<p>{d?'编码值格式不受支持，未展示原始内容。':'此历史报告未保存编码对照数据，请查看运行证据；新评测将自动记录。'}</p>:<><div className="coding-difference-columns">{[['预期编码',d.expected,d.missing],['实际编码',d.actual,d.extra]].map(([title,values,changed]:any)=><div key={title}><strong>{title}</strong><div>{values.length?values.map((v:string,i:number)=><code className={changed.includes(v)?'coding-changed':''} key={i}>{v||'空值'}</code>):<span>{title==='实际编码'&&!d.actual_present?'字段缺失':'无编码'}</span>}</div></div>)}</div><p>{d.categories.length?d.categories.map((k:string)=>labels[k]||k).join(' · '):'严格匹配'}</p>{d.categories.includes('possible_extension')&&<p>仅发现编码前缀相同，需核对字典版本与原文依据。</p>}</>}</article>;})}
 </section>;
}
