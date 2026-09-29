import {useEffect,useRef,useState} from 'react';

type Props={value:string;onChange:(value:string)=>void;kind:'evaluation'|'jobs';disabled?:boolean;hideImport?:boolean};
export function validateTaskInput(value:string,kind:Props['kind']):string{
 let rows:any;try{rows=JSON.parse(value);}catch{return 'JSON 格式不正确，请检查括号和引号。';}
 const max=kind==='evaluation'?10:20;
 if(!Array.isArray(rows)||!rows.length||rows.length>max)return `请提供 1–${max} 条资料。`;
 const ids=new Set();
 for(let i=0;i<rows.length;i++){
  const r=rows[i],prefix=`第 ${i+1} 条：`;
  if(!r||typeof r!=='object'||Array.isArray(r)||typeof r.text!=='string'||!r.text.trim())return prefix+'请填写资料正文。';
  if(r.text.length>(kind==='evaluation'?16000:32000))return prefix+'正文超出长度限制。';
  if(kind==='evaluation'){
   if(typeof r.id!=='string'||!r.id.trim()||r.id.length>80||ids.has(r.id))return prefix+'样例标识须填写且不能重复（最多 80 字符）。';ids.add(r.id);
   for(const key of ['contains','excludes'])if(r[key]!==undefined&&(!Array.isArray(r[key])||r[key].length>20||r[key].some((v:any)=>typeof v!=='string'||!v.trim()||v.length>500)))return prefix+'检查短语须为 1–500 字符，每类最多 20 条。';
   if(r.expected_fields!==undefined&&(!r.expected_fields||typeof r.expected_fields!=='object'||Array.isArray(r.expected_fields)))return prefix+'字段检查必须是对象。';
   if(Object.keys(r.expected_fields||{}).length>20||JSON.stringify(r.expected_fields||{}).length>4000)return prefix+'字段检查超出限制。';
   if(r.expected_json!==undefined&&r.expected_json!==null&&(!r.expected_json||typeof r.expected_json!=='object'||Array.isArray(r.expected_json)))return prefix+'预期 JSON 必须是对象。';
   if(Object.keys(r.expected_json||{}).length>20||JSON.stringify([r.expected_fields||{},r.expected_json??null]).replace(/[^\x00-\x7F]/g,'xxxxxx').length>4000)return prefix+'预期结果超出限制。';
   if(!(r.contains?.length||r.excludes?.length||Object.keys(r.expected_fields||{}).length||Object.keys(r.expected_json||{}).length))return prefix+'至少添加一条检查规则。';
  }
 }
 return '';
}
export default function TaskInputEditor({value,onChange,kind,disabled,hideImport}:Props){
 const alive=useRef(true);useEffect(()=>{alive.current=true;return ()=>{alive.current=false;};},[]);
 const [advanced,setAdvanced]=useState(false),[importError,setImportError]=useState('');
 let rows:any[]=[];try{const parsed=JSON.parse(value);if(Array.isArray(parsed))rows=parsed;}catch{/* Keep invalid input editable in advanced mode. */}
 const error=validateTaskInput(value,kind),isEval=kind==='evaluation';
 const update=(next:any[])=>onChange(JSON.stringify(next,null,2));
 const change=(index:number,patch:any)=>update(rows.map((r,i)=>i===index?{...r,...patch}:r));
 async function importFile(file?:File){if(!file)return;setImportError('');if(file.size>1024*1024){setImportError('文件不能超过 1 MB。');return;}
  try{const raw=await file.text();if(!alive.current)return;const next=!isEval&&file.name.toLowerCase().endsWith('.txt')?JSON.stringify([{text:raw}]):raw;const invalid=validateTaskInput(next,kind);if(invalid){setImportError(invalid);return;}onChange(next);}catch{if(alive.current)setImportError('无法读取文件，请重试。');}}
 return <div className="space-y-3 min-w-0">
 <div className="flex flex-wrap gap-3"><button type="button" disabled={disabled} onClick={()=>setAdvanced(!advanced)}>{advanced?'切换到表单':'高级 JSON'}</button>
 {!hideImport&&<label>导入{isEval?'样例 JSON':'JSON / TXT'}<input aria-label="导入资料文件" type="file" accept={isEval?'.json':'.json,.txt'} disabled={disabled} onChange={e=>{void importFile(e.target.files?.[0]);e.target.value='';}}/></label>}</div>
 {importError&&<p role="alert">{importError}</p>}
 {advanced?<textarea aria-label={isEval?'评测样例 JSON':'批量文书 JSON'} disabled={disabled} className="w-full min-h-64 border rounded-md p-3 bg-background font-mono text-sm" value={value} onChange={e=>onChange(e.target.value)}/>:<>
 {rows.map((row,i)=><fieldset key={i} disabled={disabled} className="border rounded-xl p-3 space-y-3 min-w-0"><legend>第 {i+1} {isEval?'个样例':'份文书'}</legend>
 {isEval&&<label className="block">样例标识<input aria-label={`样例 ${i+1} 标识`} className="w-full border rounded-md p-2 bg-background" value={row?.id||''} onChange={e=>change(i,{id:e.target.value})}/></label>}
 <label className="block">资料正文<textarea aria-label={`资料 ${i+1} 正文`} className="w-full min-h-28 border rounded-md p-2 bg-background" value={row?.text||''} onChange={e=>change(i,{text:e.target.value})}/></label>
 {isEval&&<>{['contains','excludes'].map(key=><label className="block" key={key}>{key==='contains'?'应包含内容':'不应包含内容'}（每行一条）<textarea aria-label={`样例 ${i+1} ${key}`} className="w-full border rounded-md p-2 bg-background" value={Array.isArray(row?.[key])?row[key].join('\n'):''} onChange={e=>change(i,{[key]:e.target.value?e.target.value.split('\n'):[]})}/></label>)}
 <label className="block">预期模型 JSON（可选）<textarea aria-label={`样例 ${i+1} 预期 JSON`} className="w-full border rounded-md p-2 bg-background font-mono text-sm" value={typeof row?.expected_json==='string'?row.expected_json:row?.expected_json===null||row?.expected_json===undefined?'':JSON.stringify(row.expected_json,null,2)} onChange={e=>{let v:any=e.target.value;try{v=v.trim()?JSON.parse(v):null;}catch{}change(i,{expected_json:v});}}/></label>
 <p className="text-sm">结构化字段检查（路径可使用点号，例如 patient.code）</p>
 {Object.entries(row?.expected_fields||{}).map(([path,expected],n)=><div key={n} className="flex flex-wrap gap-2">
 <input aria-label={`样例 ${i+1} 字段 ${n+1} 路径`} className="border rounded-md p-2 min-w-0 bg-background" value={path} onChange={e=>{if(e.target.value!==path&&Object.prototype.hasOwnProperty.call(row.expected_fields,e.target.value))return;change(i,{expected_fields:Object.fromEntries(Object.entries(row.expected_fields).map(([k,v])=>[k===path?e.target.value:k,v]))});}}/>
 <select aria-label={`样例 ${i+1} 字段 ${n+1} 类型`} value={expected===null?'null':typeof expected} onChange={e=>change(i,{expected_fields:{...row.expected_fields,[path]:e.target.value==='boolean'?true:e.target.value==='number'?0:e.target.value==='null'?null:''}})}><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔值</option><option value="null">空值</option>{typeof expected==='object'&&expected!==null&&<option value="object">对象（高级编辑）</option>}</select>
 {typeof expected==='boolean'?<select aria-label={`样例 ${i+1} 字段 ${n+1} 值`} value={String(expected)} onChange={e=>change(i,{expected_fields:{...row.expected_fields,[path]:e.target.value==='true'}})}><option>true</option><option>false</option></select>:expected!==null&&typeof expected!=='object'&&<input aria-label={`样例 ${i+1} 字段 ${n+1} 值`} type={typeof expected==='number'?'number':'text'} className="border rounded-md p-2 min-w-0 bg-background" value={String(expected)} onChange={e=>change(i,{expected_fields:{...row.expected_fields,[path]:typeof expected==='number'?Number(e.target.value):e.target.value}})}/>}
 <button type="button" onClick={()=>change(i,{expected_fields:Object.fromEntries(Object.entries(row.expected_fields).filter(([k])=>k!==path))})}>删除字段 {n+1}</button></div>)}
 <button type="button" onClick={()=>{let key='field';while(Object.prototype.hasOwnProperty.call(row.expected_fields||{},key))key+='_';change(i,{expected_fields:{...row.expected_fields,[key]:''}});}}>添加字段检查</button></>}
 <button type="button" onClick={()=>update(rows.filter((_,index)=>index!==i))}>删除第 {i+1} 条</button></fieldset>)}
 <button type="button" disabled={disabled||rows.length>=(isEval?10:20)} onClick={()=>update([...rows,isEval?{id:`case-${crypto.randomUUID().slice(0,8)}`,text:'',contains:[],excludes:[],expected_fields:{}}:{text:''}])}>添加{isEval?'样例':'文书'}</button>
 </>}
 {error&&<p role="status" className="text-amber-800">{error}{!advanced&&!rows.length?' 可切换高级 JSON 修正。':''}</p>}
 </div>;
}
