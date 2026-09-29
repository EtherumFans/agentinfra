// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Page from './EvaluationDatasets';
import api from '../../services/api';
vi.mock('../../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const d={id:'revision1',dataset_id:'dataset',name:'Synthetic',version:1,split:'validation',case_count:12,review_status:'pending',reviews:[]};
const suite=JSON.stringify([{id:'x',text:'Synthetic',contains:['ok']}]);
function setup(dataset:any=d){vi.mocked(api.get).mockImplementation(async(url:any)=>({data:url==='/evaluation-datasets'?{items:[dataset],has_more:false}:[]}));render(<Page agentId="agent" suite={suite} onLoad={vi.fn()}/>);}
test('persist current editor then require explicit review before running',async()=>{
 setup();await screen.findByText('Synthetic · v1 · 验证集 · 12 条 · 待审核');
 fireEvent.click(screen.getByText('Synthetic · v1 · 验证集 · 12 条 · 待审核'));
 expect((screen.getByText('开始后台批量评测') as HTMLButtonElement).disabled).toBe(true);
 vi.mocked(api.post).mockResolvedValue({data:d});fireEvent.change(screen.getByLabelText('评测集名称'),{target:{value:'Saved'}});
 fireEvent.click(screen.getByText('将编辑中的样例保存为新评测集'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/evaluation-datasets',{name:'Saved',split:'validation',cases:JSON.parse(suite)}));
 expect(vi.mocked(api.post).mock.calls.some(c=>String(c[0]).endsWith('/batches'))).toBe(false);
});
test('append requests a new version and reviewed datasets start explicit batches',async()=>{
 setup({...d,review_status:'approved'});fireEvent.click(await screen.findByText('Synthetic · v1 · 验证集 · 12 条 · 已审核'));
 vi.mocked(api.post).mockResolvedValue({data:{...d,id:'revision2',version:2}});
 fireEvent.click(screen.getByText('追加到所选集的新版本'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/evaluation-datasets',expect.objectContaining({dataset_id:'dataset',expected_version:1,append:true})));
});
test('restores batch evidence with failure filter and retry controls',async()=>{
 vi.mocked(api.get).mockImplementation(async(url:any)=>({data:url==='/evaluation-datasets'?{items:[{...d,review_status:'approved'}]}:String(url).endsWith('/batches')?[{id:'batch',state:'completed'}]:{state:'completed',total:12,states:{completed:11,failed:1,interrupted:0,queued:0,running:0,cancelled:0},passed:10,field_matches:{primary_diagnosis_code:{matched:10,checked:11}},items:[],has_more:false}}));
 render(<Page agentId="agent" suite={suite} onLoad={vi.fn()}/>);
 fireEvent.click(await screen.findByText('Synthetic · v1 · 验证集 · 12 条 · 已审核'));
 await screen.findByText('主要诊断：10/11 匹配');
 fireEvent.click(screen.getByText('仅看未通过样例'));
 await waitFor(()=>expect(api.get).toHaveBeenCalledWith('/evaluation-datasets/revision1/batches/batch',expect.objectContaining({params:{offset:0,failed_only:true}})));
 vi.mocked(api.post).mockResolvedValue({data:{state:'active'}});fireEvent.click(screen.getByText('重试执行失败或中断项'));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/evaluation-datasets/revision1/batches/batch/retry'));
});
