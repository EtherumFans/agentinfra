// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import Page from './AgentDependenciesPage';
import api from '../services/api';
vi.mock('../services/api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
vi.mock('../store',()=>({useAuthStore:(fn:any)=>fn({currentOrgId:'one'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function setup(data:any){vi.mocked(api.get).mockResolvedValue({data});render(<MemoryRouter initialEntries={['/agents/a/dependencies']}><Routes><Route path="/agents/:agentId/dependencies" element={<Page/>}/></Routes></MemoryRouter>);}
test('drift is explicit and registration hidden from ordinary members',async()=>{setup({bindings:[],locked:[{kind:'model',name:'model',version:'1'}],registry:[],drift:[{expected:{name:'model',version:'1'},current:{version:'2'}}],can_register:false});expect(await screen.findByRole('alert')).toBeTruthy();expect(screen.queryByText('登记当前版本')).toBeNull();});
test('saving binding edits draft without publishing',async()=>{setup({bindings:[],locked:[],registry:[{kind:'tool',name:'extract',version:'1',is_current:true}],drift:[],can_register:true});vi.mocked(api.put).mockResolvedValue({data:{}});fireEvent.click(await screen.findByRole('checkbox'));fireEvent.click(screen.getByText('保存草稿依赖'));await waitFor(()=>expect(api.put).toHaveBeenCalledWith('/rest/v1/agent_definitions/a/dependencies/bindings',{bindings:[{kind:'tool',name:'extract'}]},expect.anything()));expect(api.post).not.toHaveBeenCalled();});
