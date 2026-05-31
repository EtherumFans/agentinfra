# @icoder/sdk

iCoDer JavaScript SDK — 面向中国医院的医疗 AI 智能体平台。

## 安装

```bash
npm install @icoder/sdk
```

## 快速开始

```js
import iCoDer from '@icoder/sdk';

const icoder = new iCoDer({
  baseURL: 'http://localhost:8000',
  auth: {
    accessToken: '<your-access-token>',
    refreshToken: '<your-refresh-token>',
  },
});

// 事实提取
const facts = await icoder.facts.extract('患者因腰痛伴左下肢放射痛3月就诊...', 'zh-CN');
console.log(facts.facts.diagnosis_facts);

// Agent 流式对话
const stream = await icoder.agents.stream('agent-id', '请分析以下病例...');
const reader = stream.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(new TextDecoder().decode(value));
}

// 用量查询
const usage = await icoder.usage.summary(30);
console.log(`近30天消耗积分: ${usage.credits_used}`);
```

## 资源

| 资源 | 说明 |
|------|------|
| `icoder.facts` | 事实提取 |
| `icoder.agents` | 智能体管理 + 流式对话 |
| `icoder.experts` | 专家管理 |
| `icoder.reviews` | 医学编码审核 |
| `icoder.speechToText` | 语音转录 |
| `icoder.textGen` | 文书生成 |
| `icoder.billing` | 计费余额 |
| `icoder.usage` | 用量统计 |
| `icoder.oauth` | OAuth 客户端管理 |

## License

MIT
