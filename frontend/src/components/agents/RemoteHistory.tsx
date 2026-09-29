import {ReactNode,useEffect,useState} from 'react';
import api from '../../services/api';
import {useAuthStore} from '../../store';
type Props={url:string;field:string;label:string;revision?:number;currentOnly?:boolean;render:(row:any)=>ReactNode};
export default function RemoteHistory({url,field,label,revision=0,currentOnly=false,render}:Props){
 const org=useAuthStore(s=>s.currentOrgId);
 const [search,setSearch]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(0);
 const [retry,setRetry]=useState(0);
 const [rows,setRows]=useState<any[]>([]),[more,setMore]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{setSearch('');setQuery('');setPage(0);setRows([]);},[url,org]);
 useEffect(()=>{const c=new AbortController();setBusy(true);setError('');setRows([]);
 api.get(url,{params:{limit:20,offset:page*20,q:query,paginated:true,current_only:currentOnly},signal:c.signal}).then(r=>{if(c.signal.aborted)return;setRows(Array.isArray(r.data)?r.data:r.data[field]||[]);setMore(!!r.data.has_more);}).catch(()=>{if(!c.signal.aborted)setError('读取失败，请重试。');}).finally(()=>{if(!c.signal.aborted)setBusy(false);});return ()=>c.abort();},[url,org,page,query,revision,currentOnly,field,retry]);
 return <div className="space-y-3"><form className="flex flex-wrap gap-2" onSubmit={e=>{e.preventDefault();setPage(0);setQuery(search);}}><input aria-label={`${label}搜索`} placeholder={label} value={search} maxLength={100} onChange={e=>setSearch(e.target.value)} className="border rounded-md p-2 bg-background"/><button disabled={busy}>搜索</button><button type="button" disabled={busy} onClick={()=>{setSearch('');setQuery('');setPage(0);}}>清除筛选</button></form>
 {error&&<p role="alert">{error}<button onClick={()=>setRetry(n=>n+1)}>重试</button></p>}{busy?<p role="status">读取中…</p>:rows.length?rows.map(row=><div key={row.id||`${row.kind}:${row.name}:${row.version}`}>{render(row)}</div>):<p>暂无匹配记录。</p>}
 <div className="flex gap-3"><button disabled={busy||page===0} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第 {page+1} 页 · 每页 20 条</span><button disabled={busy||!more} onClick={()=>setPage(p=>p+1)}>下一页</button><button disabled={busy} onClick={()=>{setPage(0);setQuery(search);}}>返回首页</button></div></div>;
}
