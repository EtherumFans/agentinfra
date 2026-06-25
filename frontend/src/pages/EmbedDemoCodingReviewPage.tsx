// iCoDer M3-0 — Embed Demo Page: 病案首页编码审核
//
// 演示如何将 iCoDer 的 3 个核心 embed 组件嵌入到第三方 HIS/EMR 页面:
// - <IcoderReviewPanel />    — 主组件 (编码建议 + 高风险易错编码点)
// - <IcoderEvidenceViewer /> — 证据回链
// - <IcoderTraceViewer />    — 14 阶段运行追踪
//
// 模拟一个简单的"伪 HIS"页面布局 (左 60% 病历 / 右 40% iCoDer 嵌入),
// 表明 iCoDer 不接管宿主 UI, 而是作为独立模块嵌入。

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Code, FileText, Server, ExternalLink } from 'lucide-react';
import { icoderCodingReviewApi, type CodingReviewRunResponse, type HumanReviewAction } from '../services/icoderCodingReviewApi';
import { useToastStore } from '../store';
import { IcoderReviewPanel, type EmbedAction } from '../components/embed/IcoderReviewPanel';
import { IcoderEvidenceViewer } from '../components/embed/IcoderEvidenceViewer';
import { IcoderTraceViewer } from '../components/embed/IcoderTraceViewer';

const DEMO_CASE_ID = 'embed-demo-' + Date.now().toString(36);

const SAMPLE_EMR = `入院记录
患者: 张三, 男, 65 岁, 住院号: 20260512
主诉: 反复胸闷、心悸 3 年, 加重伴夜间呼吸困难 1 周。

现病史: 患者 3 年前无明显诱因出现胸闷心悸, 活动后明显, 休息后可缓解。
曾于外院诊断为 "冠心病", 长期口服阿司匹林、阿托伐他汀。
近 1 周症状加重, 伴夜间阵发性呼吸困难, 需高枕卧位, 遂来我院。

既往史: 高血压病史 10 年, 最高 160/100mmHg, 口服氨氯地平 5mg qd。
2 型糖尿病史 5 年, 口服二甲双胍 0.5g tid。
否认肝炎、结核等传染病史, 否认手术外伤史, 否认药物过敏史。

体格检查: T 36.5°C, P 78次/分, R 18次/分, BP 138/86mmHg。
神清, 精神可。双肺呼吸音清, 未闻及干湿啰音。
心率 78 次/分, 律齐, 各瓣膜听诊区未闻及病理性杂音。
腹软, 无压痛及反跳痛。双下肢无水肿。

辅助检查: 心电图示 V4-V6 导联 ST 段下移 0.1mV。冠脉造影示 LAD 中段狭窄 75%。

入院诊断:
1. 冠状动脉粥样硬化性心脏病 不稳定型心绞痛
2. 高血压病 2 级 (很高危)
3. 2 型糖尿病

诊疗经过: 入院后完善常规检查, 给予抗血小板 (阿司匹林 + 氯吡格雷 双抗),
强化降脂 (阿托伐他汀 20mg qn), 控制血压血糖, 监测心电图变化。
于入院第 3 天行冠脉造影 + 支架植入术 (LAD 中段, 1 枚支架)。
术后患者胸闷症状明显缓解, 未再发夜间呼吸困难。

出院医嘱: 继续双抗血小板 + 他汀治疗, 定期门诊随访心电图、心脏彩超。
`;

