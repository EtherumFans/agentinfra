// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import ConversationHistory from './ConversationHistory';
import MemorySearch from './MemorySearch';
import api from '../../services/api';
vi.mock('../../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
test('history loads task content and restores selected context',async()=>{
 vi.mocked(api.get).mockImplementation(async(url:any)=>({data:url.endsWith('/tasks')?{tasks:[{id:'task',history:[{messageId:'m',role:'user',parts:[{kind:'text',text:'Synthetic note'}]}]}],nextPageToken:null}:{contexts:[{id:'context',updatedAt:'2026-09-08',taskCount:1}],nextPageToken:null}}));
 const restore=vi.fn();render(<ConversationHistory agentId="agent" disabled={false} onRestore={restore}/>);
 fireEvent.click(await screen.findByRole('button',{name:/context/}));
 await screen.findByText('Synthetic note');fireEvent.click(screen.getByRole('button',{name:'恢复此对话'}));
 expect(restore).toHaveBeenCalledWith('context',expect.arrayContaining([expect.objectContaining({content:'Synthetic note'})]));
});
test('memory searches older server window and clears results when purpose changes',async()=>{
 vi.mocked(api.post).mockResolvedValue({data:{candidate_offset:0,candidates_scanned:100,returned:0,memories:[],next_candidate_offset:100,candidates_truncated:true,retrieval_mode:'LEXICAL'}});
 render(<MemorySearch agentId="agent"/>);
 fireEvent.change(screen.getByLabelText('记忆关键词'),{target:{value:'synthetic'}});fireEvent.click(screen.getByText('搜索记忆'));
 fireEvent.click(await screen.findByText('检索更早记忆'));
 await waitFor(()=>expect(api.post).toHaveBeenLastCalledWith(expect.any(String),expect.objectContaining({candidate_offset:100,purpose_of_use:'treatment'}),expect.any(Object)));
 fireEvent.change(screen.getByLabelText('记忆用途'),{target:{value:'research'}});
 expect(screen.queryByText('检索更早记忆')).toBeNull();
});
