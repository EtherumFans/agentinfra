// @vitest-environment jsdom
import React from 'react';
import {test, expect, vi, afterEach} from 'vitest';
import {render, screen, fireEvent, waitFor, cleanup} from '@testing-library/react';
import Card from './ModelConnectionCard';
import api from '../../services/api';
vi.mock('../../services/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const data={configured:false,enabled:false,model:'deepseek-v4-flash',version:0,editable:true,external_allowed:true,encryption_ready:true};
test('tests and enables without retaining the entered key',async()=>{
  vi.mocked(api.get).mockResolvedValue({data}); vi.mocked(api.post).mockResolvedValue({data:{}});
  const changed=vi.fn(); render(<Card onChanged={changed}/>);
  const input=await screen.findByLabelText('API Key');
  fireEvent.change(input,{target:{value:'synthetic-secret'}});
  fireEvent.click(screen.getByText('测试并启用'));
  await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/v1/model-connection/test-and-enable',{api_key:'synthetic-secret',model:'deepseek-v4-flash',expected_version:0}));
  expect((input as HTMLInputElement).value).toBe('');
  await waitFor(()=>expect(changed).toHaveBeenCalled());
});
test('members cannot edit and blocked policy disables activation',async()=>{
  vi.mocked(api.get).mockResolvedValue({data:{...data,editable:false}});
  render(<Card onChanged={()=>{}}/>);
  await screen.findByText('组织所有者或管理员可以修改模型连接。');
  expect(screen.queryByLabelText('API Key')).toBeNull();
  cleanup();vi.mocked(api.get).mockResolvedValue({data:{...data,configured:true,external_allowed:false}});
  render(<Card onChanged={()=>{}}/>);
  expect((await screen.findByText('测试并启用') as HTMLButtonElement).disabled).toBe(true);
});
