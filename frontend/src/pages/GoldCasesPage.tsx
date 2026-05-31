// iCoDer - Gold Cases Page
import { useEffect, useState } from 'react';
import { goldCasesApi } from '../services/api';
import type { GoldCase } from '../types';
import { Plus, Trash2, Upload, X } from 'lucide-react';
import { useT } from '../i18n';

export default function GoldCasesPage() {
  const t = useT();
  const [cases, setCases] = useState<GoldCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [importing, setImporting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [form, setForm] = useState({
    department: '', diagnosis_group: '',
    original_primary_diagnosis: '', original_primary_diag_name: '',
    gold_primary_diagnosis: '', gold_primary_diag_name: '',
    original_main_procedure: '', original_main_proc_name: '',
    gold_main_procedure: '', gold_main_proc_name: '',
    difficulty: 'medium',
  });

  useEffect(() => { loadCases(); }, [page]);

  const loadCases = async () => {
    setLoading(true);
    try {
      const { data } = await goldCasesApi.list(page);
      setCases(data.items);
      setTotal(data.total);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const handleCreate = async () => {
    try {
      await goldCasesApi.create(form);
      setShowForm(false);
      loadCases();
    } catch (err) { console.error(err); }
  };

  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    setDeleteConfirm(id);
  };
  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    await goldCasesApi.delete(deleteConfirm);
    setDeleteConfirm(null);
    loadCases();
  };

  return (
    <div className="p-6 bg-muted/20 h-full overflow-y-auto">
      {toast && (
        <div className="mb-4 px-4 py-3 bg-secondary/10 border border-secondary/20 rounded-lg text-sm text-secondary flex items-center justify-between">
          <span>{toast}</span>
          <button onClick={() => setToast(null)} className="text-secondary/60 hover:text-secondary shrink-0 ml-2"><X size={14} /></button>
        </div>
      )}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground">{t.goldCasesTitle}</h2>
          <p className="text-sm text-muted-foreground">{t.goldCasesDesc} (PRD Section 9.3)</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors cursor-pointer">
            <Upload size={14} /> CSV导入
            <input type="file" accept=".csv" className="hidden" onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setImporting(true);
              const text = await file.text();
              const lines = text.split('\n').filter(l => l.trim());
              const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
              let imported = 0;
              for (let i = 1; i < lines.length; i++) {
                const vals = lines[i].split(',').map(v => v.trim().replace(/"/g, ''));
                const row: any = {};
                headers.forEach((h, j) => { row[h] = vals[j] || ''; });
                try {
                  await goldCasesApi.create({
                    department: row.department || row['科室'] || '',
                    diagnosis_group: row.diagnosis_group || row['诊断组'] || '',
                    original_primary_diagnosis: row.original_primary_diagnosis || row['原始诊断代码'] || '',
                    original_primary_diag_name: row.original_primary_diag_name || row['原始诊断名称'] || '',
                    gold_primary_diagnosis: row.gold_primary_diagnosis || row['金标准诊断代码'] || '',
                    gold_primary_diag_name: row.gold_primary_diag_name || row['金标准诊断名称'] || '',
                    difficulty: row.difficulty || row['难度'] || 'medium',
                  });
                  imported++;
                } catch {}
              }
              setToast(`成功导入 ${imported}/${lines.length - 1} 条金标准案例`); setTimeout(() => setToast(null), 3000);
              setImporting(false);
              loadCases();
            }} />
          </label>
          <button onClick={() => {
            const strCSV = 'department,diagnosis_group,original_primary_diagnosis,original_primary_diag_name,gold_primary_diagnosis,gold_primary_diag_name,difficulty\n心内科,冠心病,I25.1,冠心病,I25.1,动脉硬化性心脏病,medium';
            navigator.clipboard.writeText(strCSV);
            setToast('CSV模板已复制到剪贴板'); setTimeout(() => setToast(null), 3000);
          }} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors" title="下载模板">
            模板
          </button>
          <button onClick={() => setShowForm(!showForm)} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm shadow-primary/20">
            <Plus size={16} /> {t.addGoldCase}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5 mb-6">
          <h3 className="font-semibold mb-4">{t.newGoldCase}</h3>
          <div className="grid grid-cols-2 gap-4">
            <input placeholder={t.department} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.department} onChange={e => setForm({...form, department: e.target.value})} />
            <input placeholder={t.diagnosisGroup} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.diagnosis_group} onChange={e => setForm({...form, diagnosis_group: e.target.value})} />
            <div>
              <label className="text-xs text-muted-foreground">{t.originalPrimaryDiagnosis} (code)</label>
              <input placeholder={t.code} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.original_primary_diagnosis} onChange={e => setForm({...form, original_primary_diagnosis: e.target.value})} />
              <input placeholder={t.name} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring mt-1" value={form.original_primary_diag_name} onChange={e => setForm({...form, original_primary_diag_name: e.target.value})} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.goldPrimaryDiagnosis} (code)</label>
              <input placeholder={t.code} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.gold_primary_diagnosis} onChange={e => setForm({...form, gold_primary_diagnosis: e.target.value})} />
              <input placeholder={t.name} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring mt-1" value={form.gold_primary_diag_name} onChange={e => setForm({...form, gold_primary_diag_name: e.target.value})} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.originalMainProcedure}</label>
              <input placeholder={t.code} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.original_main_procedure} onChange={e => setForm({...form, original_main_procedure: e.target.value})} />
              <input placeholder={t.name} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring mt-1" value={form.original_main_proc_name} onChange={e => setForm({...form, original_main_proc_name: e.target.value})} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.goldMainProcedure}</label>
              <input placeholder={t.code} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.gold_main_procedure} onChange={e => setForm({...form, gold_main_procedure: e.target.value})} />
              <input placeholder={t.name} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring mt-1" value={form.gold_main_proc_name} onChange={e => setForm({...form, gold_main_proc_name: e.target.value})} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t.difficulty}</label>
              <select className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring" value={form.difficulty} onChange={e => setForm({...form, difficulty: e.target.value})}>
                {['easy', 'medium', 'hard'].map(d => {
                  const label = d === 'easy' ? t.easy : d === 'medium' ? t.medium : t.hard;
                  return <option key={d} value={d}>{label}</option>;
                })}
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={handleCreate} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm shadow-primary/20">{t.save}</button>
            <button onClick={() => setShowForm(false)} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors">{t.cancel}</button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-3 px-4 font-semibold">{t.caseId}</th>
              <th className="py-3 px-4 font-semibold">{t.department}</th>
              <th className="py-3 px-4 font-semibold">{t.diagnosisGroup}</th>
              <th className="py-3 px-4 font-semibold">原始诊断 → 金标准</th>
              <th className="py-3 px-4 font-semibold">{t.difficulty}</th>
              <th className="py-3 px-4 font-semibold">{t.accuracy}</th>
              <th className="py-3 px-4 font-semibold">{t.actions}</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id} className="border-b hover:bg-accent">
                <td className="py-3 px-4 font-mono text-xs">{c.case_id}</td>
                <td className="py-3 px-4">{c.department}</td>
                <td className="py-3 px-4">{c.diagnosis_group}</td>
                <td className="py-3 px-4">
                  <span className="text-destructive">{c.original_primary_diagnosis}</span>
                  {' → '}
                  <span className="text-secondary font-medium">{c.gold_primary_diagnosis}</span>
                </td>
                <td className="py-3 px-4">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${c.difficulty === 'easy' ? 'bg-secondary/10 text-secondary' : c.difficulty === 'hard' ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary'}`}>
                    {c.difficulty === 'easy' ? t.easy : c.difficulty === 'hard' ? t.hard : t.medium}
                  </span>
                </td>
                <td className="py-3 px-4">
                  {c.agent_accuracy != null ? `${(c.agent_accuracy * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="py-3 px-4">
                  <button onClick={() => handleDelete(c.id)} className="text-destructive hover:text-destructive/80 transition-colors">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {cases.length === 0 && (
              <tr><td colSpan={7} className="py-8 text-center text-muted-foreground">{t.noGoldCases}</td></tr>
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {total > 0 && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-border">
            <span className="text-xs text-muted-foreground">
              共 {total} 条，第 {page} 页
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-xs px-3 py-1.5 rounded border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              {Array.from({ length: Math.min(5, Math.ceil(total / 10)) }, (_, i) => {
                const totalPages = Math.ceil(total / 10);
                let startPage: number;
                if (totalPages <= 5) {
                  startPage = 1;
                } else if (page <= 3) {
                  startPage = 1;
                } else if (page >= totalPages - 2) {
                  startPage = totalPages - 4;
                } else {
                  startPage = page - 2;
                }
                const pageNum = startPage + i;
                return pageNum <= totalPages ? (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`text-xs w-7 h-7 rounded border transition-colors ${pageNum === page ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-accent'}`}
                  >
                    {pageNum}
                  </button>
                ) : null;
              })}
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page >= Math.ceil(total / 10)}
                className="text-xs px-3 py-1.5 rounded border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setDeleteConfirm(null)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-sm mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-5">
              <p className="text-sm font-medium text-foreground">确定删除此金标准病例？</p>
              <p className="text-xs text-muted-foreground mt-1">此操作不可撤销。</p>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/20">
              <button onClick={() => setDeleteConfirm(null)} className="text-xs px-4 py-2 rounded-lg hover:bg-accent transition-colors">取消</button>
              <button onClick={confirmDelete} className="text-xs px-4 py-2 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors">删除</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
