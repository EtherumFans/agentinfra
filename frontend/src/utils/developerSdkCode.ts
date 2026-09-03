export interface DeveloperApiEndpoint {
  key: string;
  method: 'GET' | 'POST';
  path: string;
  label: string;
  sampleBody: string | null;
  headers?: Record<string, string>;
}

export const DEVELOPER_API_ENDPOINTS: DeveloperApiEndpoint[] = [
  {
    key: 'facts-extract',
    method: 'POST',
    path: '/api/v2/tools/extract-facts',
    label: 'POST /api/v2/tools/extract-facts',
    sampleBody: JSON.stringify({
      context: [{
        type: 'text',
        text: '患者因腰痛伴左下肢放射痛3月就诊。查体：腰椎活动受限，左下肢直腿抬高试验阳性。',
      }],
      outputLanguage: 'zh-CN',
    }, null, 2),
  },
  {
    key: 'agents-run',
    method: 'POST',
    path: '/api/icoder/agents/note-completeness-agent/v1/message:send',
    label: 'POST /api/icoder/agents/{id}/v1/message:send (A2A)',
    headers: { 'A2A-Protocol-Version': '0.3' },
    sampleBody: JSON.stringify({
      jsonrpc: '2.0',
      id: 'q-1',
      method: 'message/send',
      params: {
        message: {
          role: 'user',
          parts: [{ kind: 'text', text: '请检查以下去标识病历的完整性。' }],
        },
      },
    }, null, 2),
  },
  {
    key: 'coding',
    method: 'POST',
    path: '/api/v1/coding/predict',
    label: 'POST /api/v1/coding/predict',
    sampleBody: JSON.stringify({
      text: '主诉：腹痛3天。',
      mode: 'corti_like_fast',
      coding_systems: ['icd10cn', 'icd9cm3'],
      include_evidence: true,
      include_trace: true,
      filter: { include: [], exclude: [], expand: true },
    }, null, 2),
  },
  {
    key: 'usage',
    method: 'GET',
    path: '/api/usage/summary',
    label: 'GET /api/usage/summary',
    sampleBody: null,
  },
];

export function buildCredentialEnv(
  baseURL: string,
  clientId: string,
  clientSecret: string,
): string {
  return [
    `ICODER_BASE_URL=${baseURL.replace(/\/$/, '')}`,
    `ICODER_CLIENT_ID=${clientId || '<client-id>'}`,
    `ICODER_CLIENT_SECRET=${clientSecret || '<copy-secret-when-created>'}`,
  ].join('\n');
}

export function buildQuickstartSdkSnippets(baseURL: string) {
  const safeBaseURL = JSON.stringify(baseURL.replace(/\/$/, ''));
  return {
    javascript: `import iCoDer, { iCoDerClient } from "@icoder/sdk";

const baseURL = process.env.ICODER_BASE_URL ?? ${safeBaseURL};
const clientId = process.env.ICODER_CLIENT_ID;
const clientSecret = process.env.ICODER_CLIENT_SECRET;
if (!clientId || !clientSecret) throw new Error("Missing iCoDer client credentials");

const authClient = new iCoDerClient({
  baseURL,
  auth: { accessToken: "" },
});
const token = await authClient.authenticate(clientId, clientSecret);
const icoder = new iCoDer({
  baseURL,
  auth: { accessToken: token.access_token },
});

const facts = await icoder.facts.extract({
  context: [{ type: "text", text: "患者因腰痛伴左下肢放射痛3月就诊。" }],
  outputLanguage: "zh-CN",
});
console.log("Facts:", facts.facts);
console.log("Credits:", facts.usageInfo.creditsConsumed);`,
    dotnet: `using Icoder.Sdk;

var baseUri = new Uri(
    Environment.GetEnvironmentVariable("ICODER_BASE_URL") ?? ${safeBaseURL});
var clientId = Environment.GetEnvironmentVariable("ICODER_CLIENT_ID")
    ?? throw new InvalidOperationException("Missing ICODER_CLIENT_ID");
var clientSecret = Environment.GetEnvironmentVariable("ICODER_CLIENT_SECRET")
    ?? throw new InvalidOperationException("Missing ICODER_CLIENT_SECRET");

using var authClient = new ICoDerClient(new ICoDerClientOptions { BaseUri = baseUri });
var token = await authClient.AuthenticateClientCredentialsAsync(clientId, clientSecret);
using var icoder = new ICoDerClient(new ICoDerClientOptions
{
    BaseUri = baseUri,
    AccessToken = token.AccessToken,
});

var facts = await icoder.Facts.ExtractAsync(new FactExtractionRequest
{
    Context = [new FactExtractionContext
    {
        Text = "患者因腰痛伴左下肢放射痛3月就诊。",
    }],
    OutputLanguage = "zh-CN",
});
Console.WriteLine($"Facts: {facts.Facts.Count}");
Console.WriteLine($"Credits: {facts.UsageInfo.CreditsConsumed}");`,
  };
}

export function buildMedicalCodingSnippets(options: {
  baseURL: string;
  text: string;
  mode: 'corti_like_fast' | 'medcoder_deep';
  codingSystems: string[];
  includeCodes?: string[];
  excludeCodes?: string[];
  expand?: boolean;
}) {
  const body = {
    text: options.text,
    mode: options.mode,
    coding_systems: options.codingSystems,
    include_evidence: true,
    include_trace: true,
    filter: {
      include: options.includeCodes ?? [],
      exclude: options.excludeCodes ?? [],
      expand: options.expand ?? true,
    },
  };
  return {
    javascript: `import iCoDer from "@icoder/sdk";

const icoder = new iCoDer({
  baseURL: ${JSON.stringify(options.baseURL.replace(/\/$/, ''))},
  auth: { accessToken: "<tenant-bound-access-token>" },
});

const result = await icoder.medicalCoding.predict(${JSON.stringify(body, null, 2)});
console.log(result.codes, result.cost, result.trace_id);`,
    json: JSON.stringify({
      endpoint: '/api/v1/coding/predict',
      method: 'POST',
      headers: {
        Authorization: 'Bearer <tenant-bound-access-token>',
        'Content-Type': 'application/json',
      },
      body,
    }, null, 2),
  };
}
