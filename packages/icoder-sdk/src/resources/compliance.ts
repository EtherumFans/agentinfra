/** Compliance API resource — rule engine validation. */

import type { AxiosInstance } from 'axios';

export class ComplianceResource {
  constructor(private http: AxiosInstance) {}

  ruleEngineStatus() {
    return this.http.get('/api/compliance/rule-engine/status');
  }

  ruleEngineRules(ruleSet = 'medical_coding') {
    return this.http.get('/api/compliance/rule-engine/rules', { params: { rule_set: ruleSet } });
  }

  validate(ruleSet: string, structuredOutput: Record<string, unknown>, context: Record<string, unknown> = {}) {
    return this.http.post('/api/compliance/rule-engine/validate', {
      rule_set: ruleSet, structured_output: structuredOutput, context,
    });
  }
}
