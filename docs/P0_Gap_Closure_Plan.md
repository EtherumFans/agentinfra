# P0 差距拉平方案

> 日期: 2026-05-11
> 目标: 将 iCoDer Embedded Assistant 的实时管线能力拉平到 Corti 水平
> 四个 P0 差距: 流式 STT / 说话人分离 / 实时事实提取 / 实时编码建议

---

## 总览

四个 P0 差距构成一条**实时管线**，按数据流天然顺序排列:

```
麦克风音频
  │
  ├─[P0-1]─→ 流式逐词转录 ──→ 实时显示
  │              │
  ├─[P0-2]─→ 说话人分离 ──→ 医生/患者标注
  │              │
  ├─[P0-3]─→ 断句检测 → 实时 LLM 事实提取
  │              │
  └─[P0-4]─→ 实时 ICD 编码建议
```

**实施顺序**: P0-1 → P0-2 → P0-3 → P0-4。每个后续步骤依赖前一步的输出。

---

## P0-1: 流式 STT 逐词返回

### 当前状态

```
客户端每秒发送 4KB 音频块 → 服务端缓冲
客户端每 4 秒发 {"type":"interim"} → 服务端全量重跑 FunASR streaming
客户端点停止 → 服务端跑 FunASR batch (VAD+punc) → 返回 final
```

问题: interim 是 4s 轮询，且每次都重跑全部已缓冲音频，不是真正的增量流式。

### 目标状态

```
客户端发送音频块 → 服务端缓冲
服务端每收到完整 utterance（VAD 检测到静音间隙）→ 主动推送 interim
服务端检测到句子边界 → 主动推送 sentence
客户端点停止 → 服务端跑 batch final + 标点 + 说话人分离
```

### 实现方案

#### 1A. 后端: 缩短 interim 轮询间隔 + VAD 驱动推送

当前 4s 硬编码轮询 → 改为:

```python
# websocket.py — 服务端主动推送 interim
# 每收到 ~16000 样本（1 秒音频），运行一次增量 streaming inference
# FunASR streaming model 的 chunk_size 模式:
#   每次只处理新增的音频块，返回增量文本
#   不需要等客户端发 interim
```

具体改动 (`backend/app/api/websocket.py`):

```python
# 新增: 增量 streaming 计数器
stt_chunk_count: dict[str, int] = {}

# 在 bytes 处理中:
if conn_id in stt_buffers:
    stt_buffers[conn_id].append(chunk)
    stt_chunk_count[conn_id] = (stt_chunk_count.get(conn_id, 0) + 1)
    
    # 每积累 ~1 秒音频（约 10 个 4KB chunk），运行增量 streaming
    if stt_chunk_count[conn_id] % 10 == 0:
        combined = b"".join(stt_buffers[conn_id])
        text, err = await _transcribe_streaming(combined, current_mime)
        last = stt_last_interim.get(conn_id, "")
        if text and text != last:
            stt_last_interim[conn_id] = text
            await websocket.send_json({"type": "interim", "text": text})
```

#### 1B. 前端: 移除 4s 轮询，改为被动接收

```typescript
// SpeechToTextPage.tsx + EmbeddedAssistantPage.tsx
// 删除 setInterval 的 interim 轮询
// 改为: 服务端主动推送 interim，前端直接 setInterim(text)
```

改动量: ~20 行删除（移除 setInterval），~30 行新增（chunk counter + 主动推送）。

### 验收标准
- [ ] 在诊室内模式下说一句话，500ms 内 interim 文本出现
- [ ] 连续说话时 interim 逐句更新，不跳跃不倒退
- [ ] 网络断开时前端显示"连接断开"而非静默失败

---

## P0-2: 说话人分离前端展示

### 当前状态

后端 `speaker_diarizer.py` 已完整实现:
- WebRTC VAD 语音活动检测
- MFCC + 能量 + 基频特征提取  
- Agglomerative 聚类 (2 speaker: doctor + patient)
- 角色标注 (说话时间长的 = 医生)

后端 `websocket.py` 第 170-173 行已将 diarization 数据放入 `final` 响应:

```python
await websocket.send_json({
    "type": "final",
    "text": text,
    "diarization": diarization,  # [{speaker, start, end, text?}]
})
```

**但前端完全丢弃了 `m.diarization`。** 这是纯前端缺失。

### 目标状态

转录完成后，前端解析 diarization 数据，将转录文本按说话人分段显示:

```
🟢 医生  (00:00 - 00:12)
   您最近有没有胸闷胸痛的情况？

🟡 患者  (00:13 - 00:25)  
   有的，最近一周经常觉得胸闷，走几步路就喘。

🟢 医生  (00:26 - 00:45)
   好的，我们先做个心电图。你以前有高血压或糖尿病吗？

🟡 患者  (00:46 - 00:52)
   有高血压，在吃药。糖尿病没有。
```

### 实现方案

#### 2A. 前端显示层

SpeechToTextPage 和 EmbeddedAssistantPage 的转录显示区改为:

