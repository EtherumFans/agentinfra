// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import History from './RemoteHistory';
import api from '../../services/api';
vi.mock('../../services/api',()=>({default:{get:vi.fn()}}));
vi.mock('../../store',()=>({useAuthStore:(fn:any)=>fn({currentOrgId:'one'})}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
test('pagination and search request server data and reset page',async()=>{vi.mocked(api.get).mockImplementation(async (_url:any,options:any)=>({data:{items:[{id:String(options.params.offset),name:options.params.q||String(options.params.offset)}],has_more:options.params.offset===0}}));render(<History url="/history" field="items" label="历史" render={r=><p>{r.name}</p>}/>);await screen.findByText('0');fireEvent.click(screen.getByText('下一页'));await screen.findByText('20');fireEvent.change(screen.getByLabelText('历史搜索'),{target:{value:'old'}});fireEvent.click(screen.getByText('搜索'));await screen.findByText('old');await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/history',expect.objectContaining({params:expect.objectContaining({offset:0,q:'old'})})));});
