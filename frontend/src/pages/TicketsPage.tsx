// iCoDer - 工单系统
import { MessageSquare, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useT } from '../i18n';

export default function TicketsPage() {
  const t = useT();
  const navigate = useNavigate();

  return (
    <div className="p-6 bg-muted/20 h-full overflow-y-auto">
      <h2 className="text-2xl font-bold text-foreground mb-2">{t.ticketsTitle || '工单系统'}</h2>
      <p className="text-sm text-muted-foreground mb-8 max-w-xl">
        {t.ticketsDesc || '管理您的支持工单。访问外部系统以进行完整的工单管理。'}
      </p>

      <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-8 text-center max-w-lg">
        <MessageSquare size={48} className="mx-auto mb-4 text-muted-foreground/30" />
        <h3 className="text-sm font-semibold text-foreground mb-2">{t.externalTicketSystem || '外部工单系统'}</h3>
        <p className="text-sm text-muted-foreground mb-4">
          工单系统尚未配置。请联系系统管理员设置外部工单系统（如飞书、钉钉或 Jira）的集成地址。
        </p>
        <button
          onClick={() => navigate('/support')}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors"
        >
          {t.getHelp || '在线咨询'} <ExternalLink size={14} />
        </button>
      </div>
    </div>
  );
}
