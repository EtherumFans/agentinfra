// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../../services/api',()=>({default:api}));
import DocumentReviewPanel from '../DocumentReviewPanel';
const snapshot=()=>({id:'review-1',version:1,title:'合成测试',source:'合成原文',status:'pending',sections:[{id:'0',original:'合成初稿',text:'合成初稿',decision:'pending'}],history:[]});
beforeEach(()=>{api.get.mockReset().mockResolvedValue({data:{items:[],has_more:false}});api.post.mockReset();});
afterEach(cleanup);
describe('document result review',()=>{
 it('saves only on explicit action and blocks unfinished confirmation',async()=>{
  render(<DocumentReviewPanel source="合成原文" draft="合成初稿" title="合成测试"/>);
  await waitFor(()=>expect(api.get).toHaveBeenCalled());expect(api.post).not.toHaveBeenCalled();
  api.post.mockResolvedValue({data:snapshot()});fireEvent.click(screen.getByText('保存并开始复核'));
  await screen.findByText('合成测试 · 待复核');
  expect(api.post.mock.calls[0][1]).toMatchObject({source:'合成原文',draft:'合成初稿'});
  expect((screen.getByText('完成复核并确认') as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText('导出确认稿') as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText('保存修改') as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('第 1 段处理意见'),{target:{value:'对照原文修正'}});
  fireEvent.change(screen.getByLabelText('第 1 段复核内容'),{target:{value:'合成修订稿'}});
  const modified={...snapshot(),version:2,status:'in_review',sections:[{...snapshot().sections[0],decision:'modified',text:'合成修订稿'}]};
  api.post.mockResolvedValue({data:modified});fireEvent.click(screen.getByText('保存修改'));
  await screen.findByText('合成测试 · 复核中');
  expect(api.post.mock.calls[1][1]).toMatchObject({expected_version:1,decision:'modified',text:'合成修订稿',note:'对照原文修正'});
  api.post.mockResolvedValue({data:{...modified,version:3,status:'confirmed',confirmed_by:'reviewer',confirmed_at:new Date().toISOString()}});
  fireEvent.click(screen.getByText('完成复核并确认'));await screen.findByText('合成测试 · 已确认');
  expect((screen.getByText('导出确认稿') as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByText('保存修改') as HTMLButtonElement).disabled).toBe(true);
 });
 it('shows conflicts and does not silently overwrite another reviewer',async()=>{
  api.post.mockRejectedValue({response:{data:{detail:'记录已更新，请刷新后重试。'}}});
  render(<DocumentReviewPanel source="原文" draft="初稿" title="测试"/>);
  fireEvent.click(screen.getByText('保存并开始复核'));
  expect((await screen.findByRole('alert')).textContent).toContain('请刷新');
 });
 it('treats literal source lookup as navigation and preserves missing evidence',async()=>{
  api.post.mockResolvedValue({data:snapshot()});render(<DocumentReviewPanel source="合成原文" draft="合成初稿" title="测试"/>);
  fireEvent.click(screen.getByText('保存并开始复核'));await screen.findByText('合成测试 · 待复核');
  fireEvent.change(screen.getByPlaceholderText('输入关键词定位原文'),{target:{value:'合成原文'}});
  expect(screen.getByText(/匹配不代表内容已被证实/)).toBeTruthy();
  fireEvent.click(screen.getByText('查找对应原文'));expect(screen.getByText('未找到逐字对应，请人工核对。')).toBeTruthy();
 });
});
