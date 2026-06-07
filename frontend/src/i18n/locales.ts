// iCoDer i18n — zh-CN (default) + en-US
// Chinese expressions tailored for Chinese hospital medical coding scenarios

export type Locale = 'zh-CN' | 'en-US';

export interface LocaleDict {
  // Common
  appName: string;
  appTagline: string;
  save: string;
  cancel: string;
  confirm: string;
  delete: string;
  search: string;
  loading: string;
  noData: string;
  back: string;
  dismiss: string;

  // Header
  notifications: string;
  toggleSidebar: string;

  // Sidebar
  home: string;
  developerQuickstart: string;
  developerDocs: string;
  creating: string;
  aiStudio: string;
  overview: string;
  agents: string;
  speechToText: string;
  textGeneration: string;
  embeddedAssistant: string;
  factExtraction: string;
  medicalCoding: string;
  manage: string;
  apiClients: string;
  apiClientsManage: string;
  team: string;
  billing: string;
  usage: string;
  settings: string;
  data: string;
  codeDictionaries: string;
  ruleLibraries: string;
  goldCases: string;
  evaluation: string;
  support: string;
  getHelp: string;
  ticketsPortal: string;
  orgSwitch: string;
  orgManage: string;
  orgMembers: string;
  orgInvite: string;
  orgInviteEmail: string;
  orgNoOrg: string;
  orgSelectOrg: string;
  orgCreate: string;
  orgName: string;
  orgPlan: string;
  orgInviteRole: string;
  orgRemoveMember: string;
  orgRoleOwner: string;
  orgRoleAdmin: string;
  orgRoleMember: string;
  orgRoleViewer: string;

  // Login
  login: string;
  loginTitle: string;
  username: string;
  password: string;
  loginButton: string;
  demoHint: string;
  loggingIn: string;

  // Home
  getStartedBanner: string;
  getStartedDesc: string;
  aiStudioBtn: string;
  developerQuickstartBtn: string;
  overviewSection: string;
  availableCredits: string;
  addCredits: string;
  totalCreditsConsumed: string;
  viewUsage: string;
  creditsConsumed: string;
  comparePeriod: string;
  last30Days: string;
  allApiClients: string;
  daily: string;
  weekly: string;
  monthly: string;
  documentation: string;
  authentication: string;
  guides: string;
  apiReference: string;
  sdksAndTools: string;
  javascriptSdk: string;
  dotnetSdk: string;
  postman: string;
  aiCodingTools: string;
  needHelp: string;
  chatWithUs: string;
  openTicket: string;
  last7DaysLabel: string;
  last30DaysLabel: string;
  last90DaysLabel: string;

  // AI Studio Overview
  aiStudioTitle: string;
  aiStudioDesc: string;
  openBtn: string;

  // Agents
  agentsTitle: string;
  agentsDesc: string;
  newAgent: string;
  all: string;
  myAgents: string;
  prebuiltAgents: string;
  createdBy: string;
  searchAgents: string;
  noAgents: string;
  createAgent: string;
  creatingAgent: string;
  noMyAgents: string;
  noMyAgentsHint: string;
  browsePrebuilt: string;
  noMatchingAgents: string;
  noMatchingAgentsHint: string;
  clearFilter: string;
  allCreators: string;
  category: string;
  description: string;
  optional: string;
  aiGenerate: string;
  generating: string;
  bindExperts: string;
  selectedCount: string;
  noMatchingExperts: string;
  cloneFromExisting: string;
  cloneAction: string;
  cloneHint: string;
  useTemplate: string;
  useTemplateHint: string;
  searchTemplates: string;
  loadingTemplates: string;
  noTemplatesAvailable: string;
  agentDescPlaceholder: string;
  newAgentModalDesc: string;
  confirmDeleteAgent: string;
  deleteIrreversible: string;
  confirmDeleteBtn: string;

  // Medical Coding
  medicalCodingTitle: string;
  medicalCodingDesc: string;
  predictCodes: string;
  config: string;
  codingSystems: string;
  apiClient: string;
  inputLabel: string;
  outputLabel: string;
  useSample: string;
  clearInput: string;
  copyInput: string;
  enterClinicalText: string;
  predictedCodesWillShow: string;
  eventInspector: string;
  creditsConsumedLabel: string;
  viewFullReport: string;
  systemPrompt: string;
  codingSystem: string;
  confidenceThreshold: string;
  outputLanguage: string;
  model: string;
  includeEvidence: string;
  autoValidate: string;
  primaryDiagnosis: string;
  mainProcedure: string;
  allCandidates: string;
  confidence: string;
  getStartedWith: string;
  resetLiveCost: string;

  // Sample cases
  hospitalMedicalRecord: string;
  hospitalMedicalRecordDesc: string;
  gpTranscript: string;
  gpTranscriptDesc: string;
  orthopedicReferral: string;
  orthopedicReferralDesc: string;
  guidedDemo: string;
  guidedDemoDesc: string;

  // Sample document types
  admissionRecord: string;
  operationRecord: string;
  outpatientRecord: string;
  consultationRecord: string;

  // Medical Coding — Corti-aligned extras
  samples: string;
  openGuide: string;
  dismissGuide: string;
  selectCodingSystem: string;
  selectCodingSystemDesc: string;
  guideStepSample: string;
  guideStepSystem: string;
  guideStepSampleDesc: string;
  startByAddingText: string;
  next: string;
  done: string;
  add: string;
  ready: string;
  expand: string;
  include: string;
  exclude: string;
  filterCodes: string;
  addCodes: string;
  noSystemsSelected: string;
  processingFailed: string;
  sampleLoaded: string;
  startingPrediction: string;
  addIncludeCode: string;
  addExcludeCode: string;
  enterCodePlaceholder: string;
  tableCode: string;
  tableDescription: string;
  tableConfidence: string;
  medicalCodingBreadcrumb: string;
  tabCode: string;
  failedPrefix: string;
  completedPrefix: string;
  preGuardViolations: string;
  contractVerified: string;
  safety: string;
  schema: string;
  resetSettings: string;

  // Fact Extraction
  factExtractionTitle: string;
  factExtractionDesc: string;
  extractFacts: string;
  generatedFactsWillShow: string;

  // Case Review
  caseReview: string;
  reviewId: string;
  codesReviewed: string;
  pending: string;
  completeReview: string;
  reviewCompleted: string;
  validationSummary: string;
  supported: string;
  needsReview: string;
  unsupported: string;
  evidenceBinding: string;
  docGaps: string;
  codeCandidatesReview: string;
  review: string;
  reject: string;
  modify: string;
  reasonRequired: string;
  submitDecision: string;
  submitting: string;
  documentationGaps: string;
  suggestion: string;
  reviewerNotes: string;
  notesPlaceholder: string;

  // Workbench
  codingWorkbench: string;
  medicalRecord: string;
  evidence: string;
  candidateCodes: string;
  report: string;
  runCodingReview: string;
  analyzing: string;
  humanReview: string;
  exportData: string;
  noEncounterLoaded: string;
  goToHome: string;
  noEvidence: string;
  runReviewHint: string;
  noCandidates: string;
  noReport: string;
  completeReviewHint: string;
  humanReviewLabel: string;

  // Gold Cases
  goldCasesTitle: string;
  goldCasesDesc: string;
  addGoldCase: string;
  newGoldCase: string;
  department: string;
  diagnosisGroup: string;
  originalPrimaryDiagnosis: string;
  goldPrimaryDiagnosis: string;
  originalMainProcedure: string;
  goldMainProcedure: string;
  difficulty: string;
  easy: string;
  medium: string;
  hard: string;
  caseId: string;
  accuracy: string;
  actions: string;
  noGoldCases: string;

  // Evaluation
  evaluationTitle: string;
  evaluationDesc: string;
  runEvaluation: string;
  running: string;
  primaryDiagAccuracy: string;
  mainProcAccuracy: string;
  evidenceCompleteness: string;
  hallucinationRate: string;
  missingCodeRecall: string;
  overallScore: string;
  target: string;
  perCaseResults: string;
  noEvaluationData: string;
  runEvaluationHint: string;

  // Code Dictionaries
  codeDictionariesTitle: string;
  codeDictionariesDesc: string;
  searchByDisease: string;
  code: string;
  name: string;
  chapter: string;
  score: string;
  valid: string;
  builtInCodes: string;
  searchForCodes: string;

  // Rule Libraries
  ruleLibrariesTitle: string;
  ruleLibrariesDesc: string;
  retrieveRules: string;
  searching: string;
  relevance: string;
  examples: string;
  builtInRules: string;
  enterTopic: string;

  // API Clients
  apiClientsTitle: string;
  apiClientsDesc: string;
  newApiKey: string;
  createApiKey: string;
  keyName: string;
  noApiKeys: string;

  // Team
  teamTitle: string;
  teamDesc: string;
  inviteMember: string;
  owner: string;
  coder: string;
  deptHead: string;

  // Billing
  billingTitle: string;
  billingDesc: string;
  transactionHistory: string;
  creditPurchase: string;
  medicalCodingApi: string;

  // Usage
  usageTitle: string;
  usageDesc: string;
  totalRequests: string;
  creditsUsed: string;
  avgResponseTime: string;
  recentActivity: string;
  requests: string;

  // Settings
  settingsTitle: string;
  account: string;
  fullName: string;
  role: string;
  systemInformation: string;
  product: string;
  llmProvider: string;
  pipeline: string;
  environment: string;
  development: string;
  security: string;
  securityDesc: string;
  dataAndCompliance: string;
  dataComplianceDesc: string;

  // Developer Quickstart
  developerQuickstartTitle: string;
  developerQuickstartDesc: string;
  step1Title: string;
  step1Desc: string;
  step2Title: string;
  step2Desc: string;
  step3Title: string;
  step3Desc: string;
  generateNewKey: string;
  authenticationGuide: string;
  apiReferenceLink: string;
  javascriptSdkLink: string;
  postmanCollection: string;
  integrationGuide: string;
  ehrCompatibility: string;

  // Speech To Text
  speechToTextTitle: string;
  speechToTextDesc: string;
  record: string;
  audioInput: string;
  transcribedText: string;

  // Text Generation
  textGenerationTitle: string;
  textGenerationDesc: string;
  generate: string;
  generatedText: string;
  dischargeSummary: string;
  progressNote: string;
  referralLetter: string;

