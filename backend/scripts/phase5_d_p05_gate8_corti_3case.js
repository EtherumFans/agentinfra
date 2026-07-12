// Corti 3-case runner — inject this into the Corti console page via browser_run_code_unsafe
// Returns the full SSE-captured response per case
async (page) => {
  const results = [];

  // Pull credentials from page context
  const ctx = await page.evaluate(() => ({
    supabaseJwt: JSON.parse(localStorage.getItem('sb-api-auth-token') || '{}').access_token,
    cortiJwt: JSON.parse(sessionStorage.getItem('access-token:4c4193c7-c6bb-4a71-a275-0ed6c53172d0:f63bcaaa-d9a4-4c42-95c0-0d9d0788d636') || '{}').data,
    projectId: '4c4193c7-c6bb-4a71-a275-0ed6c53172d0',
    agentDefId: 'fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2',
  }));
  return ctx;
}
