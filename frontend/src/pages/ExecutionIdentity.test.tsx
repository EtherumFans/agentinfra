// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {ExecutionIdentity} from './RunTracePage';
vi.mock('../store',()=>({useToastStore:vi.fn()}));
vi.mock('../services/runtimeApi',()=>({runtimeAgentApi:{}}));
afterEach(cleanup);
test('shows actual pinned version and explicit review requirement',()=>{
 render(<ExecutionIdentity summary={{executed_agent_version:'1.0.0',draft_preview:false,manual_review_required:true}}/>);
 expect(screen.getByText('1.0.0')).toBeTruthy();expect(screen.getByText('需人工复核')).toBeTruthy();
});
test('old rows are unknown rather than passed',()=>{
 render(<ExecutionIdentity summary={{}}/>);
 expect(screen.getByText('历史记录未保存版本')).toBeTruthy();expect(screen.getByText('复核要求未记录')).toBeTruthy();
});
test('draft execution is labelled',()=>{
 render(<ExecutionIdentity summary={{executed_agent_version:'draft',draft_preview:true}}/>);
 expect(screen.getByText('draft · 草稿调试')).toBeTruthy();
});
