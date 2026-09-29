import {useEffect,useRef,useState} from 'react';
import {validateTaskInput} from './TaskInputEditor';
import api from '../../services/api';

export function parseEvaluationImport(raw:string){
 let parsed:any;try{parsed=JSON.parse(raw.replace(/^\uFEFF/,''));}catch{throw new Error('JSON 格式不正确，请使用下载的模板填写。');}
 const cases=Array.isArray(parsed)?parsed:parsed?.cases;
 const normalized=JSON.stringify(cases);
 const error=validateTaskInput(normalized,'evaluation');if(error)throw new Error(error);
 const allowed=new Set(['id','text','contains','excludes','expected_fields','expected_json']);
 cases.forEach((c:any,i:number)=>{if(Object.keys(c).some(k=>!allowed.has(k)))throw new Error(`第 ${i+1} 条含不支持的字段，请对照模板检查。`);});
 return cases;
}
export function downloadEvaluation(value:any,name:string){
 const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),0);
}
const template=[{id:'case-001',text:'请替换为脱敏资料，并明确智能体需要完成的任务。',contains:['请替换为应包含的内容'],excludes:[],expected_fields:{}}];

export default function EvaluationImport({suites,disabled,onApply,base}:{suites:any[];disabled?:boolean;onApply:(value:string)=>void;base:string}){
 const [selected,setSelected]=useState('documentation-v1'),[preview,setPreview]=useState<any[]|null>(null),[error,setError]=useState(''),[reading,setReading]=useState(false);
 const generation=useRef(0);useEffect(()=>()=>{generation.current++;},[]);
 const [start,setStart]=useState(1),[count,setCount]=useState(10),[sourceInfo,setSourceInfo]=useState('');
 const example=suites.find(s=>s.id===selected);
 async function importFile(file?:File){
  const ticket=++generation.current;setError('');setPreview(null);setReading(false);setSourceInfo('');if(!file)return;
  const excel=file.name.toLowerCase().endsWith('.xlsx');
  if(excel&&(!Number.isInteger(start)||start<1||start>20000||!Number.isInteger(count)||count<1||count>10)){setError('Excel 起始记录须为 1–20000，选取条数须为 1–10 的整数。');return;}
  if(file.size>(excel?10:1)*1024*1024){setError(excel?'Excel 文件不能超过 10 MB。':'JSON 文件不能超过 1 MB。');return;}
  if(!excel&&!file.name.toLowerCase().endsWith('.json')){setError('请上传 JSON 或 XLSX 文件。');return;}
  setReading(true);try{
   if(excel){
    const body=new FormData();body.append('file',file);body.append('start',String(start));body.append('limit',String(count));
    const r=await api.post(`${base}/evaluation-import`,body,{timeout:60000});if(ticket!==generation.current)return;
    setSourceInfo(`数据表共 ${r.data.total_rows} 条记录；本次选择第 ${r.data.start} 条起的 ${r.data.selected_count} 条。`);
    if(r.data.issues?.length){setError(r.data.issues.map((i:any)=>`第 ${i.record} 条：${i.message}`).join(' '));return;}
    setPreview(parseEvaluationImport(JSON.stringify(r.data.cases)));
   }else{const raw=await file.text();if(ticket!==generation.current)return;setPreview(parseEvaluationImport(raw));}
  }
  catch(e:any){if(ticket===generation.current)setError(typeof e?.response?.data?.detail==='string'?e.response.data.detail:e instanceof Error?e.message:'文件读取失败。');}
  finally{if(ticket===generation.current)setReading(false);}
 }
 return <section className="inspector-card space-y-3" aria-label="导入业务评测样例">
 <h2 className="font-semibold">准备业务评测样例</h2>
 <p className="text-sm text-muted-foreground">下载模板填写脱敏资料和预期结果，或从合成示例开始。支持 JSON（不超过 1 MB）和病历编码 XLSX（不超过 10 MB），每次使用 1–10 条。</p>
 <div className="flex flex-wrap gap-3 items-center">
 <button type="button" onClick={()=>downloadEvaluation(template,'icoder-evaluation-template.json')}>下载填写模板</button>
 <label>合成示例 <select aria-label="合成示例类别" value={selected} onChange={e=>setSelected(e.target.value)}><option value="documentation-v1">文书处理</option><option value="coding-v1">医学编码</option><option value="quality-v1">质量审核</option></select></label>
 <button type="button" disabled={!example} onClick={()=>downloadEvaluation(example.cases,`icoder-${selected}-synthetic.json`)}>下载合成示例</button>
 <button type="button" disabled={disabled||!example} onClick={()=>{generation.current++;setReading(false);setError('');setPreview(parseEvaluationImport(JSON.stringify(example.cases)));}}>预览合成示例</button>
 <label>导入样例文件<input aria-label="导入评测集文件" type="file" accept=".json,.xlsx" disabled={disabled} onChange={e=>{void importFile(e.target.files?.[0]);e.target.value='';}}/></label>
 </div>
 <div className="flex flex-wrap gap-3 text-sm"><label>Excel 起始记录<input type="number" aria-label="Excel 起始记录" min={1} max={20000} disabled={disabled||reading} value={start} onChange={e=>setStart(Number(e.target.value))} className="border rounded-lg p-1 w-24"/></label><label>选取条数<input type="number" aria-label="Excel 选取条数" min={1} max={10} disabled={disabled||reading} value={count} onChange={e=>setCount(Number(e.target.value))} className="border rounded-lg p-1 w-20"/></label></div>
 <details><summary>Excel 编码训练集格式</summary><p className="text-sm">首行为列名，正文使用主诉、现病史、既往史、个人史、婚姻史、家族史、入院情况、入院诊断、诊疗经过、出院情况、出院医嘱、手术经过、术前诊断、术中诊断。答案列为：主要疾病（诊断）编码、其他疾病（诊断）编码、主要手术编码、其他手术编码。编码按文本填写，多个其他编码用分号分隔。组合编码中的加号（+）和末尾星号（*）会原样保留，不拆成多个答案。病案标识不会进入样例，答案列不会进入模型输入。空单元格和“无”等明确空值标记作为无编码处理，导入后需核对。首条数据记为第 1 条。</p></details>
 <details><summary>填写说明</summary><ul className="text-sm list-disc pl-5 space-y-1"><li>id 是唯一标识；text 包含脱敏资料和任务要求。</li><li>contains / excludes 分别填写应包含和不应包含的短语。</li><li>expected_json 严格比较模型输出的 JSON 对象，包括字段类型、值与额外字段；expected_fields 比较运行结果的字段路径。至少填写一种检查。</li><li>模板中的提示文字必须替换。合成示例仅供学习格式，正式预期结果需业务人员确认。</li></ul></details>
 {reading&&<p role="status">正在读取文件…</p>}{sourceInfo&&<p role="status">{sourceInfo}</p>}{error&&<p role="alert">{error} 当前评测内容未被替换。</p>}
 {preview&&<div className="rounded-xl border p-3 space-y-3"><p>待导入 {preview.length} 条样例，请检查资料和预期结果。确认后会替换当前编辑内容并切换到自定义规则。</p>{preview.map(c=><details key={c.id}><summary>{c.id}</summary><p className="whitespace-pre-wrap break-words">{c.text}</p><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(Object.fromEntries(Object.entries(c).filter(([k])=>k!=='text'&&k!=='id')),null,2)}</pre></details>)}<button type="button" className="rounded-full bg-primary text-primary-foreground px-4 py-2" disabled={disabled} onClick={()=>{onApply(JSON.stringify(preview,null,2));setPreview(null);}}>使用这组样例</button><button type="button" onClick={()=>setPreview(null)}>取消导入</button></div>}
 <p className="text-xs text-muted-foreground">JSON 在浏览器解析；Excel 上传到当前服务解析，不持久保存原文件，也不调用模型。导入内容暂存在页面，刷新会丢失未导出的编辑。运行评测才会调用模型，请先核对脱敏情况和答案。自定义样例不会替代固定业务发布门禁；训练集应与正式验收集分开。</p>
 </section>;
}