```tsx
// diarized 模式下:
{diarization && diarization.length > 0 ? (
  <div className="space-y-3">
    {diarization.map((seg, i) => (
      <div key={i} className="flex gap-3">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full shrink-0"
          style={{ backgroundColor: seg.speaker === 'Doctor' ? '#dcfce7' : '#fef9c3' }}>
          {seg.speaker === 'Doctor' ? '医生' : '患者'}
        </span>
        <p className="text-sm">{seg.text}</p>
      </div>
    ))}
  </div>
) : (
  // fallback: 普通文本显示
  <p className="text-sm whitespace-pre-wrap">{transcript}</p>
)}
```

#### 2B. 后端对齐 diarization 输出格式

检查 `speaker_diarizer.py` 的 `diarize()` 返回格式，确保包含:
- `speaker`: "Doctor" | "Patient"
- `start`: 秒数
- `end`: 秒数
- `text`: 该段的转录文本 (可选，如果没有则需要前端自行切割)

如果 diarization 只返回时间戳没有文本，后端需要将时间戳与 final text 对齐。

### 验收标准
- [ ] 诊室内双人对话录音后，转录结果按说话人分段显示
- [ ] 医生和患者使用不同颜色标签区分
- [ ] diarization 失败时，降级为普通文本显示（不报错）
- [ ] 单人录音时不显示 diarization（或显示单 speaker）

---

## P0-3: 实时事实提取

### 当前状态

```
转录完成后:
  1. 调 factsApi.extract(fullText) — 一次性 LLM 提取
  2. 客户端还有 regex fallback (EmbeddedAssistantPage 行 405-450)
  
转录进行中:
  ❌ 无实时提取
```

### 目标状态

```
转录进行中:
  每次收到 "sentence" 级别的转录片段（有句号或明确断句）:
    1. 追加到累积文本
    2. 异步调 LLM 提取该句中的新事实
    3. 合并新事实到已有事实列表（去重）
    4. 实时更新 UI（诊断/手术/否定发现列表）

转录完成后:
  对全文再跑一次完整提取（覆盖可能遗漏的长距离依赖）
```

### 实现方案

#### 3A. 断句检测器（前端 utils）

```typescript
// utils/sentence-detector.ts
// 检测转录文本中是否出现了新的完整句子
export function getNewSentences(prevText: string, newText: string): string[] {
  // 取 newText 中 prevText 之后的部分
  const delta = newText.slice(prevText.length);
  // 按句末标点切割
  const sentences = delta.split(/(?<=[。！？…])/);
  // 返回完整句子（有标点结尾的）
  return sentences.filter(s => /[。！？…]$/.test(s.trim()) && s.trim().length > 5);
}
```

#### 3B. 增量提取流程

```typescript
// 在 ws.onmessage 的 interim/final 处理中:
const sentences = getNewSentences(lastExtractedText, currentFullText);
if (sentences.length > 0) {
  lastExtractedText = currentFullText;
  for (const sent of sentences) {
    // 异步提取，不阻塞 UI
    factsApi.extract(sent).then(r => {
      const newFacts = r.data?.facts || r.data;
      setAccumulatedFacts(prev => mergeFacts(prev, newFacts));
    }).catch(() => {}); // 静默失败，不影响后续
  }
}
```

#### 3C. 事实去重合并

```typescript
function mergeFacts(existing: Facts, incoming: Facts): Facts {
  const merged = { ...existing };
  for (const dx of incoming.diagnosis_facts || []) {
    if (!merged.diagnosis_facts?.find(d => 
      d.diagnosis === dx.diagnosis || d.name === dx.name)) {
      merged.diagnosis_facts = [...(merged.diagnosis_facts || []), dx];
    }
  }
  // 同理处理 procedure_facts, negated_facts
  return merged;
}
```

### 验收标准
- [ ] 录音过程中，每说一句完整的话，1-3 秒内提取的事实出现在 UI
- [ ] 事实列表随录音进行动态增长，不闪烁
- [ ] 转录完成后的最终提取结果与增量结果一致（或更完整）
- [ ] 网络/LLM 错误不影响转录流程（静默降级）

---

## P0-4: 实时编码建议

### 当前状态

```
转录完成后:
  对每个诊断事实调 codesApi.search() → 展示编码候选
  
转录进行中:
  ❌ 无编码建议
```

### 目标状态

```
转录进行中:
  每次新事实被提取:
    1. 如果是诊断事实 → 调 codesApi.search(name)
    2. 如果是手术事实 → 调 codesApi.search(name, 'ICD9_CM3')
    3. 结果追加到编码建议列表
    4. 实时显示在转录区下方
```

### 实现方案

#### 4A. 编解码建议管道

