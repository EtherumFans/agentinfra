// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import Page from './AgentJobsPage';
import api from '../services/api';
vi.mock('../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../store',()=>({useAuthStore:(fn:any)=>fn({currentOrgId:'one'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function setup(){vi.mocked(api.get).mockImplementation(async(url:any)=>({data:url.endsWith('/integration')?{version:'1.0.0',configuration_digest:'digest'}:{jobs:[]}}));render(<MemoryRouter initialEntries={['/agents/a/jobs']}><Routes><Route path="/agents/:agentId/jobs" element={<Page/>}/></Routes></MemoryRouter>);}
test('batch pins release and retains idempotency key after uncertain submit',async()=>{setup();vi.mocked(api.post).mockRejectedValue(new Error('timeout'));await screen.findByText('发布版本：1.0.0');fireEvent.click(screen.getByText('提交异步任务'));await screen.findByRole('alert');await waitFor(()=>expect((screen.getByText('提交异步任务') as HTMLButtonElement).disabled).toBe(false));fireEvent.click(screen.getByText('提交异步任务'));await waitFor(()=>expect(api.post).toHaveBeenCalledTimes(2));const calls=vi.mocked(api.post).mock.calls;expect(calls[0][1]).toMatchObject({expected_agent_version:'1.0.0',expected_configuration_digest:'digest'});expect(calls[0][2]?.headers?.['Idempotency-Key']).toBe(calls[1][2]?.headers?.['Idempotency-Key']);});
test('invalid batch does not submit',async()=>{setup();await screen.findByText('发布版本：1.0.0');fireEvent.click(screen.getByText('高级 JSON'));fireEvent.change(screen.getByLabelText('批量文书 JSON'),{target:{value:'{}'}});fireEvent.click(screen.getByText('提交异步任务'));await screen.findByRole('alert');expect(api.post).not.toHaveBeenCalled();});