  // Embedded Assistant
  embeddedAssistantTitle: string;
  embeddedAssistantDesc: string;
  embedCode: string;
  configuration: string;
  mode: string;
  ambient: string;
  onDemand: string;
  hybrid: string;
  specialty: string;
  cardiology: string;
  orthopedics: string;
  generalPractice: string;
  neurology: string;
  oncology: string;
  autoSuggest: string;
  resources: string;
  jsSdkReference: string;
  ehrMatrix: string;
  copy: string;
  copied: string;

  // ── Product Hub Homepage tabs ──
  productHubTranscribe: string;
  productHubTranscribeDesc: string;
  productHubTranscribeCta: string;
  productHubTranscribeSecondary: string;
  productHubTranscribeBuild: string;
  productHubDocument: string;
  productHubDocumentDesc: string;
  productHubDocumentCta: string;
  productHubDocumentSecondary: string;
  productHubDocumentBuild: string;
  productHubChat: string;
  productHubChatDesc: string;
  productHubChatCta: string;
  productHubChatSecondary: string;
  productHubChatBuild: string;
  productHubCode: string;
  productHubCodeDesc: string;
  productHubCodeCta: string;
  productHubCodeSecondary: string;
  productHubCodeBuild: string;
  productHubNew: string;
  productHubDevQuickstart: string;
  // ── Homepage common ──
  apiRequests: string;
  avgResponseTimeMs: string;
  milliseconds: string;
  recentEncounters: string;
  recentReviews: string;
  noEncounters: string;
  noReviews: string;
  completed: string;
  reviewing: string;
  unknown: string;
  inReview: string;
  // ── AI Studio Overview ──
  overviewTitle: string;
  overviewSubtitle: string;
  overviewExplore: string;
  overviewExploreDesc: string;
  overviewInspect: string;
  overviewInspectDesc: string;
  overviewConfigure: string;
  overviewConfigureDesc: string;
  overviewExploreCapabilities: string;
  overviewReadyToCode: string;
  overviewDevQuickstart: string;
  overviewExploreBtn: string;
  overviewDocsBtn: string;
  overviewAgentsDesc: string;
  overviewSttDesc: string;
  overviewTextGenDesc: string;
  overviewEmbeddedDesc: string;
  overviewFactExtDesc: string;
  overviewMedCodeDesc: string;
  // ── Developer Quickstart ──
  devQsTitle: string;
  devQsSubtitle: string;
  devQsApiDocs: string;
  devQsAiToolsTab: string;
  devQsJsSdkTab: string;
  devQsDotNetTab: string;
  devQsAiToolsDesc: string;
  devQsStep1Title: string;
  devQsStep2Title: string;
  devQsStep3Title: string;
  devQsStep2Hint: string;
  devQsStep3Hint: string;
  devQsPromptLabel: string;
  devQsOpenIn: string;
  devQsManageClients: string;
  devQsCopyEnv: string;
  devQsGenerateCreds: string;
  devQsGenerating: string;
  devQsViewCreds: string;
  devQsCopyCreds: string;
  devQsInstallNpm: string;
  devQsInstallDotnet: string;
  devQsJsCodeHint: string;
  devQsDotnetCodeHint: string;
  devQsReadyTitle: string;
  devQsWalkthrough1: string;
  devQsWalkthrough2: string;
  devQsWalkthrough3: string;
  devQsWalkthrough4: string;
  devQsDefaultClient: string;
  defaultLabel: string;
  devQsCredsFlow: string;
  devQsCredsFlowDotnet: string;
  devQsApiPlaygroundDesc: string;
  devQsApiEndpoint: string;
  devQsRequestBody: string;
  devQsNoRequestBody: string;
  devQsSending: string;
  devQsSendRequest: string;
  devQsResponse: string;
  // ── Use cases ──
  useCaseDictation: string;
  useCaseScribe: string;
  useCaseCoding: string;
  useCaseChat: string;
  // ── Misc
  yes: string;
  no: string;
  none: string;
  na: string;
  addContext: string;
  addCustomExpert: string;
  addExpert: string;
  addFile: string;
  addJson: string;
  addText: string;
  agentDetailName: string;
  agentNamePlaceholder: string;
  agentNotFound: string;
  allCategories: string;
  and: string;
  askTheAgentDesc: string;
  askTheAgentPlaceholder: string;
  askTheAgentTitle: string;
  backToAgentList: string;
  beforeUsing: string;
  bringYourOwnMcpExpert: string;
  browseExpertLibrary: string;
  byoMcpDesc: string;
  byoMcpExpert: string;
  clickToDefinePrompt: string;
  confirmDelete: string;
  confirmDeleteExpert: string;
  createExpert: string;
  createFailed: string;
  createFirstExpert: string;
  creatingExpert: string;
  customMcpExpert: string;
  deleteConfirmDesc: string;
  deleteConfirmMessage: string;
  deleteConfirmTitle: string;
  deleteFailed: string;
  discoverTools: string;
  discoverToolsFailed: string;
  discoveredToolsCount: string;
  discoveringTools: string;
  enterQueryOrClinicalText: string;
  enterUsernamePassword: string;
  errorPrefix: string;
  examplePrefix: string;
  expertLibrary: string;
  expertLibraryDesc: string;
  expertName: string;
  experts: string;
  externalTicketSystem: string;
  findAgent: string;
  jsonData: string;
  loadExpertsFailed: string;
  loginFailed: string;
  mcpCount: string;
  mcpServerUrl: string;
  mcpServerUrlPlaceholder: string;
  mcpServers: string;
  myExperts: string;
  myMcpExpert: string;
  noExpertsBound: string;
  noExpertsFound: string;
  openTicketSystem: string;
  prebuilt: string;
  prebuiltTag: string;
  privacyPolicy: string;
  readMore: string;
  run: string;
  runExpert: string;
  savedAgent: string;
  savingAgent: string;
  searchExperts: string;
  sessionContextRestored: string;
  showLess: string;
  suggestPrompt: string;
  systemPromptPlaceholder: string;
  termsOfService: string;
  thinking: string;
  ticketsDesc: string;
  ticketsManagedElsewhere: string;
  ticketsTitle: string;
  usageLabel: string;
  viewDetails: string;
  viewDocumentation: string;
  welcomeBack: string;
  whatCanYouDo: string;
  // Embedded Assistant
  embedInitializing: string;
  embedPreview: string;
  embedPreviewSession: string;
  embedDesktopView: string;
  embedMobileView: string;
  embedRestartSession: string;
  embedOnRefresh: string;
  embedCopyEmbedCode: string;
  embedOpenInNewWindow: string;
  embedRecording: string;
  embedWriteSomething: string;
  embedStartRecordingHint: string;
  embedTranscriptionPlaceholder: string;
  embedAiChat: string;
  embedAiChatDesc: string;
  embedAskQuestion: string;
  embedStopRecording: string;
  embedVoiceInput: string;
  embedStop: string;
  embedRecord: string;
  embedSettingsLabel: string;
  embedCodeLabel: string;
  embedRestartSessionHint: string;
  embedSessionDefaults: string;
  embedPrimaryLanguage: string;
  embedDefaultMode: string;
  embedModeInPerson: string;
  embedModeVirtual: string;
  embedFeatures: string;
  embedFeatureAllowVirtual: string;
  embedFeatureShowTitle: string;
  embedFeatureEnableAiChat: string;
  embedFeatureShowFeedback: string;
  embedFeatureEnableEditor: string;
  embedFeatureShowNav: string;
  embedFeatureShowSync: string;
  embedAppearance: string;
  embedPrimaryColor: string;
  embedLocaleSection: string;
  embedInterfaceLanguage: string;
  embedDictationLanguage: string;
  embedNewToAssistant: string;
  embedTakeTour: string;
  embedDismiss: string;
  embedSkipTour: string;
  embedPrevStep: string;
  embedNextStep: string;
  embedGetStarted: string;
  // Orchestration Pipeline
  orchestrationTitle: string;
  orchestrationDesc: string;
  orchestrationSelectEncounter: string;
  orchestrationExistingEncounter: string;
  orchestrationNewClinicalText: string;
  orchestrationEncounterPlaceholder: string;
  orchestrationNoEncounterFound: string;
  orchestrationEnterClinicalText: string;
  orchestrationPipelineSteps: string;
  orchestrationProgress: string;
  orchestrationStatusIdle: string;
  orchestrationStatusRunning: string;
  orchestrationStatusCompleted: string;
  orchestrationStatusFailed: string;
  orchestrationRunPipeline: string;
  orchestrationDiagnosisCandidates: string;
  orchestrationProcedureCandidates: string;
  orchestrationDrgImpact: string;
  orchestrationDocumentationGaps: string;
  orchestrationHumanChecklist: string;
  orchestrationHumanReview: string;
  orchestrationApprove: string;
  orchestrationReject: string;
  orchestrationRationale: string;
  orchestrationRationalePlaceholder: string;
  orchestrationAuditTrail: string;
  orchestrationNoAuditEvents: string;
  orchestrationViewReport: string;
  orchestrationReportMarkdown: string;
  orchestrationReportHtml: string;
  orchestrationEventLog: string;
}