export default function EmbedDemoCodingReviewPage() {
  const toast = useToastStore((s) => s.addToast);
  const [response, setResponse] = useState<CodingReviewRunResponse | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>('');
  const [actionLog, setActionLog] = useState<Array<{ ts: string; action: string; code: string; role: string }>>([]);

  // 初始: 跑一次, 拿 runId
  useEffect(() => {
    runPipeline();
  }, []);

  async function runPipeline() {
    setLoading(true);
    setErr('');
    try {
      const r = await icoderCodingReviewApi.run({
        encounter_text: SAMPLE_EMR,
        case_id: DEMO_CASE_ID,
        input_source: 'embed_demo',
        mode: 'link_validation',
        primary_disease_codes: 'I20.000',
        other_disease_codes: 'I10.x00, E11.900',
        primary_surgery_codes: '36.0600',
      });
      setResponse(r);
      setRunId(r.run_id);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'run failed');
    } finally {
      setLoading(false);
    }
  }

  // 嵌入场景下, 宿主调用 iCoDer human-review API
  async function handleEmbedAction(action: EmbedAction, code: string, role: string, newCode?: string) {
    if (!runId) return;
    setActionLog((prev) => [
      { ts: new Date().toISOString().slice(11, 19), action, code, role },
      ...prev,
    ]);
    try {
      const payload: HumanReviewAction = {
        action: action as HumanReviewAction['action'],
        target_code: code,
        target_role: role as HumanReviewAction['target_role'],
        reason_code: 'R007',
        reviewer: 'embed-demo-reviewer',
        reviewer_role: 'medical_insurance_reviewer',
        new_code: newCode,
      };
      const r = await icoderCodingReviewApi.humanReview(runId, payload);
      if (r.accepted) {
        toast(`Embed action=${action} 已记录: target=${code} → production_writeback_blocked=true`, 'success');
      } else {
        toast(`复核校验失败: ${r.validation_errors.join('; ')}`, 'error');
      }
    } catch (e: any) {
      toast(`调用失败: ${String(e)}`, 'error');
    }
  }

  return (
    <div className="flex flex-col h-full bg-slate-100">
      {/* 模拟第三方 HIS 顶部条 (不是 iCoDer 自己的 Layout) */}
      <div className="bg-slate-800 text-white px-4 py-2 text-sm flex items-center gap-2 shrink-0">
        <Server size={14} />
        <span className="font-semibold">某 HIS 系统 (Mock)</span>
        <span className="text-xs text-slate-400">· 病案首页</span>
        <div className="ml-auto flex items-center gap-3 text-xs text-slate-300">
          <Link to="/studio/medical-coding" className="hover:text-white flex items-center gap-0.5">
            打开完整 iCoDer Workbench <ExternalLink size={10} />
          </Link>
        </div>
      </div>

      {/* 模拟第三方 breadcrumb */}
      <div className="bg-white px-4 py-1.5 border-b border-slate-200 text-xs flex items-center gap-1.5 shrink-0">
        <span className="text-slate-500">病案管理</span>
        <ChevronRight size={12} className="text-slate-400" />
        <span className="text-slate-500">入院记录</span>
        <ChevronRight size={12} className="text-slate-400" />
        <span className="text-slate-700 font-medium">首页编码 (iCoDer 嵌入)</span>
      </div>

      <div
        className="flex-1 grid grid-cols-1 md:grid-cols-12 gap-3 p-3 overflow-y-auto md:overflow-hidden min-h-0"
        tabIndex={0}
        role="region"
        aria-label="iCoDer Embed 演示"
      >
        {/* 左侧: 模拟第三方病历 (M3-0.1 修复: 窄屏单列, ≥md 双列) */}
        <div
          className="md:col-span-7 bg-white rounded-lg border border-slate-200 p-4 overflow-y-auto min-h-0"
          tabIndex={0}
          role="region"
          aria-label="病历原文 (HIS 侧)"
        >
          <div className="text-xs text-slate-500 mb-2 flex items-center gap-1">
            <FileText size={12} /> 病历原文 (HIS 侧)
          </div>
          <pre className="text-[12px] leading-relaxed text-slate-700 whitespace-pre-wrap font-sans">
            {SAMPLE_EMR}
          </pre>
        </div>

        {/* 右侧: iCoDer Embed 区域 (M3-0.1 修复: 窄屏堆叠在下方) */}
        <div
          className="md:col-span-5 flex flex-col gap-3 md:overflow-y-auto min-h-0"
          tabIndex={0}
          role="region"
          aria-label="iCoDer Embed 组件"
        >
          <div className="text-[11px] text-slate-600 italic px-1">
            ↓ 以下是 iCoDer Embed 组件 (在第三方 HIS 页面里直接渲染, 不接管宿主 UI)
          </div>

          {err && (
            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">
              初始化失败: {err}
            </div>
          )}

          {loading && !response && (
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-xs text-slate-400 flex items-center gap-2">
              <Code size={14} className="animate-pulse" /> 正在调用 iCoDer Agent...
            </div>
          )}

          {response && (
            <>
              <IcoderReviewPanel
                response={response}
                onAction={handleEmbedAction}
                title="iCoDer 编码审核 (Embed)"
              />

              <IcoderEvidenceViewer response={response} reviewer="embed-demo-reviewer" />

              <IcoderTraceViewer response={response} />

              {actionLog.length > 0 && (
                <div className="bg-white rounded-lg border border-slate-200 p-3 text-[11px]">
                  <div className="font-medium text-slate-700 mb-1.5">本次嵌入交互记录</div>
                  <ul className="space-y-0.5 text-slate-600">
                    {actionLog.map((a, i) => (
                      <li key={i} className="font-mono">
                        <span className="text-slate-400">{a.ts}</span>{' '}
                        <span className="text-blue-600">action={a.action}</span>{' '}
                        <span>code={a.code}</span>{' '}
                        <span className="text-slate-500">role={a.role}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* 底部说明 (iCoDer 立场: 这是 Embed 演示, 不是 iCoDer 全部产品) */}
      <div className="border-t border-slate-200 bg-white px-4 py-2 text-[11px] text-slate-500 shrink-0">
        <span className="font-medium text-blue-700">iCoDer Embed</span> 演示 ·
        iCoDer 是医学编码 Agent 开发和运行基础设施,
        <strong className="text-rose-600">本页仅展示 embed 组件能力, 不代表 iCoDer 全部产品定位</strong>。
        Embed 组件不接管宿主 UI, 接受 fetcher / onAction / className 注入, 便于接入第三方 HIS/EMR。
      </div>
    </div>
  );
}
