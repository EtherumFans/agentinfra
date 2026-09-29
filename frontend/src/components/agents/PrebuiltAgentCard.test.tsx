// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import PrebuiltAgentCard from './PrebuiltAgentCard';
import type {HubCard} from '../../services/agentHubApi';
afterEach(cleanup);
const card={agent_id:'medical-coding-agent',agent_ref:'icoder/medical-coding-agent@2.0.0',name:'医学编码智能体',description:'production_ready=false no_upcoding',runnable:true,display_status:'preview',display_badges:[{label_zh:'预览版'},{label_zh:'发送前需审批'}],red_lines:{no_upcoding:true,evidence_required:true,production_writeback_blocked:true},runtime_readiness:{run_action_enabled:true}} as unknown as HubCard;
test('explains the task without exposing technical metadata and retains actions',()=>{
 const use=vi.fn(),details=vi.fn();render(<PrebuiltAgentCard card={card} locale="zh-CN" cloning={false} onUse={use} onDetails={details}/>);
 expect(screen.getByRole('heading',{name:'医学编码'})).toBeTruthy();
 expect(screen.getByText(/根据病历生成诊断与手术编码建议/)).toBeTruthy();
 expect(screen.queryByText(/no_upcoding|预览版|发送前需审批/)).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'使用'}));expect(use).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole('button',{name:'查看详情'}));expect(details).toHaveBeenCalledOnce();
});
test('unavailable runtime cannot be started but details remain available',()=>{
 const use=vi.fn();render(<PrebuiltAgentCard card={{...card,runtime_readiness:{...card.runtime_readiness,run_action_enabled:false}} as HubCard} locale="zh-CN" cloning={false} onUse={use} onDetails={()=>{}}/>);
 expect(screen.getByText('暂不可用')).toBeTruthy();
 const button=screen.getByRole('button',{name:'使用'}) as HTMLButtonElement;expect(button.disabled).toBe(true);fireEvent.click(button);expect(use).not.toHaveBeenCalled();
 expect((screen.getByRole('button',{name:'查看详情'}) as HTMLButtonElement).disabled).toBe(false);
});
test('prevents repeated use while preparing the agent',()=>{
 render(<PrebuiltAgentCard card={card} locale="zh-CN" cloning onUse={()=>{}} onDetails={()=>{}}/>);
 expect((screen.getByRole('button',{name:'准备中…'}) as HTMLButtonElement).disabled).toBe(true);
});
