// iCoDer Release Notes
import { useState } from 'react';

import { BACKEND_BASE_URL } from '../config';
import { useT } from '../i18n';

const RELEASES = [
  {
    version: 'v1.0.0-beta.1',
    date: '2026-05-21',
    sections: [
      {
        title: '开发者平台',
        items: [
          '新增 JavaScript SDK (@icoder/sdk) - OAuth 自动刷新、SSE 流式、WebSocket 支持',
          '新增 Python SDK (icoder-sdk) - httpx 客户端、dataclass 类型、async WebSocket',
          '新增 Web Components (@icoder/web) - <icoder-stt> 语音转录、<icoder-assistant> AI 助手',
          '新增 Agent Skills - 4 个 .well-known/agent-skills/ SKILL.md，AI coding agent 可发现',
          '新增 API Playground - Developer Quickstart 中直接测试 API',
          '新增开发者文档站 - /docs，含 SDK 安装指南、API 参考、5 分钟快速开始',
        ],
      },
      {
        title: 'API & 后端',
        items: [
          '85 个 REST + WebSocket 端点全部可用',
          'DeepSeek V4 Pro 引擎驱动所有 AI 能力',
          'FunASR Paraformer + Whisper + Google STT 三层语音回退',
          'OAuth 2.0 Client Credentials 短期令牌支持',
        ],
      },
      {
        title: 'Console UI',
        items: [
          '全 27 页面统一 Apple 极简设计系统',
          '463 i18n 键覆盖 zh-CN + en-US',
          '零 alert()/confirm() - 全部模态框 + 内联提示',
          '零硬编码颜色 - 全部语义 token',
          '前端 TypeScript 零错误',
        ],
      },
    ],
  },
];

export default function ReleaseNotesPage() {
  const t = useT();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ 'v1.0.0-beta.1': true });

  return (
    <div className="flex h-full bg-muted/20">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto p-8">
          <div className="mb-10">
            <h1 className="text-2xl font-bold text-foreground mb-2">{t.releaseNotesTitle}</h1>
            <p className="text-sm text-muted-foreground">{t.releaseNotesSubtitle}</p>
          </div>

          <div className="space-y-6">
            {RELEASES.map(release => (
              <div key={release.version} className="bg-background rounded-xl shadow-sm overflow-hidden">
                <button
                  onClick={() => setExpanded(prev => ({ ...prev, [release.version]: !prev[release.version] }))}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-foreground">{release.version}</span>
                    <span className="text-xs text-muted-foreground">{release.date}</span>
                  </div>
                  <span className={`text-muted-foreground transition-transform text-xs ${expanded[release.version] ? 'rotate-180' : ''}`}>▼</span>
                </button>
                {expanded[release.version] && (
                  <div className="px-6 pb-5 space-y-5">
                    {release.sections.map(section => (
                      <div key={section.title}>
                        <h3 className="text-sm font-semibold text-foreground mb-2">{section.title}</h3>
                        <ul className="space-y-1.5">
                          {section.items.map((item, i) => (
                            <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                              <span className="text-primary mt-1.5 shrink-0">•</span>
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="mt-10 border-t border-border pt-6 text-xs text-muted-foreground">
            <p>查看 <a href={`${BACKEND_BASE_URL}/docs`} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{t.releaseNotesApiPolicy}</a>。</p>
          </div>
        </div>
      </div>
    </div>
  );
}