const zhCN: LocaleDict = {
  // Common
  appName: 'iCoDer Console',
  appTagline: '可审计的临床AI',
  save: '保存',
  cancel: '取消',
  confirm: '确认',
  delete: '删除',
  search: '搜索',
  loading: '加载中...',
  noData: '暂无数据',
  back: '返回',
  dismiss: '关闭',

  // Header
  notifications: '通知',
  toggleSidebar: '切换侧边栏',

  // Sidebar
  home: '首页',
  developerQuickstart: '开发者快速入门',
  developerDocs: '开发者文档',
  creating: '创建中...',
  aiStudio: 'AI Studio',
  overview: '总览',
  agents: 'AI智能体',
  speechToText: '语音转录',
  textGeneration: '文书生成',
  embeddedAssistant: '嵌入助手',
  factExtraction: '事实提取',
  medicalCoding: '医学编码',
  manage: '管理',
  apiClients: 'API 客户端',
  apiClientsManage: '管理 API 客户端',
  team: '团队',
  billing: '计费',
  usage: '用量',
  settings: '设置',
  data: '数据管理',
  codeDictionaries: '编码字典',
  ruleLibraries: '规则库',
  goldCases: '金标准病例',
  evaluation: 'AI智能体评估',
  support: '支持',
  getHelp: '获取帮助',
  ticketsPortal: '工单中心',

  // Login
  login: '登录',
  loginTitle: '登录 iCoDer',
  username: '用户名',
  password: '密码',
  loginButton: '登 录',
  demoHint: '演示账号：admin / admin123',
  loggingIn: '登录中...',

  // Home
  getStartedBanner: '开始使用 iCoDer Console',
  getStartedDesc: '在 AI Studio 中立即测试编码能力，或跟随开发者快速入门发起您的第一个 API 请求',
  aiStudioBtn: 'AI Studio',
  developerQuickstartBtn: '开发者快速入门',
  overviewSection: '概览',
  availableCredits: '可用额度',
  addCredits: '充值',
  totalCreditsConsumed: '累计消耗额度',
  viewUsage: '查看用量',
  creditsConsumed: '额度消耗',
  comparePeriod: '对比周期',
  last30Days: '近30天',
  allApiClients: '全部 API 客户端',
  daily: '日',
  weekly: '周',
  monthly: '月',
  documentation: '文档',
  authentication: '认证方式',
  guides: '开发指南',
  apiReference: 'API 参考',
  sdksAndTools: 'SDK 与工具',
  javascriptSdk: 'JavaScript SDK',
  dotnetSdk: '.NET SDK',
  postman: 'Postman',
  aiCodingTools: 'AI 编码工具',
  needHelp: '需要帮助？',
  chatWithUs: '在线咨询',
  openTicket: '提交工单',
  last7DaysLabel: '近7天',
  last30DaysLabel: '近30天',
  last90DaysLabel: '近90天',

  // AI Studio Overview
  aiStudioTitle: 'AI Studio',
  aiStudioDesc: '测试和配置医疗 AI AI智能体。每个AI智能体处理临床数据并返回结构化、可审计的结果。',
  openBtn: '打开',

  // Agents
  agentsTitle: 'AI智能体',
  agentsDesc: '构建医疗 AI AI智能体，在您的业务系统中执行任务',
  newAgent: '新建AI智能体',
  all: '全部',
  myAgents: '我的AI智能体',
  prebuiltAgents: '预置AI智能体',
  createdBy: '创建者',
  searchAgents: '搜索AI智能体...',
  noAgents: '暂无AI智能体',
  createAgent: '创建AI智能体',
  creatingAgent: '创建中...',
  noMyAgents: '还没有AI智能体',
  noMyAgentsHint: '创建您的第一个AI智能体，或从预置模板快速开始',
  browsePrebuilt: '浏览预置',
  noMatchingAgents: '没有匹配的AI智能体',
  noMatchingAgentsHint: '尝试调整搜索条件或筛选器',
  clearFilter: '清除筛选',
  allCreators: '所有创建者',
  category: '类别',
  description: '描述',
  optional: '（可选）',
  aiGenerate: 'AI 生成',
  generating: '生成中...',
  bindExperts: '关联专家',
  selectedCount: '{count} 个已选',
  noMatchingExperts: '无匹配的专家',
  cloneFromExisting: '从已有AI智能体克隆',
  cloneAction: '克隆',
  cloneHint: '选择一个AI智能体作为模板，将预填其名称、描述和系统提示词。',
  useTemplate: '使用模板',
  useTemplateHint: '选择一个模板以预填名称、描述和系统提示词',
  searchTemplates: '搜索模板',
  loadingTemplates: '加载模板中...',
  noTemplatesAvailable: '暂无可用模板',
  agentDescPlaceholder: '简要描述AI智能体的用途和功能',
  newAgentModalDesc: '配置AI智能体的名称、行为和关联的专家',
  confirmDeleteAgent: '确定要删除 "{name}" 吗？',
  deleteIrreversible: '此操作不可恢复',
  confirmDeleteBtn: '确认删除',

  // Medical Coding
  medicalCodingTitle: '医学编码',
  medicalCodingDesc: '将非结构化临床文本（如入院记录、出院小结、病程记录等）转换为结构化的医学编码。',
  predictCodes: '预测编码',
  config: '配置',
  codingSystems: '编码体系',
  apiClient: 'API 客户端',
  inputLabel: '输入',
  outputLabel: '输出',
  useSample: '使用样例',
  clearInput: '清空输入',
  copyInput: '复制输入',
  enterClinicalText: '请输入临床文本...',
  predictedCodesWillShow: '预测编码结果将在此显示',
  eventInspector: '事件检查器',
  creditsConsumedLabel: '已消耗额度',
  viewFullReport: '查看完整报告',
  systemPrompt: '系统提示词',
  codingSystem: '编码体系',
  confidenceThreshold: '置信度阈值',
  outputLanguage: '输出语言',
  model: '模型',
  includeEvidence: '在输出中包含证据',
  autoValidate: '自动校验编码规则',
  primaryDiagnosis: '主要诊断',
  mainProcedure: '主要手术/操作',
  allCandidates: '全部候选编码',
  confidence: '置信度',
  getStartedWith: '快速开始',
  resetLiveCost: '重置费用',

  // Sample cases
  hospitalMedicalRecord: '住院病历',
  hospitalMedicalRecordDesc: '含主诉、现病史、既往史、体格检查、影像学及出院诊断的完整入院记录',
  gpTranscript: '全科门诊记录',
  gpTranscriptDesc: '含症状描述和初步评估的门诊就诊记录',
  orthopedicReferral: '骨科转诊单',
  orthopedicReferralDesc: '含影像学发现和疑似诊断的专科转诊记录',
  guidedDemo: '引导演示',
  guidedDemoDesc: '交互式引导，逐步了解医学编码AI智能体的使用方法',

  // Sample document types
  admissionRecord: '入院记录',
  operationRecord: '手术记录',
  outpatientRecord: '门诊病历',
  consultationRecord: '会诊记录',

  // Medical Coding — Corti-aligned extras
  samples: '样例',
  openGuide: '打开引导',
  dismissGuide: '关闭引导',
  selectCodingSystem: '选择编码体系',
  selectCodingSystemDesc: '勾选要在本次预测中使用的编码体系（与右侧设置共享）',
  guideStepSample: '选择文书样例',
  guideStepSystem: '选择编码体系',
  guideStepSampleDesc: '选择一份样本文档，向导将自动填入输入区并触发预测',
  startByAddingText: '开始添加文本输入',
  next: '下一步',
  done: '完成',
  add: '添加',
  ready: '就绪',
  expand: '展开',
  include: '包含',
  exclude: '排除',
  filterCodes: '筛选编码',
  addCodes: '添加编码',
  noSystemsSelected: '未选择编码体系',
  processingFailed: '处理失败',
  sampleLoaded: '已加载样例',
  startingPrediction: '开始预测...',
  addIncludeCode: '添加包含编码',
  addExcludeCode: '添加排除编码',
  enterCodePlaceholder: '输入编码（如 J18.1）',
  tableCode: '编码',
  tableDescription: '描述',
  tableConfidence: '置信度',
  medicalCodingBreadcrumb: '医学编码',
  tabCode: '代码',
  failedPrefix: '失败',
  completedPrefix: '已完成',
  preGuardViolations: '预检查：{count} 个违规',
  contractVerified: '合约：{status}',
  safety: '安全',
  schema: '架构',
  resetSettings: '重置设置',

  // Fact Extraction
  factExtractionTitle: '事实提取',
  factExtractionDesc: '从非结构化医学文本中提取结构化临床事实（诊断、手术操作、药物、解剖部位、病因等）。',
  extractFacts: '提取事实',
  generatedFactsWillShow: '提取的临床事实将在此显示',

  // Case Review
  caseReview: '病例审核',
  reviewId: '审核编号',
  codesReviewed: '已审核编码',
  pending: '待处理',
  completeReview: '完成审核',
  reviewCompleted: '审核已完成',
  validationSummary: '验证摘要',
  supported: '有证据支持',
  needsReview: '需人工复核',
  unsupported: '无证据支持',
  evidenceBinding: '证据绑定率',
  docGaps: '文书缺陷',
  codeCandidatesReview: '候选编码审核',
  review: '审核',
  reject: '驳回',
  modify: '修改',
  reasonRequired: '审核意见（必填）...',
  submitDecision: '提交审核意见',
  submitting: '提交中...',
  documentationGaps: '文书缺陷提示',
  suggestion: '建议',
  reviewerNotes: '审核备注',
  notesPlaceholder: '添加审核备注...',

  // Workbench
  codingWorkbench: '编码工作台',
  medicalRecord: '病历文书',
  evidence: '临床证据',
  candidateCodes: '候选编码',
  report: '审核报告',
  runCodingReview: '执行编码审核',
  analyzing: '分析中...',
  humanReview: '人工复核',
  exportData: '导出',
  noEncounterLoaded: '未加载病例。',
  goToHome: '返回首页开始审核。',
  noEvidence: '尚未提取临床证据。',
  runReviewHint: '执行编码审核以提取证据。',
  noCandidates: '尚未生成候选编码。',
  noReport: '尚未生成审核报告。',
  completeReviewHint: '完成审核后可查看编码审核报告。',
  humanReviewLabel: '人工审核',

  // Gold Cases
  goldCasesTitle: '金标准病例',
  goldCasesDesc: '专家审核的基准病例库，用于AI智能体性能评估',
  addGoldCase: '添加金标准病例',
  newGoldCase: '新建金标准病例',
  department: '科室',
  diagnosisGroup: '诊断分组',
  originalPrimaryDiagnosis: '原始主要诊断',
  goldPrimaryDiagnosis: '金标准主要诊断',
  originalMainProcedure: '原始主要手术',
  goldMainProcedure: '金标准主要手术',
  difficulty: '难度',
  easy: '简单',
  medium: '中等',
  hard: '困难',
  caseId: '病例编号',
  accuracy: '准确率',
  actions: '操作',
  noGoldCases: '暂无金标准病例。',

  // Evaluation
  evaluationTitle: 'AI智能体评估',
  evaluationDesc: '基于金标准病例的AI智能体编码性能评估指标',
  runEvaluation: '执行评估',
  running: '运行中...',
  primaryDiagAccuracy: '主要诊断准确率',
  mainProcAccuracy: '主要手术准确率',
  evidenceCompleteness: '证据完整度',
  hallucinationRate: '幻觉率',
  missingCodeRecall: '漏编码召回率',
  overallScore: '综合评分',
  target: '目标',
  perCaseResults: '分病例结果',
  noEvaluationData: '暂无评估数据。',
  runEvaluationHint: '基于金标准病例执行评估以查看AI智能体性能指标。',

  // Code Dictionaries
  codeDictionariesTitle: '编码字典',
  codeDictionariesDesc: '检索 ICD-10、ICD-9-CM-3、医保编码和医院本地扩展码',
  searchByDisease: '按疾病名称、手术名称或编码搜索...',
  code: '编码',
  name: '名称',
  chapter: '章节',
  score: '匹配度',
  valid: '有效性',
  builtInCodes: '内置编码：25 条 ICD-10 + 15 条 ICD-9-CM-3',
  searchForCodes: '在上方搜索医学编码',

  // Rule Libraries
  ruleLibrariesTitle: '规则库',
  ruleLibrariesDesc: '检索和应用主要诊断、手术操作、DRG/DIP 校验相关编码规则',
  retrieveRules: '检索规则',
  searching: '搜索中...',
  relevance: '相关度',
  examples: '示例',
  builtInRules: '内置规则：12 条规则，覆盖 7 个规则集',
  enterTopic: '输入编码主题搜索相关规则，如"骨质疏松伴病理性骨折 主诊断选择"',

  // API Clients
  apiClientsTitle: 'API 客户端',
  apiClientsDesc: '管理用于 iCoDer API 认证的 API 密钥',
  newApiKey: '新建 API 密钥',
  createApiKey: '创建 API 密钥',
  keyName: '密钥名称（如：生产环境、测试环境）',
  noApiKeys: '暂无 API 密钥。创建一个以开始使用。',

  // Team
  teamTitle: '团队',
  teamDesc: '管理团队成员及其对本项目的访问权限',
  inviteMember: '邀请成员',
  owner: '拥有者',
  coder: '编码员',
  deptHead: '科室负责人',

  // Billing
  billingTitle: '计费',
  billingDesc: '管理额度和查看计费历史',
  transactionHistory: '交易记录',
  creditPurchase: '额度充值',
  medicalCodingApi: '医学编码 API',

  // Usage
  usageTitle: '用量',
  usageDesc: '监控 API 使用情况和额度消耗',
  totalRequests: '总请求数',
  creditsUsed: '已消耗额度',
  avgResponseTime: '平均响应时间',
  recentActivity: '最近活动',
  requests: '请求',

  // Settings
  settingsTitle: '设置',
  account: '账户',
  fullName: '姓名',
  role: '角色',
  systemInformation: '系统信息',
  product: '产品',
  llmProvider: '大模型服务商',
  pipeline: '编排管线',
  environment: '运行环境',
  development: '开发环境',
  security: '安全',
  securityDesc: '所有操作均记录审计日志。患者数据已脱敏处理。采用 JWT 认证与基于角色的访问控制。生产部署时数据不出医院内网。',
  dataAndCompliance: '数据与合规',
  dataComplianceDesc: '内置编码字典：ICD-10（25条）、ICD-9-CM-3（15条）。规则库：12条规则覆盖7个规则集。支持本地私有化部署。审计日志保留365天。',

  // Developer Quickstart
  developerQuickstartTitle: '开发者快速入门',
  developerQuickstartDesc: '发起您的第一个 API 请求。获取 API 密钥，查看示例代码，几分钟内完成集成。',
  step1Title: '1. 获取 API 密钥',
  step1Desc: '您的 API 密钥用于对 iCoDer API 进行身份认证。',
  step2Title: '2. 发起请求',
  step2Desc: '向编码接口发送临床文本。',
  step3Title: '3. 构建应用',
  step3Desc: '查阅文档、SDK 和工具，将 iCoDer 集成到您的业务流程中。',
  generateNewKey: '生成新密钥',
  authenticationGuide: '认证指南',
  apiReferenceLink: 'API 参考文档',
  javascriptSdkLink: 'JavaScript SDK',
  postmanCollection: 'Postman 集合',
  integrationGuide: '集成指南',
  ehrCompatibility: 'HIS/EMR 兼容性矩阵',

  // Speech To Text
  speechToTextTitle: '语音转录',
  speechToTextDesc: '将医学语音和口述转换为结构化、可检索的文本，支持实时语音识别。',
  record: '录音',
  audioInput: '语音输入 / 文本输入',
  transcribedText: '转录文本将在此显示',

  // Text Generation
  textGenerationTitle: '文书生成',
  textGenerationDesc: '从结构化数据或提示词生成临床文书（出院小结、病程记录、转诊单等）。',
  generate: '生成',
  generatedText: '生成的文本将在此显示',
  dischargeSummary: '出院小结',
  progressNote: '病程记录',
  referralLetter: '转诊单',

  // Embedded Assistant
  embeddedAssistantTitle: '嵌入助手',
  embeddedAssistantDesc: '将智能临床 AI 助手直接嵌入您的 HIS/EMR 或临床工作流应用。助手可实时监听、转录并建议编码。',
  embedCode: '嵌入代码',
  configuration: '配置',
  mode: '模式',
  ambient: '环境监听（后台持续监听）',
  onDemand: '按需使用（按键说话）',
  hybrid: '混合模式',
  specialty: '专科',
  cardiology: '心血管内科',
  orthopedics: '骨科',
  generalPractice: '全科',
  neurology: '神经内科',
  oncology: '肿瘤科',
  autoSuggest: '自动推荐编码',
  resources: '资源',
  jsSdkReference: 'JavaScript SDK 参考',
  ehrMatrix: 'HIS/EMR 兼容性矩阵',
  copy: '复制',
  copied: '已复制',

  // ── Product Hub Homepage tabs ──
  productHubTranscribe: '语音转录',
  productHubTranscribeDesc: '实时转录临床对话，支持中英混合语音指令，可用于环境抄录和临床听写',
  productHubTranscribeCta: '试用语音转录',
  productHubTranscribeSecondary: '开始录音',
  productHubTranscribeBuild: 'SDK集成',
  productHubDocument: '文书生成',
  productHubDocumentDesc: '将转录文本或结构化事实转化为出院小结、病程记录、转诊信等临床文书',
  productHubDocumentCta: '试用文书生成',
  productHubDocumentSecondary: '进入文书生成',
  productHubDocumentBuild: 'SDK集成',
  productHubChat: 'AI智能体',
  productHubChatDesc: '使用预置Agent模板或自定义智能体，执行编码审核、CDI分析、DRG风控等任务',
  productHubChatCta: '试用AI智能体',
  productHubChatSecondary: '进入智能体',
  productHubChatBuild: 'SDK集成',
  productHubCode: '智能编码',
  productHubCodeDesc: '将非结构化临床文本转化为ICD-10-CN/ICD-9-CM-3编码，支持置信度校准和证据溯源',
  productHubCodeCta: '试用智能编码',
  productHubCodeSecondary: '进入医学编码',
  productHubCodeBuild: 'SDK集成',
  productHubNew: 'NEW',
  productHubDevQuickstart: '开发者快速入门',
  // ── Homepage common ──
  apiRequests: 'API 请求数',
  avgResponseTimeMs: '平均响应时间',
  milliseconds: '毫秒',
  recentEncounters: '最近病历',
  recentReviews: '最近审核',
  noEncounters: '暂无病历',
  noReviews: '暂无审核',
  completed: '已完成',
  reviewing: '审核中',
  unknown: '待处理',
  inReview: '审核中',
  // ── AI Studio Overview ──
  overviewTitle: 'AI Studio 总览',
  overviewSubtitle: '直接在 iCoDer 控制台中测试和配置各项功能',
  overviewExplore: '探索',
  overviewExploreDesc: '构建AI智能体，生成实时转录文本、临床文书等内容',
  overviewInspect: '检查',
  overviewInspectDesc: '使用事件查看器调试并监控实时额度消耗',
  overviewConfigure: '配置',
  overviewConfigureDesc: '根据需求微调设置，并将代码直接复制到应用中',
  overviewExploreCapabilities: '探索各项能力...',
  overviewReadyToCode: '准备好开始编写代码并发起您的第一个请求了吗？',
  overviewDevQuickstart: '开发者快速入门',
  overviewExploreBtn: '探索',
  overviewDocsBtn: '文档',
  overviewAgentsDesc: '通过添加专家、系统提示和上下文来定制AI智能体',
  overviewSttDesc: '流式传输实时音频，配置自定义命令并生成转录文本',
  overviewTextGenDesc: '将转录文本转化为结构化临床记录，根据需求定制',
  overviewEmbeddedDesc: '配置并测试嵌入式环境抄录助手的各项设置',
  overviewFactExtDesc: '从医疗转录文本和记录中提取结构化临床事实',
  overviewMedCodeDesc: '将非结构化临床文本转化为结构化医疗编码',
  // ── Developer Quickstart ──
  devQsTitle: '开发者快速入门',
  devQsSubtitle: '几分钟内完成 iCoDer API 的首次调用',
  devQsApiDocs: 'API 文档',
  devQsAiToolsTab: 'AI 编码工具',
  devQsJsSdkTab: 'JavaScript SDK',
  devQsDotNetTab: '.NET SDK',
  devQsAiToolsDesc: '为您的 AI 编码助手提供构建 iCoDer 应用所需的上下文。选择用例，复制提示词和凭据到您的应用中。',
  devQsStep1Title: '选择用例',
  devQsStep2Title: '向 AI 编码助手发送提示词',
  devQsStep3Title: '将凭据复制到应用中',
  devQsStep2Hint: '让您的 AI 助手在 iCoDer API 上构建此应用。以下是可以使用的提示词：',
  devQsStep3Hint: '您的 AI 助手会要求您将凭据添加到应用中。请复制以下凭据并安全存储。',
  devQsPromptLabel: '提示词',
  devQsOpenIn: '在以下工具中打开',
  devQsManageClients: '管理 API 客户端',
  devQsCopyEnv: '复制为 .env 文件',
  devQsGenerateCreds: '生成凭据',
  devQsGenerating: '生成中...',
  devQsViewCreds: '查看凭据',
  devQsCopyCreds: '复制凭据',
  devQsInstallNpm: '使用 npm 安装：',
  devQsInstallDotnet: '使用 .NET CLI 安装：',
  devQsJsCodeHint: '使用凭据创建 SDK 客户端：',
  devQsDotnetCodeHint: '使用凭据创建 SDK 客户端：',
  devQsReadyTitle: '准备开始构建！',
  devQsWalkthrough1: '使用 /transcribe API 构建听写应用',
  devQsWalkthrough2: '构建环境抄录应用',
  devQsWalkthrough3: '从自由文本预测结构化医疗编码',
  devQsWalkthrough4: '开始使用 iCoDer AI智能体框架',
  devQsDefaultClient: '默认客户端',
  defaultLabel: '(默认)',
  devQsCredsFlow: '您需要这些凭据来使用 iCoDer OAuth 2.0 客户端凭据流进行认证：',
  devQsCredsFlowDotnet: '您需要这些凭据来使用 iCoDer OAuth 2.0 客户端凭据流进行认证：',
  devQsApiPlaygroundDesc: '直接在浏览器中测试 API 端点。选择端点，填写请求体，查看响应结果。',
  devQsApiEndpoint: 'API 端点',
  devQsRequestBody: '请求体',
  devQsNoRequestBody: 'GET 请求 — 无需请求体',
  devQsSending: '发送中...',
  devQsSendRequest: '发送请求',
  devQsResponse: '响应',
  // ── Use cases ──
  useCaseDictation: '构建听写应用',
  useCaseScribe: '构建环境抄录助手',
  useCaseCoding: '构建医学编码应用',
  useCaseChat: '构建临床对话助手',
  // ── Misc
  yes: '是',
  no: '否',
  none: '无',
  na: '不适用',
  addContext: '添加上下文',
  addCustomExpert: '添加自定义专家',
  addExpert: '添加专家',
  addFile: '添加文件',
  addJson: '添加JSON',
  addText: '添加文本',
  agentDetailName: '智能体详情',
  agentNamePlaceholder: '例如：骨科编码审核助手',
  agentNotFound: '未找到智能体',
  allCategories: '全部分类',
  and: '和',
  askTheAgentDesc: '输入临床问题，AI智能体将基于专家知识回答',
  askTheAgentPlaceholder: '输入问题...（回车发送）',
  askTheAgentTitle: '与AI智能体对话',
  backToAgentList: '返回智能体列表',
  beforeUsing: '使用前请阅读',
  bringYourOwnMcpExpert: '接入自有MCP专家',
  browseExpertLibrary: '浏览专家库',
  byoMcpDesc: '通过MCP协议接入自有专家服务',
  byoMcpExpert: '自有MCP专家',
  clickToDefinePrompt: '点击定义系统提示词',
  confirmDelete: '确认删除',
  confirmDeleteExpert: '确定删除专家"{name}"？',
  createExpert: '创建专家',
  createFailed: '创建失败',
  createFirstExpert: '创建第一个专家',
  creatingExpert: '创建中...',
  customMcpExpert: '自定义MCP专家',
  deleteConfirmDesc: '此操作不可撤销',
  deleteConfirmMessage: '确定删除智能体 {name}？',
  deleteConfirmTitle: '删除智能体',
  deleteFailed: '删除失败',
  discoverTools: '发现工具',
  discoverToolsFailed: '发现工具失败',
  discoveredToolsCount: '已发现 {count} 个工具',
  discoveringTools: '发现中...',
  enterQueryOrClinicalText: '输入查询或临床文本...',
  enterUsernamePassword: '请输入用户名和密码',
  errorPrefix: '错误',
  examplePrefix: '示例',
  expertLibrary: '专家库',
  expertLibraryDesc: '浏览和管理AI专家',
  expertName: '专家名称',
  experts: '专家',
  externalTicketSystem: '外部工单系统',
  findAgent: '查找智能体',
  jsonData: 'JSON数据',
  loadExpertsFailed: '加载专家失败',
  loginFailed: '登录失败',
  mcpCount: '{count} 个MCP服务器',
  mcpServerUrl: 'MCP服务器URL',
  mcpServerUrlPlaceholder: 'https://your-mcp-server.com',
  mcpServers: 'MCP服务器',
  myExperts: '我的专家',
  myMcpExpert: '我的MCP专家',
  noExpertsBound: '未绑定专家',
  noExpertsFound: '未找到专家',
  openTicketSystem: '打开工单系统',
  prebuilt: '预置',
  prebuiltTag: '预置',
  privacyPolicy: '隐私政策',
  readMore: '阅读更多',
  run: '运行',
  runExpert: '运行专家',
  savedAgent: '已保存',
  savingAgent: '保存中...',
  searchExperts: '搜索专家',
  sessionContextRestored: '会话上下文已恢复',
  showLess: '收起',
  suggestPrompt: '建议提示',
  systemPromptPlaceholder: '定义AI智能体的角色、专业领域和行为规范...',
  termsOfService: '服务条款',
  thinking: '思考中...',
  ticketsDesc: '管理您的支持工单',
  ticketsManagedElsewhere: '工单通过帮助台系统进行管理',
  ticketsTitle: '工单系统',
  usageLabel: '用法',
  viewDetails: '查看详情',
  viewDocumentation: '查看文档',
  welcomeBack: '欢迎回来，请登录您的账户',
  whatCanYouDo: '你能做什么？',
  // Embedded Assistant
  embedInitializing: '初始化中...',
  embedPreview: '预览',
  embedPreviewSession: '预览会话',
  embedDesktopView: '桌面视图',
  embedMobileView: '移动视图',
  embedRestartSession: '重新开始会话',
  embedOnRefresh: '刷新后生效',
  embedCopyEmbedCode: '复制嵌入代码',
  embedOpenInNewWindow: '在新窗口打开',
  embedRecording: '录音中...',
  embedWriteSomething: '输入内容',
  embedStartRecordingHint: '开始录音以获取内容。录音过程中会自动捕获事实。',
  embedTranscriptionPlaceholder: '转录文本将在此显示...',
  embedAiChat: 'AI对话',
  embedAiChatDesc: '基于当前转录内容，提问临床相关问题。',
  embedAskQuestion: '输入问题...',
  embedStopRecording: '停止录音',
  embedVoiceInput: '语音输入',
  embedStop: '停止',
  embedRecord: '录音',
  embedSettingsLabel: '设置',
  embedCodeLabel: '代码',
  embedRestartSessionHint: '重新开始会话以在预览中查看更改',
  embedSessionDefaults: '会话默认设置',
  embedPrimaryLanguage: '主要对话语言',
  embedDefaultMode: '默认模式',
  embedModeInPerson: '诊室内',
  embedModeVirtual: '远程',
  embedFeatures: '功能',
  embedFeatureAllowVirtual: '允许远程模式',
  embedFeatureShowTitle: '显示交互标题',
  embedFeatureEnableAiChat: '启用AI对话',
  embedFeatureShowFeedback: '显示文档反馈',
  embedFeatureEnableEditor: '启用模板编辑器',
  embedFeatureShowNav: '显示导航栏',
  embedFeatureShowSync: '显示同步文档操作',
  embedAppearance: '外观',
  embedPrimaryColor: '主题颜色',
  embedLocaleSection: '语言区域',
  embedInterfaceLanguage: '界面语言',
  embedDictationLanguage: '听写语言',
  embedNewToAssistant: '初次使用嵌入助手？',
  embedTakeTour: '观看引导',
  embedDismiss: '关闭',
  embedSkipTour: '跳过引导',
  embedPrevStep: '上一步',
  embedNextStep: '下一步',
  embedGetStarted: '开始使用',
  // Orchestration Pipeline
  orchestrationTitle: '编码审核流水线',
  orchestrationDesc: '运行完整的9步编码审核流水线，查看多专家协作的诊断编码、手术编码、DRG分析和合规审查结果',
  orchestrationSelectEncounter: '选择就诊记录或输入临床文本',
  orchestrationExistingEncounter: '已有就诊',
  orchestrationNewClinicalText: '新建临床文本',
  orchestrationEncounterPlaceholder: '搜索就诊记录...',
  orchestrationNoEncounterFound: '未找到就诊记录',
  orchestrationEnterClinicalText: '在此粘贴临床文本（病历、出院小结、手术记录等）...',
  orchestrationPipelineSteps: '流水线步骤',
  orchestrationProgress: '进度',
  orchestrationStatusIdle: '等待开始',
  orchestrationStatusRunning: '运行中...',
  orchestrationStatusCompleted: '已完成',
  orchestrationStatusFailed: '失败',
  orchestrationRunPipeline: '运行编码审核流水线',
  orchestrationDiagnosisCandidates: '诊断编码候选',
  orchestrationProcedureCandidates: '手术编码候选',
  orchestrationDrgImpact: 'DRG 影响分析',
  orchestrationDocumentationGaps: '文档缺口',
  orchestrationHumanChecklist: '人工审核清单',
  orchestrationHumanReview: '人工复核',
  orchestrationApprove: '批准',
  orchestrationReject: '驳回',
  orchestrationRationale: '复核理由',
  orchestrationRationalePlaceholder: '请描述批准或驳回的原因...',
  orchestrationAuditTrail: '审计跟踪',
  orchestrationNoAuditEvents: '暂无审计事件',
  orchestrationViewReport: '查看完整报告',
  orchestrationReportMarkdown: 'Markdown 报告',
  orchestrationReportHtml: 'HTML 报告',
  orchestrationEventLog: '事件日志',

  // Organization
  orgSwitch: '切换组织',
  orgNoOrg: '无组织',
  orgSelectOrg: '选择组织',
  orgCreate: '创建组织',
  orgManage: '组织管理',
  orgName: '组织名称',
  orgPlan: '套餐',
  orgMembers: '成员',
  orgInvite: '邀请成员',
  orgInviteEmail: '邮箱地址',
  orgInviteRole: '角色',
  orgRemoveMember: '移除成员',
  orgRoleOwner: '拥有者',
  orgRoleAdmin: '管理员',
  orgRoleMember: '成员',
  orgRoleViewer: '观察者',
};

