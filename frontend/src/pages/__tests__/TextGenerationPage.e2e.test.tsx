// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const generateDynamic = vi.hoisted(() => vi.fn());

vi.mock('../../services/api', () => ({
  guidedDocumentsApi: { generateDynamic },
}));

vi.mock('../../i18n', () => ({
  useT: () => new Proxy({}, { get: (_target, key) => String(key) }),
  useLocaleStore: (selector: (state: { locale: string }) => unknown) =>
    selector({ locale: 'zh-CN' }),
}));

import TextGenerationPage from '../TextGenerationPage';


describe('TextGenerationPage local end-to-end flow', () => {
  beforeEach(() => {
    localStorage.clear();
    generateDynamic.mockReset();
  });

  afterEach(() => cleanup());

  it('selects a template, sends Guided Documents context, and displays acknowledged output', async () => {
    generateDynamic.mockResolvedValue({
      data: {
        document: {
          name: 'guided-discharge',
          templateId: 'template-1',
          templateVersionId: 'version-1',
          language: 'zh-CN',
          stringDocument: { 出院小结: '已生成的去标识出院小结' },
          labels: [],
        },
        usageInfo: { creditsConsumed: 0.007 },
      },
      headers: { 'x-corti-retention-policy': 'acknowledged' },
    });

    render(<TextGenerationPage />);
    fireEvent.click(screen.getByRole('button', { name: '选择模板' }));
    fireEvent.click(screen.getByText('出院小结'));
    fireEvent.change(screen.getByPlaceholderText('输入临床文本、事实摘要或转录文本...'), {
      target: { value: '患者因胸闷入院，完成 PCI 后出院。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '生成文书' }));

    await waitFor(() => expect(generateDynamic).toHaveBeenCalledTimes(1));
    expect(generateDynamic.mock.calls[0][0]).toMatchObject({
      outputLanguage: 'zh-CN',
      context: [{ type: 'text', text: '患者因胸闷入院，完成 PCI 后出院。' }],
      dynamicTemplate: {
        name: '出院小结',
        generation: {
          sections: [{ heading: '出院小结', outputSchema: { type: 'string' } }],
        },
      },
    });
    expect(await screen.findByText('已生成的去标识出院小结')).toBeTruthy();
    expect(screen.queryByText(/未确认零留存策略/)).toBeNull();
  });

  it('discards output when the server does not acknowledge document zero-retention', async () => {
    generateDynamic.mockResolvedValue({
      data: {
        document: { stringDocument: { note: '不得展示' } },
        usageInfo: { creditsConsumed: 0.01 },
      },
      headers: {},
    });

    render(<TextGenerationPage />);
    fireEvent.click(screen.getByRole('button', { name: '选择模板' }));
    fireEvent.click(screen.getByText('出院小结'));
    fireEvent.change(screen.getByPlaceholderText('输入临床文本、事实摘要或转录文本...'), {
      target: { value: '去标识临床文本' },
    });
    fireEvent.click(screen.getByRole('button', { name: '生成文书' }));

    expect(await screen.findByText('服务器未确认零留存策略，结果已丢弃。')).toBeTruthy();
    expect(screen.queryByText('不得展示')).toBeNull();
  });
});
