// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import Page from './AgentEvaluationPage';
import api from '../services/api';
vi.mock('../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../store',()=>({useAuthStore:(fn:any)=>fn({currentOrgId:'one'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function setup(){vi.mocked(api.get).mockImplementation(async (url:any)=>({data:url.endsWith('/releases')?{active_version:'1.0.0',releases:[{version:'1.0.0'}]}:[]}));
 render(<MemoryRouter initialEntries={['/agents/a/evaluations']}><Routes><Route path="/agents/:agentId/evaluations" element={<Page/>}/></Routes></MemoryRouter>);}
test('invalid JSON makes no execution request',async()=>{setup();fireEvent.click(screen.getByRole('button',{name:'单次评测'}));await waitFor(()=>expect((screen.getByLabelText('基线版本') as HTMLSelectElement).value).toBe('1.0.0'));
 fireEvent.click(screen.getByText('高级 JSON'));fireEvent.change(screen.getByLabelText('评测样例 JSON'),{target:{value:'invalid'}});fireEvent.click(screen.getByText('运行新旧版本评测'));
 expect(await screen.findByRole('alert')).toBeTruthy();expect(api.post).not.toHaveBeenCalled();});
test('submits fixed suite and labels inconsistent evaluation',async()=>{setup();vi.mocked(api.post).mockResolvedValue({data:{id:'e',baseline_version:'1.0.0',candidate_version:'draft',candidate_passed:1,case_count:1,regressions:0,consistent:false,checks_passed:false,cases:[]}});
 fireEvent.click(screen.getByRole('button',{name:'单次评测'}));
 await waitFor(()=>expect((screen.getByLabelText('基线版本') as HTMLSelectElement).value).toBe('1.0.0'));
 fireEvent.click(screen.getByText('运行新旧版本评测'));
 await screen.findByText('评测期间草稿发生变化，本次结论无效');expect(api.post).toHaveBeenCalledWith('/rest/v1/agent_definitions/a/evaluations',expect.objectContaining({baseline_version:'1.0.0',candidate_version:'draft',cases:expect.any(Array)}),expect.anything());});

test('business suite uses server cases and requires an explicit review note',async()=>{
 vi.mocked(api.get).mockImplementation(async (url:any)=>({data:url.endsWith('/evaluation-suites')?{suites:[{id:'documentation-v1',name:'文书处理',cases:[]}]}:url.endsWith('/releases')?{active_version:'1.0.0',releases:[{version:'1.0.0'}]}:[{id:'business',candidate_version:'draft',candidate_passed:2,case_count:2,regressions:0,consistent:true,checks_passed:true,cases:[],review_editable:true,review:{id:'previous',decision:'rejected',note:'重验',created_at:'2026-09-09T00:00:00Z'}}]}));
 vi.mocked(api.post).mockResolvedValue({data:{id:'business',consistent:true,checks_passed:true}});
 render(<MemoryRouter initialEntries={['/agents/a/evaluations']}><Routes><Route path="/agents/:agentId/evaluations" element={<Page/>}/></Routes></MemoryRouter>);
 fireEvent.click(screen.getByRole('button',{name:'单次评测'}));
 await screen.findByRole('option',{name:'文书处理 · documentation-v1'});
 fireEvent.click(screen.getByText('导入样例或下载模板'));
 expect(screen.getAllByRole('heading',{name:'准备业务评测样例'})).toHaveLength(1);
 fireEvent.change(screen.getByLabelText('业务验收套件'),{target:{value:'documentation-v1'}});
 fireEvent.click(screen.getByText('运行新旧版本评测'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/rest/v1/agent_definitions/a/evaluations',expect.objectContaining({business_suite:'documentation-v1',baseline_version:null}),expect.anything()));
 expect(vi.mocked(api.post).mock.calls[0][1]).not.toHaveProperty('cases');
 fireEvent.click(screen.getByRole('button',{name:'评测记录'}));
 fireEvent.click(await screen.findByText(/候选通过 2\/2/));
 const accept=await screen.findByRole('button',{name:'接受评测'});
 expect((accept as HTMLButtonElement).disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('复核意见 business'),{target:{value:'已核对合成样例证据'}});
 fireEvent.click(accept);
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/rest/v1/agent_definitions/a/evaluations/business/review',{decision:'approved',note:'已核对合成样例证据',expected_previous_review_id:'previous'}));
});
