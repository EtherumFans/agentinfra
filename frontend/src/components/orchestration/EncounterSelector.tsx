import { useState, useEffect } from 'react';
import { Search, FileText, Loader2 } from 'lucide-react';
import { useT } from '../../i18n';
import { encountersApi } from '../../services/api';

interface Props {
  onSelect: (encounterId: string, encounterData?: any) => void;
  disabled?: boolean;
  batchMode?: boolean;
  selectedBatchIds?: string[];
}

export default function EncounterSelector({ onSelect, disabled, batchMode, selectedBatchIds }: Props) {
  const t = useT();
  const [tab, setTab] = useState<'existing' | 'new'>('existing');
  const [searchQuery, setSearchQuery] = useState('');
  const [encounters, setEncounters] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [clinicalText, setClinicalText] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (tab === 'existing' && encounters.length === 0) {
      setSearching(true);
      encountersApi.list(1, 20).then(r => {
        setEncounters(r.data.items || []);
      }).catch(() => {}).finally(() => setSearching(false));
    }
  }, [tab]);

  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (!q.trim()) {
      setSearching(true);
      encountersApi.list(1, 20).then(r => {
        setEncounters(r.data.items || []);
      }).catch(() => {}).finally(() => setSearching(false));
      return;
    }
    setSearching(true);
    try {
      const r = await encountersApi.list(1, 20);
      const items = r.data.items || [];
      const filtered = items.filter((e: any) => {
        const id = (e.encounter_id || e.id || '').toLowerCase();
        const dept = (e.department || '').toLowerCase();
        const ql = q.toLowerCase();
        return id.includes(ql) || dept.includes(ql);
      });
      setEncounters(filtered);
    } catch {} finally { setSearching(false); }
  };

  const handleCreateAndRun = async () => {
    if (!clinicalText.trim()) return;
    setCreating(true);
    try {
      const r = await encountersApi.createFromText(clinicalText.trim());
      const enc = r.data;
      onSelect(enc.encounter_id || enc.id, enc);
    } catch {} finally { setCreating(false); }
  };

  return (
    <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5">
      <div className="flex items-center gap-4 mb-4">
        <button
          onClick={() => setTab('existing')}
          className={`text-sm font-medium pb-1.5 border-b-2 transition-colors ${tab === 'existing' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          disabled={disabled}
        >
          {t.orchestrationExistingEncounter}
        </button>
        <button
          onClick={() => setTab('new')}
          className={`text-sm font-medium pb-1.5 border-b-2 transition-colors ${tab === 'new' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          disabled={disabled}
        >
          {t.orchestrationNewClinicalText}
        </button>
      </div>

      {tab === 'existing' ? (
        <div className="space-y-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={e => handleSearch(e.target.value)}
              placeholder={t.orchestrationEncounterPlaceholder}
              className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-lg bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20"
              disabled={disabled}
            />
          </div>
          {searching ? (
            <div className="flex justify-center py-4"><Loader2 className="animate-spin h-4 w-4 text-muted-foreground" /></div>
          ) : encounters.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">{t.orchestrationNoEncounterFound}</p>
          ) : (
            <div className="max-h-48 overflow-y-auto space-y-1">
              {encounters.map((enc: any) => (
                <button
                  key={enc.id || enc.encounter_id}
                  onClick={() => onSelect(enc.encounter_id || enc.id, enc)}
                  disabled={disabled}
                  className={`w-full text-left px-3 py-2 rounded-lg hover:bg-accent transition-colors group ${batchMode && selectedBatchIds?.includes(enc.encounter_id || enc.id) ? 'bg-primary/10 ring-1 ring-primary/20' : ''}`}
                >
                  {batchMode && <input type="checkbox" checked={selectedBatchIds?.includes(enc.encounter_id || enc.id) || false} readOnly className="w-3 h-3 mr-2 shrink-0" />}
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono text-foreground">{enc.encounter_id || enc.id}</span>
                    <span className="text-[10px] text-muted-foreground">{enc.department || '--'}</span>
                  </div>
                  {enc.created_at && (
                    <span className="text-[10px] text-muted-foreground">{new Date(enc.created_at).toLocaleDateString()}</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <textarea
            value={clinicalText}
            onChange={e => setClinicalText(e.target.value)}
            placeholder={t.orchestrationEnterClinicalText}
            className="w-full h-40 p-3 text-sm border border-border rounded-lg bg-background text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-ring/20"
            disabled={disabled || creating}
          />
          <button
            onClick={handleCreateAndRun}
            disabled={disabled || creating || !clinicalText.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 className="animate-spin h-3.5 w-3.5" /> : <FileText size={14} />}
            {creating ? t.creating : t.orchestrationRunPipeline}
          </button>
        </div>
      )}
    </div>
  );
}
