import { useState } from 'react';

import { useAuthStore, OrgInfo } from '../../store';
import { authApi } from '../../services/api';
import { useT } from '../../i18n';

export default function OrgSwitcher() {
  const { organizations, currentOrgId, setOrganizations } = useAuthStore();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const t = useT();

  const currentOrg = organizations.find((o) => o.id === currentOrgId);
  const otherOrgs = organizations.filter((o) => o.id !== currentOrgId);

  const handleSwitch = async (org: OrgInfo) => {
    if (org.id === currentOrgId) {
      setOpen(false);
      return;
    }
    setSwitching(true);
    try {
      const { data } = await authApi.switchOrg(org.id);
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      setOrganizations(data.organizations || organizations, data.current_org_id || org.id);
      setOpen(false);
      window.location.reload();
    } catch {
      // silent
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={switching}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors"
      >
        <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
        <span className="max-w-[120px] truncate">
          {currentOrg?.name || (organizations.length === 0 ? t.orgSwitcherNoOrg : t.orgSwitcherSelectOrg)}
        </span>
        {organizations.length > 1 && (
          <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 w-64 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg py-1">
            <div className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              {t.orgSwitcherOrganizations}
            </div>
            {organizations.map((org) => (
              <button
                key={org.id}
                onClick={() => handleSwitch(org)}
                disabled={switching}
                className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-750 ${
                  org.id === currentOrgId ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-200'
                }`}
              >
                <span className="truncate flex-1">{org.name}</span>
                <span className="text-xs text-gray-400 ml-2 capitalize">{org.role}</span>
                {org.id === currentOrgId && (
                  <svg className="w-4 h-4 ml-1 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
              </button>
            ))}
            {otherOrgs.length === 0 && organizations.length === 0 && (
              <div className="px-3 py-2 text-sm text-gray-400">{t.orgSwitcherNoOrgsFound}</div>
            )}
            <div className="border-t border-gray-100 dark:border-gray-700 mt-1 pt-1">
              <a
                href="/settings"
                className="block w-full text-left px-3 py-2 text-sm text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-750"
                onClick={(e) => { e.preventDefault(); setOpen(false); window.location.href = '/settings?tab=organization'; }}
              >
                {t.orgSwitcherCreateManage}
              </a>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

