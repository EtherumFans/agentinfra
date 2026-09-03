// @vitest-environment jsdom

import { beforeAll, describe, expect, it } from 'vitest';

let parseGuidedDocumentContext: typeof import('../TextGenerationPage').parseGuidedDocumentContext;
let parseStoredTemplates: typeof import('../TextGenerationPage').parseStoredTemplates;

beforeAll(async () => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  });
  const module = await import('../TextGenerationPage');
  parseGuidedDocumentContext = module.parseGuidedDocumentContext;
  parseStoredTemplates = module.parseStoredTemplates;
});


describe('TextGenerationPage launch-candidate contracts', () => {
  it('maps text input to a non-empty Guided Documents text context', () => {
    expect(parseGuidedDocumentContext('  去标识临床文本  ', 'text')).toEqual([
      { type: 'text', text: '去标识临床文本' },
    ]);
    expect(() => parseGuidedDocumentContext('   ', 'text')).toThrow('文本输入不能为空');
  });

  it('parses Corti-compatible facts and transcript JSON contexts', () => {
    const result = parseGuidedDocumentContext(JSON.stringify({
      context: [
        { type: 'facts', facts: [{ group: 'diagnosis', text: ' 高血压 ' }] },
        {
          type: 'transcript',
          transcript: {
            transcripts: [{ text: ' 医生：目前感觉如何？ ', speakerId: 1 }],
            metadata: { locale: 'zh-CN' },
          },
        },
      ],
    }), 'json');

    expect(result).toEqual([
      { type: 'facts', facts: [{ group: 'diagnosis', text: '高血压' }] },
      {
        type: 'transcript',
        transcript: {
          transcripts: [{ text: '医生：目前感觉如何？', speakerId: 1 }],
          metadata: { locale: 'zh-CN' },
        },
      },
    ]);
  });

  it('fails closed for malformed or unsupported JSON context', () => {
    expect(() => parseGuidedDocumentContext('{', 'json')).toThrow('JSON 输入格式无效');
    expect(() => parseGuidedDocumentContext('[]', 'json')).toThrow('JSON context 不能为空');
    expect(() => parseGuidedDocumentContext(JSON.stringify({
      type: 'facts', facts: [{ value: 'missing text' }],
    }), 'json')).toThrow('仅支持非空 text、facts 或 transcript');
  });

  it('rejects oversized text, JSON, and aggregate clinical context', () => {
    expect(() => parseGuidedDocumentContext('x'.repeat(200_001), 'text'))
      .toThrow('200000');
    expect(() => parseGuidedDocumentContext(JSON.stringify({
      context: [{ type: 'text', text: 'x'.repeat(200_001) }],
    }), 'json')).toThrow('单个 text context 过长');
    expect(() => parseGuidedDocumentContext(' '.repeat(1024 * 1024 + 1), 'json'))
      .toThrow('1048576 字节');
  });

  it('rejects corrupt or structurally invalid local template caches', () => {
    const fallback = parseStoredTemplates('{bad json');
    expect(fallback.length).toBeGreaterThan(0);
    expect(fallback[0].key).toBe('discharge_summary');
    expect(parseStoredTemplates(JSON.stringify([{ key: 'only-key' }]))[0].key)
      .toBe('discharge_summary');
    expect(parseStoredTemplates(JSON.stringify([{
      key: 'x'.repeat(65), name: '过长', desc: '', category: '通用', sample: '',
    }]))[0].key).toBe('discharge_summary');

    const custom = [{
      key: 'custom', name: '自定义', desc: '说明', category: '通用', sample: '样例',
    }];
    expect(parseStoredTemplates(JSON.stringify(custom))).toEqual(custom);
  });
});
