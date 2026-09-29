// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import AgentDetailHeader from './AgentDetailHeader';
afterEach(cleanup);
const props={name:'文书助手',description:'整理文书中的已记录信息。',agentId:'a',draft:false,unavailable:false,managed:true,advanced:false,onAdvanced:vi.fn(),onHistory:vi.fn(),onNew:vi.fn(),busy:false};
test('draft leads to draft debugging instead of claiming it is runnable',()=>{
 render(<MemoryRouter><AgentDetailHeader {...props} draft unavailable/></MemoryRouter>);
 expect(screen.getByRole('link',{name:'调试草稿'}).getAttribute('href')).toBe('/ai-studio/agents/a/releases');
 expect(screen.getByText(/当前为草稿/)).toBeTruthy();
 expect(screen.queryByText(/当前暂不可运行/)).toBeNull();
});
test('advanced settings and history remain accessible, new conversation is disabled while busy',()=>{
 render(<MemoryRouter><AgentDetailHeader {...props} busy/></MemoryRouter>);
 const button=screen.getByRole('button',{name:'高级设置'});
 expect(button.getAttribute('aria-expanded')).toBe('false');
 fireEvent.click(button);expect(props.onAdvanced).toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'对话记录'}));expect(props.onHistory).toHaveBeenCalled();
 expect((screen.getByRole('button',{name:'新建对话'}) as HTMLButtonElement).disabled).toBe(true);
});
test('unavailable prebuilt agent explains status without offering project publishing',()=>{
 render(<MemoryRouter><AgentDetailHeader {...props} managed={false} unavailable/></MemoryRouter>);
 expect(screen.getByText(/当前暂不可运行/)).toBeTruthy();
 expect(screen.queryByRole('link',{name:'版本与发布'})).toBeNull();
});
