import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const srcRoot = path.resolve(process.cwd(), 'src');
const page = fs.readFileSync(path.join(srcRoot, 'pages', 'AcceptInvitePage.tsx'), 'utf8');
const login = fs.readFileSync(path.join(srcRoot, 'pages', 'LoginPage.tsx'), 'utf8');
const app = fs.readFileSync(path.join(srcRoot, 'App.tsx'), 'utf8');
const api = fs.readFileSync(path.join(srcRoot, 'services', 'api.ts'), 'utf8');

describe('organization invitation browser credential boundary', () => {
  it('keeps invite credentials in the fragment and scrubs browser history', () => {
    expect(page).toContain("window.location.hash");
    expect(page).toContain("window.history.replaceState");
    expect(page).toContain("/login#token=");
    expect(page).not.toMatch(/sessionStorage/);
    expect(page).not.toMatch(/localStorage\.setItem\(['\"]invite/i);
    expect(login).toContain("/^#token=");
    expect(login).toContain("/accept-invite${inviteHash}");
  });

  it('mounts the acceptance route and calls the authenticated API', () => {
    expect(app).toContain('path="/accept-invite"');
    expect(api).toContain("api.post('/organizations/invites/accept', { token })");
    expect(page).toContain('orgApi.acceptInvite(token)');
  });
});
