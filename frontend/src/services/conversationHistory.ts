export type HistoryMessage={role:string;content:string};
export function messagesFromTasks(tasks:any[]):HistoryMessage[]{
 const seen=new Set<string>(),messages:HistoryMessage[]=[];
 for(const task of tasks){
  for(const message of task.history||[]){
   const id=message.messageId||message.message_id||JSON.stringify(message);
   if(seen.has(id))continue;seen.add(id);
   const content=(message.parts||[]).map((part:any)=>part.text || (part.data?JSON.stringify(part.data,null,2):'')).filter(Boolean).join('\n');
   if(content)messages.push({role:message.role==='user'?'user':'assistant',content});
  }
  if(!(task.history||[]).some((m:any)=>m.role==='agent'||m.role==='assistant')){
   const content=(task.artifacts||[]).flatMap((a:any)=>a.parts||[]).map((p:any)=>p.text||(p.data?JSON.stringify(p.data,null,2):'')).filter(Boolean).join('\n');
   if(content)messages.push({role:'assistant',content});
  }
 }
 return messages;
}
