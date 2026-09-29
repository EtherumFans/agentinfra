import {useEffect,useRef,useState} from 'react';
import api from '../../services/api';
import {messagesFromTasks,HistoryMessage} from '../../services/conversationHistory';
export default function ConversationHistory({agentId,disabled,onRestore}:{agentId:string;disabled:boolean;onRestore:(id:string,messages:HistoryMessage[])=>void}){
 const [contexts,setContexts]=useState<any[]>([]),[next,setNext]=useState<string|null>(null),[selected,setSelected]=useState(''),[tasks,setTasks]=useState<any[]>([]),[taskNext,setTaskNext]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[listing,setListing]=useState(false);
 const lifecycle=useRef(new AbortController()),request=useRef<AbortController|null>(null);
 async function loadContexts(token?:string){const c=lifecycle.current;setListing(true);setError('');try{const r=await api.get('/v2/agentic/contexts',{params:{agentId,pageSize:20,pageToken:token},signal:c.signal});if(c.signal.aborted)return;setContexts(v=>token?[...v,...r.data.contexts]:r.data.contexts);setNext(r.data.nextPageToken);}catch{if(!c.signal.aborted)setError('无法读取组织对话历史。');}finally{if(!c.signal.aborted)setListing(false);}}
 useEffect(()=>{lifecycle.current=new AbortController();void loadContexts();return ()=>{lifecycle.current.abort();request.current?.abort();};},[agentId]);
 async function select(id:string,token?:string){request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setError('');if(!token){setSelected(id);setTasks([]);setTaskNext(null);}
  try{const r=await api.get(`/v2/agentic/contexts/${encodeURIComponent(id)}/tasks`,{params:{pageSize:20,pageToken:token,historyLength:100},signal:c.signal});if(c.signal.aborted)return;setTasks(v=>token?[...v,...r.data.tasks]:r.data.tasks);setTaskNext(r.data.nextPageToken);}catch{if(!c.signal.aborted)setError('无法读取对话，可能已过期或无权访问。');}finally{if(!c.signal.aborted)setBusy(false);}}
 return <section className="inspector-card m-3 space-y-3 max-h-96 overflow-auto"><h2 className="font-semibold">组织对话历史</h2><p className="text-xs">沿用当前组织的访问权限；正文从服务端读取，不保存在浏览器。每页 20 个任务，每个任务最多展示 100 条历史消息。</p>{error&&<p role="alert">{error}</p>}
 <div className="flex flex-wrap gap-2">{contexts.map(c=><button disabled={disabled||busy} key={c.id} className="border rounded-lg p-2 text-sm" onClick={()=>select(c.id)}>{new Date(c.updatedAt).toLocaleString()} · {c.taskCount} 个任务 · {c.id.slice(0,8)}</button>)}</div>
 {next&&<button disabled={listing} onClick={()=>loadContexts(next)}>更多对话</button>}{!contexts.length&&<p>暂无可用对话。</p>}
 {selected&&<><p className="text-xs break-all">上下文：{selected}</p>{messagesFromTasks(tasks).map((m,i)=><p className="text-sm whitespace-pre-wrap" key={i}><strong>{m.role==='user'?'用户':'智能体'}：</strong>{m.content}</p>)}{taskNext&&<button disabled={busy} onClick={()=>select(selected,taskNext)}>加载后续任务</button>}<button disabled={disabled||busy||!tasks.length} className="bg-primary text-primary-foreground px-4 py-2" onClick={()=>onRestore(selected,messagesFromTasks(tasks))}>恢复此对话</button></>}
 </section>;
}
