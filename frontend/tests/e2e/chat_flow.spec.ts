/**
 * Phase 3-B2 Loop 2 — Click-to-Chat UX (Gap 2.2) end-to-end test.
 *
 * Verifies the Hub → Clone → Chat → A2A Run loop with mocked backend
 * responses (so the test runs without a live backend). The mocked
 * responses follow the Loop 1 CloneResponse contract and the A2A v0.3
 * JSON-RPC envelope.
 *
 * Acceptance:
 *   - Click Hub "Chat / Use Agent" CTA → clone endpoint is called →
 *     navigation to /agents/{project_agent_id}/chat?preset={agent_ref}.
 *   - Chat page loads the cloned agent metadata, accepts input, clicks
 *     Run → A2A POST to /v1/message:send → result renders.
 *   - No console errors.
 */
import { test, expect, type Page } from '@playwright/test';

const PROJECT_AGENT_ID = 'mock-project-001';
const AGENT_REF = 'icoder/medical-coding-agent@2.0.0';
const AGENT_ID = 'medical-coding-agent';

const MOCK_AGENT = {
  id: PROJECT_AGENT_ID,
  name: 'Medical Coding Agent',
  description: 'iCoDer 官方医学编码 Agent (Corti-style MVP)',
  version: '2.0.0',
  category: 'medical-coding',
  icon: 'Stethoscope',
  expert_ids: ['coding-expert'],
  default_expert_id: 'coding-expert',
  config: {
    agent_ref: AGENT_REF,
    source_agent_ref: AGENT_REF,
    cloned_from_prebuilt: true,
  },
};

const MOCK_CLONE_RESPONSE = {
  project_agent_id: PROJECT_AGENT_ID,
  runtime_agent_id: AGENT_ID,
  source_agent_ref: AGENT_REF,
  chat_url: `/agents/${PROJECT_AGENT_ID}/chat`,
  customize_url: `/ai-studio/agents/${PROJECT_AGENT_ID}`,
  run_url: `/api/icoder/agents/${AGENT_ID}/v1/message:send`,
  cloned: true,
};

const MOCK_A2A_ENVELOPE = {
  jsonrpc: '2.0',
  id: 'mock-1',
  result: {
    id: 'task-mock-1',
    status: { state: 'completed' },
    parts: [
      {
        kind: 'data',
        data: {
          encounter_summary: { encounter_id: 'mock-001' },
          documentation_analysis: {
            completeness: 0.85,
            missing_elements: [],
            evidence_buckets: { primary_dx: 1, secondary_dx: 0, procedures: 0 },
          },
          code_assignment: {
            primary_diagnosis: { code: 'I50.900', label: '心功能不全', confidence: 0.92 },
            other_diagnoses: [],
            procedures: [],
          },
          documentation_gaps: [],
          uncodable_items: [],
          validation_summary: { rule_count: 12, passed: 12, failed: 0 },
          human_review: { required: true, reason: 'MVP / AI-assisted' },
          trace_refs: { run_id: 'run-mock-1' },
        },
      },
    ],
  },
};

async function mockBackend(page: Page) {
  // 1. Clone endpoint — return mock CloneResponse.
  await page.route('**/api/icoder/agents/medical-coding-agent/clone', (route) =>
    route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_CLONE_RESPONSE),
    }),
  );

  // 2. Agent definitions GET — return mock agent metadata.
  await page.route(
    `**/api/rest/v1/agent_definitions/${PROJECT_AGENT_ID}`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_AGENT),
      }),
  );

  // 3. A2A mainline POST — return mock JSON-RPC envelope.
  await page.route(
    '**/api/icoder/agents/medical-coding-agent/v1/message:send',
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_A2A_ENVELOPE),
      }),
  );
}

test.describe('Phase 3-B2 Loop 2 — Click-to-Chat UX', () => {
  test('Hub CTA clones + navigates to chat + A2A run loop', async ({ page }) => {
    await mockBackend(page);

    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // 1. Go to Agent Hub → Prebuilt tab.
    await page.goto('/ai-studio/agents');
    // Click the "预置AI智能体" tab button.
    const prebuiltTab = page.getByRole('button', { name: /预置|Prebuilt/i }).first();
    await prebuiltTab.click();
    await page.waitForTimeout(300);

    // 2. Find the Medical Coding Agent card and click "Chat / Use Agent".
    const chatCta = page.getByRole('button', { name: /Chat \/ Use Agent/ }).first();
    await expect(chatCta).toBeVisible();
    await chatCta.click();

    // 3. URL should now point at the chat page with preset query param.
    await page.waitForURL(
      new RegExp(`/agents/${PROJECT_AGENT_ID}/chat\\?preset=${encodeURIComponent(AGENT_REF)}$`),
      { timeout: 5000 },
    );

    // 4. Chat page should render the agent name + description.
    await expect(page.getByText('Medical Coding Agent')).toBeVisible();
    await expect(page.getByText(/ICD-10-CN 诊断编码/)).toBeVisible();

    // 5. Type into the input textarea.
    const textarea = page.locator('textarea').first();
    await textarea.fill('患者, 男, 65岁, 诊断为冠心病, 行冠脉造影。');

    // 6. Click Run.
    const runBtn = page.getByRole('button', { name: /^运行$/ }).first();
    await runBtn.click();

    // 7. Wait for result — the JSON view appears with the mocked code.
    await expect(page.getByText('运行结果').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('I50.900')).toBeVisible({ timeout: 5000 });

    // 8. No console errors.
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  test('route guard redirects when agent_definitions returns 404', async ({ page }) => {
    // If the project_agent_id doesn't exist in the DB, the chat page
    // must redirect to /ai-studio/agents (Loop 2 route guard).
    await page.route('**/api/rest/v1/agent_definitions/nonexistent-**', (route) =>
      route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }),
    );

    await page.goto('/agents/nonexistent-id/chat?preset=icoder/medical-coding-agent@2.0.0');
    // Should redirect to /ai-studio/agents after a short delay.
    await page.waitForURL('**/ai-studio/agents**', { timeout: 5000 });
    expect(page.url()).toContain('/ai-studio/agents');
  });
});