```typescript
// 在增量事实提取的回调中:
factsApi.extract(sentenceText).then(r => {
  const newFacts = r.data?.facts || r.data;
  
  // 对每个新诊断，搜索 ICD-10 编码
  const newDiags = newFacts.diagnosis_facts || [];
  newDiags.slice(0, 3).forEach((dx: any) => {
    codesApi.search(dx.diagnosis || dx.name, 'ICD10_CN', 3)
      .then(r2 => {
        const codes = (r2.data?.results || []).filter((c: any) => c.score > 0.6);
        setCodeSuggestions(prev => {
          // 去重合并
          const existing = new Set(prev.map((c: any) => c.code));
          const toAdd = codes.filter((c: any) => !existing.has(c.code));
          return [...prev, ...toAdd].slice(0, 10);
        });
      }).catch(() => {});
  });
  
  // 对每个新手术，搜索 ICD-9-CM-3 编码
  const newProcs = newFacts.procedure_facts || [];
  newProcs.slice(0, 3).forEach((proc: any) => {
    codesApi.search(proc.procedure || proc.name, 'ICD9_CM3', 3)
      .then(r2 => {
        const codes = (r2.data?.results || []).filter((c: any) => c.score > 0.6);
        setCodeSuggestions(prev => {
          const existing = new Set(prev.map((c: any) => c.code));
          const toAdd = codes.filter((c: any) => !existing.has(c.code));
          return [...prev, ...toAdd].slice(0, 10);
        });
      }).catch(() => {});
  });
}).catch(() => {});
```

#### 4B. UI 展示

在 EmbeddedAssistantPage 的录音中/转录显示区域，添加一个实时更新的编码建议面板:

```
┌────────────────────────────────────────┐
│ 转录文本                               │
│ 主诉：胸闷3天，加重1天。                │
│ 现病史：患者3天前无明显诱因出现胸闷...   │
├────────────────────────────────────────┤
│ 实时编码建议               (随录音更新)  │
│                                        │
│ I25.101  冠心病              置信度 92% │
│ I10.x02  高血压3级           置信度 87% │
│ E11.900  2型糖尿病           置信度 65% │
│ 36.0700  冠脉支架植入术       置信度 78% │
└────────────────────────────────────────┘
```

### 验收标准
- [ ] 诊断事实被提取后，2 秒内对应的 ICD 编码出现在建议区
- [ ] 编码随事实增多而更新，不重复
- [ ] 点击编码可查看详情（编码名、章节、有效性）
- [ ] 编码搜索 API 失败不影响转录和事实提取

---

## 实施顺序与依赖

```
Phase 1: P0-1 流式STT (1-2h)
  └─ 无依赖，独立改动
  └─ 只改 backend/app/api/websocket.py + 前端移除 setInterval

Phase 2: P0-2 说话人分离 (0.5h)
  └─ 依赖 P0-1 完成（需要流式 final 响应包含 diarization）
  └─ 只改前端显示层 + 验证后端 diarization 格式

Phase 3: P0-3 实时事实提取 (2-3h)
  └─ 依赖 P0-1 完成（需要流式的 sentence 级别文本）
  └─ 新增 utils/sentence-detector.ts
  └─ 改 EmbeddedAssistantPage 的 ws.onmessage
  └─ 改 SpeechToTextPage 的 ws.onmessage

Phase 4: P0-4 实时编码建议 (1h)
  └─ 依赖 P0-3 完成（需要实时提取的事实）
  └─ 改 EmbeddedAssistantPage 的增量提取回调
```

## 改动文件清单

| # | 文件 | 改动 | 新增行 |
|---|------|------|--------|
| P0-1 | `backend/app/api/websocket.py` | 主动推送 interim，chunk counter | +30 |
| P0-1 | `frontend/src/pages/SpeechToTextPage.tsx` | 移除 setInterval 轮询 | -15 |
| P0-1 | `frontend/src/pages/EmbeddedAssistantPage.tsx` | 移除 setInterval 轮询 | -15 |
| P0-2 | `frontend/src/pages/SpeechToTextPage.tsx` | diarization UI 展示 | +30 |
| P0-2 | `frontend/src/pages/EmbeddedAssistantPage.tsx` | diarization UI 展示 | +30 |
| P0-3 | `frontend/src/utils/sentence-detector.ts` | **新增** 断句检测 | +30 |
| P0-3 | `frontend/src/pages/EmbeddedAssistantPage.tsx` | 增量事实提取管线 | +40 |
| P0-3 | `frontend/src/pages/SpeechToTextPage.tsx` | 增量事实提取管线 | +40 |
| P0-4 | `frontend/src/pages/EmbeddedAssistantPage.tsx` | 实时编码建议 UI + 管线 | +50 |
| P0-4 | `frontend/src/services/api.ts` | codesApi 已存在，无需改 | 0 |
| | **总计** | | **~220 行新增, ~30 行删除** |

## 风险评估

| 风险 | 概率 | 缓解 |
|------|------|------|
| FunASR streaming 增量模式不稳定 | 中 | 保留 4s 轮询作为 fallback concurrent 通道 |
| LLM 调用频繁导致费用高 | 中 | 只在完整句末触发（非每个 interim）；加 debounce |
| diarization 与文本时间轴不对齐 | 中 | 先用 simple 模式（整体文本 + speaker 标签）；精确对齐放后续迭代 |
| 断句检测在中文场景不准 | 中 | 结合标点+语义检测（已有 punctuation_service） |
