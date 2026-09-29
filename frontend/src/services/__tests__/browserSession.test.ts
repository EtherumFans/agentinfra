// @vitest-environment jsdom
import {afterEach,expect,test,vi} from 'vitest';
import axios from 'axios';
import {useAuthStore} from '../../store';
import {ensureBrowserAccess,invalidateBrowserSession} from '../browserSession';
vi.hoisted(()=>{Object.defineProperty(window,'matchMedia',{writable:true,value:()=>({matches:false})});});
vi.mock('axios',()=>({default:{post:vi.fn()}}));
afterEach(()=>{vi.clearAllMocks();invalidateBrowserSession();useAuthStore.setState({accessToken:null,isAuthenticated:false});localStorage.clear();});
test('login never persists access or refresh tokens',()=>{useAuthStore.getState().login({id:'u'} as any,'access-secret','refresh-secret',[],'org');expect(useAuthStore.getState().accessToken).toBe('access-secret');expect(useAuthStore.getState().refreshToken).toBeNull();expect(localStorage.getItem('access_token')).toBeNull();expect(localStorage.getItem('refresh_token')).toBeNull();expect(localStorage.getItem('icoder-auth')).toBeNull();});
test('concurrent refresh requests share one cookie exchange',async()=>{vi.mocked(axios.post).mockResolvedValue({data:{user:{id:'u'},access_token:'short-token',refresh_token:'',organizations:[],current_org_id:'org'}});const values=await Promise.all([ensureBrowserAccess(true),ensureBrowserAccess(true)]);expect(values).toEqual(['short-token','short-token']);expect(axios.post).toHaveBeenCalledTimes(1);expect(axios.post).toHaveBeenCalledWith('/api/auth/browser/refresh',null,expect.objectContaining({headers:{'X-iCoDer-Browser':'1'},withCredentials:true}));});
test('late refresh cannot restore credentials after logout',async()=>{let resolve:any;vi.mocked(axios.post).mockImplementation(()=>new Promise(r=>{resolve=r;}) as any);const pending=ensureBrowserAccess(true);invalidateBrowserSession();resolve({data:{user:{id:'u'},access_token:'stale',organizations:[]}});await pending;expect(useAuthStore.getState().accessToken).toBeNull();});
