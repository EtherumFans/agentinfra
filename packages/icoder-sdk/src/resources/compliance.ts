/** Compliance API resource — rule engine validation. */

import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export class ComplianceResource {
  constructor(private http: AxiosInstance) {}

  ruleEngineStatus(options?: iCoDerRequestOptions) {
    return this.http.get('/api/compliance/rule-engine/status', requestConfig(options));
  }

  ruleEngineRules(ruleSet = 'medical_coding', options?: iCoDerRequestOptions) {
    return this.http.get(
      '/api/compliance/rule-engine/rules',
      requestConfig(options, { rule_set: ruleSet }),
    );
  }

  validate(
    ruleSet: string,
    structuredOutput: Record<string, unknown>,
    context: Record<string, unknown> = {},
    options?: iCoDerRequestOptions,
  ) {
    return this.http.post('/api/compliance/rule-engine/validate', {
      rule_set: ruleSet, structured_output: structuredOutput, context,
    }, requestConfig(options));
  }
}
