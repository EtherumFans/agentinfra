// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Importer,{parseEvaluationImport,downloadEvaluation} from './EvaluationImport';
import api from '../../services/api';
vi.mock('../../services/api',()=>({default:{post:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
const cases=[{id:'synthetic',text:'合成资料',expected_json:{codes:['I10.x00'],missing:false}}];
test('roundtrip supports server suites and typed JSON expectations',()=>{
 expect(parseEvaluationImport('\ufeff'+JSON.stringify({cases}))).toEqual(cases);
 expect(()=>parseEvaluationImport(JSON.stringify([...cases,...cases]))).toThrow('不能重复');
 expect(()=>parseEvaluationImport(JSON.stringify([{...cases[0],wrong:1}]))).toThrow('不支持');
 expect(()=>parseEvaluationImport(JSON.stringify([{...cases[0],expected_json:[]}]))).toThrow('对象');
});
test('download emits a reusable JSON file',()=>{
 const create=vi.fn(()=> 'blob:fixture');vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:vi.fn()}));
 const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 downloadEvaluation(cases,'synthetic.json');expect(create).toHaveBeenCalledWith(expect.any(Blob));expect(click).toHaveBeenCalled();click.mockRestore();
});
test('preview does not replace current editor until explicitly applied',()=>{
 const apply=vi.fn();render(<Importer base="/agent" suites={[{id:'documentation-v1',cases}]} onApply={apply}/>);
 fireEvent.click(screen.getByText('预览合成示例'));expect(apply).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('使用这组样例'));expect(JSON.parse(apply.mock.calls[0][0])).toEqual(cases);expect(api.post).not.toHaveBeenCalled();
});
test('invalid files and cancelled previews keep current editor',async()=>{
 const apply=vi.fn();render(<Importer base="/agent" suites={[]} onApply={apply}/>);
 fireEvent.change(screen.getByLabelText('导入评测集文件'),{target:{files:[{name:'bad.json',size:5,text:async()=>'{bad'}]}});
 await screen.findByRole('alert');expect(apply).not.toHaveBeenCalled();
});
test('Excel uploads selected range and refuses partial import on row errors',async()=>{
 const apply=vi.fn();vi.mocked(api.post).mockResolvedValue({data:{total_rows:1800,start:11,selected_count:2,cases,issues:[{record:12,message:'编码列须为文本'}]}});
 render(<Importer base="/agent" suites={[]} onApply={apply}/>);
 fireEvent.change(screen.getByLabelText('Excel 起始记录'),{target:{value:11}});
 fireEvent.change(screen.getByLabelText('Excel 选取条数'),{target:{value:2}});
 fireEvent.change(screen.getByLabelText('导入评测集文件'),{target:{files:[new File(['synthetic'],'train.xlsx')]}});
 await screen.findByRole('alert');expect(screen.queryByText('使用这组样例')).toBeNull();expect(apply).not.toHaveBeenCalled();
 const body=vi.mocked(api.post).mock.calls[0][1] as FormData;expect(body.get('start')).toBe('11');expect(body.get('limit')).toBe('2');
});
