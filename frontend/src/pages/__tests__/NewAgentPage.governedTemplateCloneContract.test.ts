import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const source = fs.readFileSync(
  path.resolve(__dirname, '../NewAgentPage.tsx'),
  'utf8',
);

describe('New Agent governed template clone contract', () => {
  it('routes Pack-mastered templates through Agent Hub clone', () => {
    expect(source).toContain("selected.template_kind === 'governed_prebuilt'");
    expect(source).toContain('await agentHubApi.clone(');
    expect(source).toContain('selected.runtime_agent_id || selected.id');
    expect(source).toContain('clone.customize_url');
    expect(source).toContain('clone.project_agent_id');
  });

  it('keeps generic blank templates on the generic create path', () => {
    const governedBranch = source.indexOf(
      "selected.template_kind === 'governed_prebuilt'",
    );
    const genericCreate = source.indexOf('await agentsApi.create({', governedBranch);
    expect(governedBranch).toBeGreaterThanOrEqual(0);
    expect(genericCreate).toBeGreaterThan(governedBranch);
  });
});