const enUS: LocaleDict = {
  // Common
  appName: 'iCoDer Console',
  appTagline: 'Auditable Clinical AI',
  save: 'Save',
  cancel: 'Cancel',
  confirm: 'Confirm',
  delete: 'Delete',
  search: 'Search',
  loading: 'Loading...',
  noData: 'No data',
  back: 'Back',
  dismiss: 'Dismiss',

  // Header
  notifications: 'Notifications',
  toggleSidebar: 'Toggle Sidebar',

  // Sidebar
  home: 'Home',
  developerQuickstart: 'Developer quickstart',
  developerDocs: 'Developer Docs',
  creating: 'Creating...',
  aiStudio: 'AI Studio',
  overview: 'Overview',
  agents: 'Agents',
  speechToText: 'Speech To Text',
  textGeneration: 'Text Generation',
  embeddedAssistant: 'Embedded Assistant',
  factExtraction: 'Fact Extraction',
  medicalCoding: 'Medical Coding',
  manage: 'Manage',
  apiClients: 'API Clients',
  apiClientsManage: 'Manage API Clients',
  team: 'Team',
  billing: 'Billing',
  usage: 'Usage',
  settings: 'Settings',
  data: 'Data',
  codeDictionaries: 'Code Dictionaries',
  ruleLibraries: 'Rule Libraries',
  goldCases: 'Gold Cases',
  evaluation: 'Evaluation',
  support: 'Support',
  getHelp: 'Get Help',
  ticketsPortal: 'Tickets Portal',

  // Login
  login: 'Login',
  loginTitle: 'Login to iCoDer',
  username: 'Username',
  password: 'Password',
  loginButton: 'Login',
  demoHint: 'Demo: admin / admin123',
  loggingIn: 'Logging in...',

  // Home
  getStartedBanner: 'Get started with iCoDer Console',
  getStartedDesc: 'Test capabilities right away in AI Studio, or follow the developer quickstart to make your first request',
  aiStudioBtn: 'AI Studio',
  developerQuickstartBtn: 'Developer quickstart',
  overviewSection: 'Overview',
  availableCredits: 'Available credits',
  addCredits: 'Add credits',
  totalCreditsConsumed: 'Total credits consumed',
  viewUsage: 'View usage',
  creditsConsumed: 'Credits consumed',
  comparePeriod: 'Compare period',
  last30Days: 'Last 30 days',
  allApiClients: 'All API clients',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  documentation: 'Documentation',
  authentication: 'Authentication',
  guides: 'Guides',
  apiReference: 'API Reference',
  sdksAndTools: 'SDKs and Tools',
  javascriptSdk: 'JavaScript SDK',
  dotnetSdk: '.NET SDK',
  postman: 'Postman',
  aiCodingTools: 'AI coding tools',
  needHelp: 'Need Help?',
  chatWithUs: 'Chat with us',
  openTicket: 'Open a ticket',
  last7DaysLabel: 'Last 7 days',
  last30DaysLabel: 'Last 30 days',
  last90DaysLabel: 'Last 90 days',

  // AI Studio Overview
  aiStudioTitle: 'AI Studio',
  aiStudioDesc: 'Test and configure healthcare AI agents. Each agent processes clinical data and returns structured, auditable results.',
  openBtn: 'Open',

  // Agents
  agentsTitle: 'Agents',
  agentsDesc: 'Build healthcare agents to take action across your systems',
  newAgent: 'New Agent',
  all: 'All',
  myAgents: 'My agents',
  prebuiltAgents: 'Pre-built',
  createdBy: 'Created by',
  searchAgents: 'Search agents...',
  noAgents: 'No agents found',
  createAgent: 'Create an agent',
  creatingAgent: 'Creating...',
  noMyAgents: 'No agents yet',
  noMyAgentsHint: 'Create your first agent or start from a prebuilt template',
  browsePrebuilt: 'Browse prebuilt',
  noMatchingAgents: 'No matching agents',
  noMatchingAgentsHint: 'Try adjusting your search or filters',
  clearFilter: 'Clear filters',
  allCreators: 'All creators',
  category: 'Category',
  description: 'Description',
  optional: '(optional)',
  aiGenerate: 'AI Generate',
  generating: 'Generating...',
  bindExperts: 'Bind Experts',
  selectedCount: '{count} selected',
  noMatchingExperts: 'No matching experts',
  cloneFromExisting: 'Clone from existing',
  cloneAction: 'Clone',
  cloneHint: 'Select an agent as a template. Its name, description, and system prompt will be prefilled.',
  useTemplate: 'Use a template',
  useTemplateHint: 'Select a template to prefill name, description, and system prompt',
  searchTemplates: 'Search templates',
  loadingTemplates: 'Loading templates...',
  noTemplatesAvailable: 'No templates available',
  agentDescPlaceholder: 'Briefly describe the agent\'s purpose and functionality',
  newAgentModalDesc: 'Configure the agent\'s name, behavior, and associated experts',
  confirmDeleteAgent: 'Delete "{name}"?',
  deleteIrreversible: 'This action cannot be undone',
  confirmDeleteBtn: 'Confirm delete',

  // Medical Coding
  medicalCodingTitle: 'Medical Coding',
  medicalCodingDesc: 'Convert unstructured clinical text (e.g., encounter notes, discharge summaries, transcripts) into structured medical codes.',
  predictCodes: 'Predict codes',
  config: 'Config',
  codingSystems: 'Coding systems',
  apiClient: 'API Client',
  inputLabel: 'Input',
  outputLabel: 'Output',
  useSample: 'Use sample',
  clearInput: 'Clear input',
  copyInput: 'Copy input',
  enterClinicalText: 'Enter clinical text...',
  predictedCodesWillShow: 'Predicted codes will show here',
  eventInspector: 'Event Inspector',
  creditsConsumedLabel: 'Credits consumed',
  viewFullReport: 'View full report',
  systemPrompt: 'System Prompt',
  codingSystem: 'Coding System',
  confidenceThreshold: 'Confidence Threshold',
  outputLanguage: 'Output Language',
  model: 'Model',
  includeEvidence: 'Include evidence in output',
  autoValidate: 'Auto-validate against rules',
  primaryDiagnosis: 'Primary Diagnosis',
  mainProcedure: 'Main Procedure',
  allCandidates: 'All Candidates',
  confidence: 'Confidence',
  getStartedWith: 'Get started with',
  resetLiveCost: 'Reset live cost',

  // Sample cases
  hospitalMedicalRecord: 'Hospital medical record',
  hospitalMedicalRecordDesc: 'Inpatient admission with history, exam, imaging, and discharge summary',
  gpTranscript: 'GP transcript',
  gpTranscriptDesc: 'Primary care visit note with symptoms and assessment',
  orthopedicReferral: 'Orthopedic referral letter',
  orthopedicReferralDesc: 'Specialist referral with imaging findings and suspected diagnosis',
  guidedDemo: 'Guided demo',
  guidedDemoDesc: 'Interactive walkthrough of the Medical Coding agent',

  // Sample document types
  admissionRecord: 'Admission record',
  operationRecord: 'Operation record',
  outpatientRecord: 'Outpatient record',
  consultationRecord: 'Consultation record',

  // Medical Coding — Corti-aligned extras
  samples: 'Samples',
  openGuide: 'Open guided demo',
  dismissGuide: 'Dismiss guided demo',
  selectCodingSystem: 'Select coding systems',
  selectCodingSystemDesc: 'Pick the coding systems to use for this prediction (shared with right Settings)',
  guideStepSample: 'Pick a sample document',
  guideStepSystem: 'Pick coding systems',
  guideStepSampleDesc: 'Choose a sample document — the wizard will fill the input and trigger prediction',
  startByAddingText: 'Start by adding text input',
  next: 'Next',
  done: 'Done',
  add: 'Add',
  ready: 'Ready',
  expand: 'Expand',
  include: 'Include',
  exclude: 'Exclude',
  filterCodes: 'Filter codes',
  addCodes: 'Add codes',
  noSystemsSelected: 'No systems selected',
  processingFailed: 'Processing failed',
  sampleLoaded: 'Sample loaded',
  startingPrediction: 'Starting prediction...',
  addIncludeCode: 'Add include code',
  addExcludeCode: 'Add exclude code',
  enterCodePlaceholder: 'Enter code (e.g. J18.1)',
  tableCode: 'Code',
  tableDescription: 'Description',
  tableConfidence: 'Conf.',
  medicalCodingBreadcrumb: 'Medical coding',
  tabCode: 'Code',
  failedPrefix: 'Failed',
  completedPrefix: 'Completed —',
  preGuardViolations: 'Pre-guard: {count} violations',
  contractVerified: 'Contract: {status}',
  safety: 'Safety',
  schema: 'Schema',
  resetSettings: 'Reset settings',

  // Fact Extraction
  factExtractionTitle: 'Fact Extraction',
  factExtractionDesc: 'Extract structured clinical facts (diagnoses, procedures, medications, anatomy) from unstructured medical text.',
  extractFacts: 'Extract facts',
  generatedFactsWillShow: 'Generated facts will show here',

  // Case Review
  caseReview: 'Case Review',
  reviewId: 'Review ID',
  codesReviewed: 'codes reviewed',
  pending: 'pending',
  completeReview: 'Complete Review',
  reviewCompleted: 'Review Completed',
  validationSummary: 'Validation Summary',
  supported: 'Supported',
  needsReview: 'Needs Review',
  unsupported: 'Unsupported',
  evidenceBinding: 'Evidence Binding',
  docGaps: 'Doc Gaps',
  codeCandidatesReview: 'Code Candidates Review',
  review: 'Review',
  reject: 'Reject',
  modify: 'Modify',
  reasonRequired: 'Reason for this decision (required)...',
  submitDecision: 'Submit Decision',
  submitting: 'Submitting...',
  documentationGaps: 'Documentation Gaps',
  suggestion: 'Suggestion',
  reviewerNotes: 'Reviewer Notes',
  notesPlaceholder: 'Add any notes about this review...',

  // Workbench
  codingWorkbench: 'Coding Workbench',
  medicalRecord: 'Medical Record',
  evidence: 'Evidence',
  candidateCodes: 'Candidate Codes',
  report: 'Report',
  runCodingReview: 'Run Coding Review',
  analyzing: 'Analyzing...',
  humanReview: 'Human Review',
  exportData: 'Export',
  noEncounterLoaded: 'No encounter loaded.',
  goToHome: 'Go to Home to start a review.',
  noEvidence: 'No evidence extracted yet.',
  runReviewHint: 'Run a review to extract clinical evidence.',
  noCandidates: 'No candidate codes generated yet.',
  noReport: 'No report generated yet.',
  completeReviewHint: 'Complete a review to see the Coding Review Report.',
  humanReviewLabel: 'Human review',

  // Gold Cases
  goldCasesTitle: 'Gold Cases',
  goldCasesDesc: 'Expert-reviewed benchmark cases for agent evaluation',
  addGoldCase: 'Add Gold Case',
  newGoldCase: 'New Gold Case',
  department: 'Department',
  diagnosisGroup: 'Diagnosis Group',
  originalPrimaryDiagnosis: 'Original Primary Diagnosis',
  goldPrimaryDiagnosis: 'Gold Primary Diagnosis',
  originalMainProcedure: 'Original Main Procedure',
  goldMainProcedure: 'Gold Main Procedure',
  difficulty: 'Difficulty',
  easy: 'Easy',
  medium: 'Medium',
  hard: 'Hard',
  caseId: 'Case ID',
  accuracy: 'Accuracy',
  actions: 'Actions',
  noGoldCases: 'No gold cases yet.',

  // Evaluation
  evaluationTitle: 'Evaluation',
  evaluationDesc: 'Agent performance metrics against gold cases',
  runEvaluation: 'Run Evaluation',
  running: 'Running...',
  primaryDiagAccuracy: 'Primary Diag Accuracy',
  mainProcAccuracy: 'Main Procedure Accuracy',
  evidenceCompleteness: 'Evidence Completeness',
  hallucinationRate: 'Hallucination Rate',
  missingCodeRecall: 'Missing Code Recall',
  overallScore: 'Overall Score',
  target: 'Target',
  perCaseResults: 'Per-Case Results',
  noEvaluationData: 'No evaluation data yet.',
  runEvaluationHint: 'Run an evaluation against gold cases to see agent performance metrics.',

  // Code Dictionaries
  codeDictionariesTitle: 'Code Dictionaries',
  codeDictionariesDesc: 'Search and explore ICD-10, ICD-9-CM-3, insurance codes, and local extension codes',
  searchByDisease: 'Search by disease name, procedure name, or code...',
  code: 'Code',
  name: 'Name',
  chapter: 'Chapter',
  score: 'Score',
  valid: 'Valid',
  builtInCodes: 'Built-in codes: 25 ICD-10 + 15 ICD-9-CM-3',
  searchForCodes: 'Search for medical codes above',

  // Rule Libraries
  ruleLibrariesTitle: 'Rule Libraries',
  ruleLibrariesDesc: 'Retrieve and apply coding rules for main diagnosis, procedures, DRG/DIP validation',
  retrieveRules: 'Retrieve Rules',
  searching: 'Searching...',
  relevance: 'Relevance',
  examples: 'Examples',
  builtInRules: 'Built-in: 12 rules across 7 rule sets',
  enterTopic: 'Enter a topic to retrieve relevant coding rules',

  // API Clients
  apiClientsTitle: 'API Clients',
  apiClientsDesc: 'Manage API keys for authenticating requests to the iCoDer API.',
  newApiKey: 'New API Key',
  createApiKey: 'Create API Key',
  keyName: 'Key name (e.g., Production, Staging)',
  noApiKeys: 'No API keys yet. Create one to get started.',

  // Team
  teamTitle: 'Team',
  teamDesc: 'Manage team members and their access to this project.',
  inviteMember: 'Invite Member',
  owner: 'Owner',
  coder: 'Coder',
  deptHead: 'Department Head',

  // Billing
  billingTitle: 'Billing',
  billingDesc: 'Manage credits and view your billing history.',
  transactionHistory: 'Transaction History',
  creditPurchase: 'Credit purchase',
  medicalCodingApi: 'Medical Coding API',

  // Usage
  usageTitle: 'Usage',
  usageDesc: 'Monitor your API usage and credit consumption.',
  totalRequests: 'Total Requests',
  creditsUsed: 'Credits Used',
  avgResponseTime: 'Avg Response Time',
  recentActivity: 'Recent Activity',
  requests: 'requests',

  // Settings
  settingsTitle: 'Settings',
  account: 'Account',
  fullName: 'Full Name',
  role: 'Role',
  systemInformation: 'System Information',
  product: 'Product',
  llmProvider: 'LLM Provider',
  pipeline: 'Pipeline',
  environment: 'Environment',
  development: 'Development',
  security: 'Security',
  securityDesc: 'All operations are audited. Patient data is anonymized. JWT authentication with role-based access control. Data never leaves the hospital network in production deployments.',
  dataAndCompliance: 'Data & Compliance',
  dataComplianceDesc: 'Built-in code dictionaries: ICD-10 (25 codes), ICD-9-CM-3 (15 codes). Rule libraries: 12 rules across 7 rule sets. Supports local private deployment. Audit log retention: 365 days.',

  // Developer Quickstart
  developerQuickstartTitle: 'Developer quickstart',
  developerQuickstartDesc: 'Make your first API request. Get your API key, see example code, and integrate in minutes.',
  step1Title: '1. Get your API key',
  step1Desc: 'Your API key authenticates requests to the iCoDer API.',
  step2Title: '2. Make a request',
  step2Desc: 'Send clinical text to the coding endpoint.',
  step3Title: '3. Build your app',
  step3Desc: 'Explore docs, SDKs, and tools to integrate iCoDer into your workflow.',
  generateNewKey: 'Generate new key',
  authenticationGuide: 'Authentication guide',
  apiReferenceLink: 'API Reference',
  javascriptSdkLink: 'JavaScript SDK',
  postmanCollection: 'Postman collection',
  integrationGuide: 'Integration guide',
  ehrCompatibility: 'EHR compatibility matrix',

  // Speech To Text
  speechToTextTitle: '语音转录',
  speechToTextDesc: 'Convert medical speech and dictation into structured, searchable text using real-time speech recognition.',
  record: 'Record',
  audioInput: 'Audio input / Text input',
  transcribedText: 'Transcribed text will appear here',

  // Text Generation
  textGenerationTitle: 'Text Generation',
  textGenerationDesc: 'Generate clinical documentation (discharge summaries, progress notes, referral letters) from structured data or prompts.',
  generate: 'Generate',
  generatedText: 'Generated text will appear here',
  dischargeSummary: 'Discharge summary',
  progressNote: 'Progress note',
  referralLetter: 'Referral letter',

  // Embedded Assistant
  embeddedAssistantTitle: 'Embedded Assistant',
  embeddedAssistantDesc: 'Embed an ambient clinical AI assistant directly into your EHR or clinical workflow application.',
  embedCode: 'Embed code',
  configuration: 'Configuration',
  mode: 'Mode',
  ambient: 'Ambient (background listening)',
  onDemand: 'On-demand (push-to-talk)',
  hybrid: 'Hybrid',
  specialty: 'Specialty',
  cardiology: 'Cardiology',
  orthopedics: 'Orthopedics',
  generalPractice: 'General Practice',
  neurology: 'Neurology',
  oncology: 'Oncology',
  autoSuggest: 'Auto-suggest codes',
  resources: 'Resources',
  jsSdkReference: 'JavaScript SDK reference',
  ehrMatrix: 'EHR compatibility matrix',
  copy: 'Copy',
  copied: 'Copied',

  // ── Product Hub Homepage tabs ──
  productHubTranscribe: 'Transcribe',
  productHubTranscribeDesc: 'Real-time clinical speech transcription with bilingual (ZH/EN) voice commands for ambient scribing and dictation',
  productHubTranscribeCta: 'Try Speech to Text',
  productHubTranscribeSecondary: 'Start recording',
  productHubTranscribeBuild: 'SDK Integration',
  productHubDocument: 'Document',
  productHubDocumentDesc: 'Generate discharge summaries, progress notes, referral letters and more from transcripts or structured facts',
  productHubDocumentCta: 'Try Text Generation',
  productHubDocumentSecondary: 'Document Studio',
  productHubDocumentBuild: 'SDK Integration',
  productHubChat: 'AI Agents',
  productHubChatDesc: 'Use pre-built Agent templates or custom agents for coding audit, CDI analysis, DRG risk assessment and more',
  productHubChatCta: 'Try AI Agents',
  productHubChatSecondary: 'Agent Studio',
  productHubChatBuild: 'SDK Integration',
  productHubCode: 'Medical Coding',
  productHubCodeDesc: 'Convert unstructured clinical text into ICD-10-CN / ICD-9-CM-3 codes with confidence calibration and evidence traceability',
  productHubCodeCta: 'Try Medical Coding',
  productHubCodeSecondary: 'Code Studio',
  productHubCodeBuild: 'SDK Integration',
  productHubNew: 'NEW',
  productHubDevQuickstart: 'Developer quickstart',
  // ── Homepage common ──
  apiRequests: 'API Requests',
  avgResponseTimeMs: 'Avg Response Time',
  milliseconds: 'milliseconds',
  recentEncounters: 'Recent encounters',
  recentReviews: 'Recent reviews',
  noEncounters: 'No encounters yet',
  noReviews: 'No reviews yet',
  completed: 'Completed',
  reviewing: 'Reviewing',
  unknown: 'Pending',
  inReview: 'In Review',
  // ── AI Studio Overview ──
  overviewTitle: 'AI Studio Overview',
  overviewSubtitle: 'Test and configure use cases directly from iCoDer Console',
  overviewExplore: 'Explore',
  overviewExploreDesc: 'Build agents, generate live transcripts, clinical documents and more',
  overviewInspect: 'Inspect',
  overviewInspectDesc: 'Debug with the events inspector and monitor live credit consumption',
  overviewConfigure: 'Configure',
  overviewConfigureDesc: 'Fine tune settings for your needs and copy code directly into your application',
  overviewExploreCapabilities: 'Explore capabilities...',
  overviewReadyToCode: 'Ready to dive into code and make your first request?',
  overviewDevQuickstart: 'Developer quickstart',
  overviewExploreBtn: 'Explore',
  overviewDocsBtn: 'Docs',
  overviewAgentsDesc: 'Customize agents by adding experts, system prompts and context',
  overviewSttDesc: 'Stream live audio, configure custom commands and generate transcriptions',
  overviewTextGenDesc: 'Turn transcriptions into structured clinical notes, customized for your needs',
  overviewEmbeddedDesc: 'Configure and test settings for an embedded ambient scribe experience',
  overviewFactExtDesc: 'Extract structured clinical facts from medical transcriptions and notes',
  overviewMedCodeDesc: 'Convert unstructured clinical text into structured medical codes',
  // ── Developer Quickstart ──
  devQsTitle: 'Developer quickstart',
  devQsSubtitle: 'Get started with the iCoDer API in minutes',
  devQsApiDocs: 'API docs',
  devQsAiToolsTab: 'Code with AI tools',
  devQsJsSdkTab: 'JavaScript SDK',
  devQsDotNetTab: '.NET SDK',
  devQsAiToolsDesc: 'Give your coding agent the context it needs to start building on iCoDer. Start by selecting your use case, then copy the prompt and credentials into your application.',
  devQsStep1Title: 'Select your use case',
  devQsStep2Title: 'Prompt your coding agent',
  devQsStep3Title: 'Copy credentials into your app',
  devQsStep2Hint: 'Ask your AI assistant to build this app on the iCoDer API. Here\'s a prompt you can use:',
  devQsStep3Hint: 'Your agent will ask you to add credentials into your app. Copy the credentials below, making sure to store them securely.',
  devQsPromptLabel: 'Prompt',
  devQsOpenIn: 'Open in',
  devQsManageClients: 'Manage API clients',
  devQsCopyEnv: 'Copy all as .env variables',
  devQsGenerateCreds: 'Generate credentials',
  devQsGenerating: 'Generating...',
  devQsViewCreds: 'View credentials',
  devQsCopyCreds: 'Copy credentials',
  devQsInstallNpm: 'Install using npm:',
  devQsInstallDotnet: 'Install using the .NET CLI:',
  devQsJsCodeHint: 'Create an SDK Client with your credentials:',
  devQsDotnetCodeHint: 'Create an SDK client with your credentials:',
  devQsReadyTitle: 'You\'re ready to build!',
  devQsWalkthrough1: 'Build a dictation app using the /transcribe API',
  devQsWalkthrough2: 'Build an ambient scribe application',
  devQsWalkthrough3: 'Predict structured medical codes from free-text input',
  devQsWalkthrough4: 'Get started with the iCoDer Agentic Framework',
  devQsDefaultClient: 'Default client',
  defaultLabel: '(default)',
  devQsCredsFlow: 'You\'ll need these credentials at hand to authenticate using iCoDer\'s OAuth 2.0 client credentials flow:',
  devQsCredsFlowDotnet: 'You\'ll need these credentials at hand to authenticate using iCoDer\'s OAuth 2.0 client credentials flow:',
  devQsApiPlaygroundDesc: 'Test API endpoints directly from the browser. Select an endpoint, provide the request body, and inspect the response.',
  devQsApiEndpoint: 'API Endpoint',
  devQsRequestBody: 'Request Body',
  devQsNoRequestBody: 'GET request — no request body',
  devQsSending: 'Sending...',
  devQsSendRequest: 'Send Request',
  devQsResponse: 'Response',
  // ── Use cases ──
  useCaseDictation: 'Build a dictation app',
  useCaseScribe: 'Build an ambient scribe',
  useCaseCoding: 'Build a medical coding app',
  useCaseChat: 'Build a clinical chat assistant',
  // ── Misc
  yes: 'Yes',
  no: 'No',
  none: 'None',
  na: 'N/A',
  addContext: 'Add context',
  addCustomExpert: 'Add custom expert',
  addExpert: 'Add expert',
  addFile: 'Add file',
  addJson: 'Add JSON',
  addText: 'Add text',
  agentDetailName: 'Agent Detail',
  agentNamePlaceholder: 'e.g. Orthopedic coding audit assistant',
  agentNotFound: 'Agent not found',
  allCategories: 'All categories',
  and: 'and',
  askTheAgentDesc: 'Ask clinical questions, AI agent answers based on expert knowledge',
  askTheAgentPlaceholder: 'Ask a question... (Enter to send)',
  askTheAgentTitle: 'Chat with AI Agent',
  backToAgentList: 'Back to agent list',
  beforeUsing: 'Before using, please read',
  bringYourOwnMcpExpert: 'Bring your own MCP expert',
  browseExpertLibrary: 'Browse expert library',
  byoMcpDesc: 'Connect your own expert services via MCP protocol',
  byoMcpExpert: 'BYO MCP expert',
  clickToDefinePrompt: 'Click to define system prompt',
  confirmDelete: 'Confirm delete',
  confirmDeleteExpert: 'Delete expert "{name}"?',
  createExpert: 'Create expert',
  createFailed: 'Create failed',
  createFirstExpert: 'Create first expert',
  creatingExpert: 'Creating...',
  customMcpExpert: 'Custom MCP expert',
  deleteConfirmDesc: 'This action cannot be undone',
  deleteConfirmMessage: 'Delete agent {name}?',
  deleteConfirmTitle: 'Delete agent',
  deleteFailed: 'Delete failed',
  discoverTools: 'Discover tools',
  discoverToolsFailed: 'Failed to discover tools',
  discoveredToolsCount: '{count} tools discovered',
  discoveringTools: 'Discovering...',
  enterQueryOrClinicalText: 'Enter query or clinical text...',
  enterUsernamePassword: 'Please enter username and password',
  errorPrefix: 'Error',
  examplePrefix: 'Example',
  expertLibrary: 'Expert Library',
  expertLibraryDesc: 'Browse and manage AI experts',
  expertName: 'Expert name',
  experts: 'Experts',
  externalTicketSystem: 'External ticket system',
  findAgent: 'Find agent',
  jsonData: 'JSON data',
  loadExpertsFailed: 'Failed to load experts',
  loginFailed: 'Login failed',
  mcpCount: '{count} MCP servers',
  mcpServerUrl: 'MCP server URL',
  mcpServerUrlPlaceholder: 'https://your-mcp-server.com',
  mcpServers: 'MCP servers',
  myExperts: 'My experts',
  myMcpExpert: 'My MCP expert',
  noExpertsBound: 'No experts bound',
  noExpertsFound: 'No experts found',
  openTicketSystem: 'Open ticket system',
  prebuilt: 'Prebuilt',
  prebuiltTag: 'Prebuilt',
  privacyPolicy: 'Privacy policy',
  readMore: 'Read more',
  run: 'Run',
  runExpert: 'Run expert',
  savedAgent: 'Saved',
  savingAgent: 'Saving...',
  searchExperts: 'Search experts',
  sessionContextRestored: 'Session context restored',
  showLess: 'Show less',
  suggestPrompt: 'Suggest prompt',
  systemPromptPlaceholder: 'Define the agent\'s role, specialty domain, and behavior rules...',
  termsOfService: 'Terms of service',
  thinking: 'Thinking...',
  ticketsDesc: 'Manage your support tickets',
  ticketsManagedElsewhere: 'Tickets managed through help desk',
  ticketsTitle: 'Ticket System',
  usageLabel: 'Usage',
  viewDetails: 'View details',
  viewDocumentation: 'View documentation',
  welcomeBack: 'Welcome back, please log in to your account',
  whatCanYouDo: 'What can you do?',
  // Embedded Assistant
  embedInitializing: 'Initializing...',
  embedPreview: 'preview',
  embedPreviewSession: 'Preview session',
  embedDesktopView: 'Desktop view',
  embedMobileView: 'Mobile view',
  embedRestartSession: 'Restart session',
  embedOnRefresh: 'on refresh',
  embedCopyEmbedCode: 'Copy embed code',
  embedOpenInNewWindow: 'Open in new window',
  embedRecording: 'Recording...',
  embedWriteSomething: 'Write something',
  embedStartRecordingHint: 'Start recording to begin. Facts automatically captured while recording.',
  embedTranscriptionPlaceholder: 'Transcription will appear here...',
  embedAiChat: 'AI Chat',
  embedAiChatDesc: 'Ask clinical questions based on the current transcript.',
  embedAskQuestion: 'Ask a question...',
  embedStopRecording: 'Stop recording',
  embedVoiceInput: 'Voice input',
  embedStop: 'Stop',
  embedRecord: 'Record',
  embedSettingsLabel: 'Settings',
  embedCodeLabel: 'Code',
  embedRestartSessionHint: 'Restart session to see changes in the preview',
  embedSessionDefaults: 'Session defaults',
  embedPrimaryLanguage: 'Primary spoken language',
  embedDefaultMode: 'Default mode',
  embedModeInPerson: 'In-person',
  embedModeVirtual: 'Virtual',
  embedFeatures: 'Features',
  embedFeatureAllowVirtual: 'Allow virtual mode',
  embedFeatureShowTitle: 'Show interaction title',
  embedFeatureEnableAiChat: 'Enable AI chat',
  embedFeatureShowFeedback: 'Show document feedback',
  embedFeatureEnableEditor: 'Enable template editor',
  embedFeatureShowNav: 'Show navigation',
  embedFeatureShowSync: 'Show sync-document action',
  embedAppearance: 'Appearance',
  embedPrimaryColor: 'Primary color',
  embedLocaleSection: 'Locale',
  embedInterfaceLanguage: 'Interface language',
  embedDictationLanguage: 'Dictation language',
  embedNewToAssistant: 'New to Embedded Assistant?',
  embedTakeTour: 'Take a tour',
  embedDismiss: 'Dismiss',
  embedSkipTour: 'Skip tour',
  embedPrevStep: 'Previous',
  embedNextStep: 'Next',
  embedGetStarted: 'Get started',
  // Orchestration Pipeline
  orchestrationTitle: 'Coding Audit Pipeline',
  orchestrationDesc: 'Run the complete 9-step coding audit pipeline with multi-expert collaboration for diagnosis coding, procedure coding, DRG analysis, and compliance review',
  orchestrationSelectEncounter: 'Select an encounter or enter clinical text',
  orchestrationExistingEncounter: 'Existing encounter',
  orchestrationNewClinicalText: 'New clinical text',
  orchestrationEncounterPlaceholder: 'Search encounters...',
  orchestrationNoEncounterFound: 'No encounters found',
  orchestrationEnterClinicalText: 'Paste clinical text here (medical records, discharge summaries, operative notes)...',
  orchestrationPipelineSteps: 'Pipeline Steps',
  orchestrationProgress: 'Progress',
  orchestrationStatusIdle: 'Ready to start',
  orchestrationStatusRunning: 'Running...',
  orchestrationStatusCompleted: 'Completed',
  orchestrationStatusFailed: 'Failed',
  orchestrationRunPipeline: 'Run Coding Audit Pipeline',
  orchestrationDiagnosisCandidates: 'Diagnosis Code Candidates',
  orchestrationProcedureCandidates: 'Procedure Code Candidates',
  orchestrationDrgImpact: 'DRG Impact Analysis',
  orchestrationDocumentationGaps: 'Documentation Gaps',
  orchestrationHumanChecklist: 'Human Review Checklist',
  orchestrationHumanReview: 'Human Review',
  orchestrationApprove: 'Approve',
  orchestrationReject: 'Reject',
  orchestrationRationale: 'Review Rationale',
  orchestrationRationalePlaceholder: 'Describe the reason for approval or rejection...',
  orchestrationAuditTrail: 'Audit Trail',
  orchestrationNoAuditEvents: 'No audit events yet',
  orchestrationViewReport: 'View Full Report',
  orchestrationReportMarkdown: 'Markdown Report',
  orchestrationReportHtml: 'HTML Report',
  orchestrationEventLog: 'Event Log',

  // Organization
  orgSwitch: 'Switch Organization',
  orgNoOrg: 'No Organization',
  orgSelectOrg: 'Select Organization',
  orgCreate: 'Create Organization',
  orgManage: 'Organization Management',
  orgName: 'Organization Name',
  orgPlan: 'Plan',
  orgMembers: 'Members',
  orgInvite: 'Invite Member',
  orgInviteEmail: 'Email Address',
  orgInviteRole: 'Role',
  orgRemoveMember: 'Remove Member',
  orgRoleOwner: 'Owner',
  orgRoleAdmin: 'Admin',
  orgRoleMember: 'Member',
  orgRoleViewer: 'Viewer',
};

export const locales: Record<Locale, LocaleDict> = {
  'zh-CN': zhCN,
  'en-US': enUS,
};
