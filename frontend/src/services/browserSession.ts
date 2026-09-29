import axios from 'axios';
import {useAuthStore} from '../store';
import type {TokenResponse} from '../types';
export const browserHeaders={'X-iCoDer-Browser':'1'};
let pending:Promise<string | null> | null=null;
let generation=0;
export function invalidateBrowserSession(){generation++;pending=null;}
export function rememberBrowserSession(data:TokenResponse){
 invalidateBrowserSession();
 useAuthStore.getState().login(data.user,data.access_token,'',data.organizations||[],data.current_org_id||'');
 return data;
}
function fresh(token:string | null){
 if(!token)return false;
 try{return JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).exp*1000>Date.now()+60000;}catch{return false;}
}
export async function ensureBrowserAccess(force=false):Promise<string | null>{
 const token=useAuthStore.getState().accessToken;
 if(!force&&fresh(token))return token;
 if(pending)return pending;
 const attempt=generation;
 const request=axios.post<TokenResponse>('/api/auth/browser/refresh',null,{headers:browserHeaders,withCredentials:true}).then(({data})=>{
  if(attempt!==generation)return useAuthStore.getState().accessToken;
  useAuthStore.getState().login(data.user,data.access_token,'',data.organizations||[],data.current_org_id||'');
  return data.access_token;
 }).catch(error=>{if(attempt===generation&&error.response?.status===401)useAuthStore.setState({user:null,accessToken:null,isAuthenticated:false,currentOrgId:null,organizations:[]});return null;}).finally(()=>{if(attempt===generation)pending=null;});
 pending=request;return request;
}
