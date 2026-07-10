// iCoDer - 帮助与支持页面
import { useNavigate } from 'react-router-dom';
import { MessageCircle, ExternalLink, Mail, BookOpen, FileText } from 'lucide-react';
import { useT } from '../i18n';

export default function SupportPage() {
  const t = useT();
  const navigate = useNavigate();

  return (
    <div className="bg-muted/20 min-h-dvh p-6">
      <h2 className="text-2xl font-bold text-foreground mb-2">{t.getHelp || '获取帮助'}</h2>
      <p className="text-sm text-muted-foreground mb-8 max-w-xl">需要 iCoDer 帮助？请从以下支持选项中选择。</p>

      <div className="grid grid-cols-2 gap-6 w-full">
        <a href={`${window.location.origin}/docs`} target="_blank" rel="noopener noreferrer" className="bg-background rounded-xl shadow-sm p-5 hover:border-primary transition-colors">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
            <BookOpen size={20} className="text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-foreground mb-1">文档中心</h3>
          <p className="text-sm text-muted-foreground">浏览全面的指南、API 参考和集成教程。</p>
          <span className="text-xs text-primary mt-3 inline-flex items-center gap-1">
            访问文档 <ExternalLink size={12} />
          </span>
        </a>

        <a href="/tickets" target="_blank" rel="noopener noreferrer" className="bg-background rounded-xl shadow-sm p-5 hover:border-primary transition-colors">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
            <FileText size={20} className="text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-foreground mb-1">工单系统</h3>
          <p className="text-sm text-muted-foreground">通过帮助台系统提交和跟踪支持工单。</p>
          <span className="text-xs text-primary mt-3 inline-flex items-center gap-1">
            打开工单 <ExternalLink size={12} />
          </span>
        </a>

        <div className="bg-background rounded-xl shadow-sm p-5">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
            <MessageCircle size={20} className="text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-foreground mb-1">在线客服</h3>
          <p className="text-sm text-muted-foreground mb-3">通过在线客服窗口直接与支持团队沟通。</p>
          <button onClick={() => navigate('/tickets')} className="bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors">打开客服</button>
        </div>

        <div className="bg-background rounded-xl shadow-sm p-5">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
            <Mail size={20} className="text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-foreground mb-1">邮件支持</h3>
          <p className="text-sm text-muted-foreground">联系我们：{' '}
            <a href="mailto:support@icoder.local" className="text-primary hover:underline">support@icoder.local</a>
          </p>
        </div>
      </div>
    </div>
  );
}
