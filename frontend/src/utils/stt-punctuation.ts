/**
 * Chinese STT Punctuation Restoration.
 *
 * JS rule-based restoration (the LLM endpoint /api/experts/stt/punctuate
 * was removed in Phase 2.1-B Step 1 when experts.py was deleted; the JS
 * fallback is now the only tier).
 */

// ── JS fallback (lightweight, for interim text and API failures) ────

const CJK_PUNCT_RE = /[。，！？：；…、—]/;

const SECTION_HEADERS = [
  '主诉', '现病史', '既往史', '个人史', '家族史', '婚育史', '月经史',
  '查体', '体格检查', '辅助检查', '专科检查',
  '初步诊断', '入院诊断', '出院诊断', '鉴别诊断',
  '诊疗计划', '治疗经过',
];

const KV_RULES: [RegExp, string][] = [
  [/(性别)([男女])/g, '$1：$2'],
  [/(年龄)(\d+)/g, '$1：$2'],
  [/(体温|T)\s*(\d+[\.\d]*)/g, '$1：$2'],
  [/(血压|BP)\s*(\d+[/\d]*)/g, '$1：$2'],
  [/(心率|HR|脉搏|P)\s*(\d+)/g, '$1：$2'],
  [/(呼吸|[Rr])\s*(\d+)/g, '$1：$2'],
  [/(SpO[₂2]|血氧饱和度|血氧)\s*(\d+[%％]?)/g, '$1：$2'],
  [/(身高|体重|BMI)\s*(\d+[\.\d]*)/g, '$1：$2'],
  [/(\d+[次天周月年日时分钟秒个只片粒支瓶盒包袋条张块])/g, '$1，'],
];

/**
 * Append new STT segment with punctuation. For final text from server STT
 * (which may have punctuation from Paraformer's punc model), minimal processing.
 * For browser STT raw text, tries LLM first, falls back to JS rules.
 */
export function appendWithPunctuation(existing: string, incoming: string): string {
  let seg = incoming.trim();
  if (!seg) return existing;

  // If text already has CJK punctuation, just ensure sentence ending
  if (CJK_PUNCT_RE.test(seg)) {
    seg = ensureSentenceEnd(seg);
  } else {
    // Raw text — apply JS quick restoration now, then queue LLM refinement
    seg = jsRestore(seg);
  }

  if (!existing) return seg;

  const lastChar = existing.slice(-1);
  if (/[。！？…\n]/.test(lastChar)) return existing + seg;
  if (/[，、：；]/.test(lastChar)) return existing + seg;
  return existing + '，' + seg;
}

/**
 * Queue LLM punctuation restoration for the full transcript.
 * Returns a promise that resolves with the punctuated text.
 * Call this after recording stops to refine the complete transcript.
 */
export async function llmPunctuate(text: string): Promise<string> {
  if (!text || !text.trim()) return text;
  // Don't call LLM for very short text or already-punctuated text
  if (text.length < 15) return ensureSentenceEnd(text);

  const punctCount = (text.match(CJK_PUNCT_RE) || []).length;
  const charCount = text.length;
  // If already has reasonable punctuation density, skip
  if (punctCount > charCount / 12) return text;

  try {
    // LLM endpoint removed — JS rules only
    return jsRestore(text);
  } catch {
    return jsRestore(text);
  }
}

// ── JS rule-based restoration (fallback) ─────────────────────────────

function jsRestore(text: string): string {
  if (!text || !text.trim()) return text;
  let result = text.trim();

  // Pass 1: KV patterns
  for (const [re, replacement] of KV_RULES) {
    result = result.replace(re, replacement);
  }

  // Pass 2: Section headers → ：
  for (const h of SECTION_HEADERS) {
    const re = new RegExp(`(${escapeRegExp(h)})\\s*([\u4e00-\u9fff\\d])`, 'g');
    result = result.replace(re, '$1：$2');
  }

  // Pass 3: Period before topic shifts
  const markers = ['但是', '不过', '然而', '所以', '因此', '然后', '接着', '随后', '另外', '此外', '目前', '患者', '否认', '自述'];
  for (const m of markers) {
    const re = new RegExp(`([\u4e00-\u9fff\\d%％])[，、]?\\s*(${escapeRegExp(m)})`, 'g');
    result = result.replace(re, '$1。$2');
  }

  // Pass 4: Comma between measurement keys
  const kvKeys = '年龄|体温|血压|心率|脉搏|呼吸|身高|体重|BMI';
  result = result.replace(new RegExp(`([\u4e00-\u9fff\\d%％])(\\s*)(${kvKeys})`, 'g'), '$1，$3');

  // Pass 5: Cleanup
  result = result
    .replace(/^[。，、：；]+/, '')
    .replace(/。。+/g, '。')
    .replace(/，，+/g, '，')
    .replace(/。，/g, '。')
    .replace(/，。/g, '。')
    .replace(/：：+/g, '：')
    .trim();

  return ensureSentenceEnd(result);
}

// Question patterns: if text contains question cues, end with ？ not 。
const QUESTION_PATTERNS = /[吗呢]|[什么怎怎][么样]|为[什么]|多[少久]|哪[个些]|是[不是]|有[没有]|能[不能]|会[不会]|可[可以]|请[问]|如何|为何|几[岁时个]/;
const EXCLAMATION_PATTERNS = /[！!]$|^[真太好多][好棒对]|^[恭祝贺]/;

function ensureSentenceEnd(text: string): string {
  if (!text) return text;
  if (/[。！？…\n]/.test(text.slice(-1))) return text;

  const clean = text.replace(/[，、：；]+$/, '');

  // Detect exclamation
  if (EXCLAMATION_PATTERNS.test(clean)) return clean + '！';
  // Detect question
  if (QUESTION_PATTERNS.test(clean)) return clean + '？';
  // Default
  return clean + '。';
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
