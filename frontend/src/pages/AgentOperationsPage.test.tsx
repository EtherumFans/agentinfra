// @vitest-environment jsdom
import React from 'react';
import {test,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import Page from './AgentOperationsPage';
import api from '../services/api';
vi.mock('../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../store',()=>({useAuthStore:(fn:any)=>fn({currentOrgId:'org'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const data={scope:'organization',as_of:'2026-09-09T01:00:00Z',summary:{runs:25,succeeded:20,failed:5,other:0,success_rate:80,average_latency_ms:180},queue:{queued:1},notifications:{failed:1},failures:[],groups:[],runs:[],jobs:[],runs_more:true,jobs_more:false};
test('filters and pagination query the server and preserve summary scope',async()=>{
 vi.mocked(api.get).mockResolvedValue({data});render(<MemoryRouter><Page/></MemoryRouter>);
 await screen.findByText('80%');fireEvent.click(screen.getByText('执行下一页'));
 await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/operations/overview',expect.objectContaining({params:expect.objectContaining({run_offset:20})})));
 fireEvent.change(screen.getByLabelText('客户端 ID'),{target:{value:'client-one'}});fireEvent.click(screen.getByText('应用筛选'));
 await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/operations/overview',expect.objectContaining({params:expect.objectContaining({run_offset:0,client_id:'client-one'})})));
});
test('only queued tasks can cancel and failed notifications retry through scoped endpoint',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:{...data,jobs:[{id:'q',agent_id:'a',version:'1',state:'queued',notification_state:'none',actor_kind:'oauth',actor_id:'c'},{id:'u',agent_id:'a',version:'1',state:'interrupted',notification_state:'failed',category:'uncertain',actor_kind:'oauth',actor_id:'c'}]}});vi.mocked(api.post).mockResolvedValue({data:{updated:true}});
 render(<MemoryRouter><Page/></MemoryRouter>);await screen.findByText('仅重试通知');
 expect(screen.getAllByText('取消排队')).toHaveLength(1);expect(screen.queryByText('重新执行')).toBeNull();
 fireEvent.click(screen.getByText('仅重试通知'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/operations/jobs/u/retry-notification',null,expect.any(Object)));
});
test('failed loading is not displayed as zero successful runs',async()=>{
 vi.mocked(api.get).mockRejectedValue(new Error('offline'));render(<MemoryRouter><Page/></MemoryRouter>);
 await screen.findByRole('alert');expect(screen.queryByText('成功率')).toBeNull();
});

test('usage distinguishes missing values from recorded zero and shows coverage',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:{...data,model_usage:{recorded_runs:1,unrecorded_runs:24,calls:1,input_tokens:0,output_tokens:null,estimated_cost_usd:null,complete_usage_runs:0,complete_cost_runs:0},runs:[{run_id:'usage-run',agent_id:'a',status:'COMPLETED',created_at:'2026-09-09T01:00:00Z',model_usage:{calls:1,input_tokens:0,output_tokens:null,estimated_cost_usd:null,usage_complete:false,cost_complete:false,models:[{provider:'deepseek',model:'deepseek-v4-flash',calls:1,input_tokens:0,output_tokens:null,estimated_cost_usd:null}]}}]}});
 render(<MemoryRouter><Page/></MemoryRouter>);
 await screen.findByText('模型用量与估算费用');
 expect(screen.getByText(/24 条未记录/)).toBeTruthy();
 expect(screen.getByText(/deepseek \/ deepseek-v4-flash/)).toBeTruthy();
 expect(screen.getByText(/部分记录/)).toBeTruthy();
 expect(screen.queryByText('$0.000000')).toBeNull();
});
