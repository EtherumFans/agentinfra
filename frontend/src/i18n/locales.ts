// iCoDer i18n - zh-CN (default) + en-US
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
  homeSubtitle: string;
  homeFooterHint: string;
  homeTabTranscribe: string;
  homeTabTranscribeDesc: string;
  homeTabTranscribeCta: string;
  homeTabDocument: string;
  homeTabDocumentDesc: string;
  homeTabDocumentCta: string;
  homeTabChat: string;
  homeTabChatDesc: string;
  homeTabChatCta: string;
  homeTabCode: string;
  homeTabCodeDesc: string;
  homeTabCodeCta: string;
  homePropRealtime: string;
  homePropDication: string;
  homePropDetect: string;
  homePropTemplate: string;
  homePropMultilang: string;
  homePropStructured: string;
  homePropEmbed: string;
  homePropSession: string;
  homePropMultimodal: string;
  homePropIcdCn: string;
  homePropEvidence: string;
  homePropRule: string;
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
  codingCompliance: string;
  cdiWorkbench: string;
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
  createAgentSubtitle: string;
  useCaseFilter: string;
  askTheAgent: string;
  agentInputPlaceholder: string;
  messagingConsumesCredits: string;
  customizeAgent: string;
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
  codingSystemsInfo: string;
  addSystem: string;
  close: string;
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
  charCount: string;
  costEstimate: string;
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
  agentChatAvailableCredits: string;

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

  // Medical Coding pipeline UI (Corti-aligned - was MedCodER pipeline)
  medcoderPipeline: string;  // deprecated alias, kept for back-compat
  medcoderMode: string;      // deprecated alias, kept for back-compat
  enableMedcoder: string;    // deprecated alias, kept for back-compat
  codingPipeline: string;
  codingMode: string;
  enableCoding: string;
  evidenceHighlight: string;
  topKCandidates: string;
  overrideCode: string;
  overridePlaceholder: string;
  overrideConfirm: string;
  diagnosisCard: string;
  supportingEvidence: string;
  llmInitialCode: string;
  rerankNotes: string;
  noExtractedDiagnoses: string;
  pipelineNotes: string;
  // Per-diagnosis card i18n (C10)
  diagnosisNumber: string;       // e.g. "诊断 #1" / "Diagnosis #1"
  topKClickHint: string;         // e.g. "Top-5 候选 (点击选择)" / "Top-5 candidates (click to select)"
  extractedDiagnosesCount: string; // e.g. "3 diagnoses" / "3 个诊断"
  noDiseaseName: string;         // fallback "(无疾病名)" / "(no disease name)"
  confidencePercent: string;     // e.g. "置信度 85%" / "Confidence 85%"
  positionRange: string;         // evidence chip title e.g. "位置 0-12" / "Position 0-12"

  // Medical Coding - Corti-aligned extras
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
  speechToTextBreadcrumb: string;
  textGenBreadcrumb: string;
  factExtractionBreadcrumb: string;
  embeddedAssistantBreadcrumb: string;
  tabCode: string;

  // Phase 3-A Section D - Corti-style 8-field output + banners
  mvpBanner: string;
  aiAssistedBanner: string;
  reviewSummary: string;
  reviewConclusion: string;
  reviewConclusionPass: string;
  reviewConclusionWarning: string;
  reviewConclusionFail: string;
  manualReviewRequired: string;
  // Note: documentationGaps + validationSummary already declared in Review section above; reused.
  uncodableItems: string;
  encounterSummary: string;
  traceRefs: string;
  noDocumentationGaps: string;
  noUncodableItems: string;
  rulesPassed: string;
  rulesFired: string;
  runId: string;
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
  dailyCostChart: string;
  requests: string;

  // Customers (Embedded Assistant end-user mgmt - Corti parity)
  customersTitle: string;
  customersDesc: string;
  addCustomer: string;
  searchCustomerPlaceholder: string;
  clearFilters: string;
  customerColName: string;
  customerColNfr: string;
  customerColRegion: string;
  customerColCustomerId: string;
  customerColCreated: string;
  customerColActions: string;
  customerIdSuffix: string;
  customerIdSuffixHelp: string;
  customerRegionUs: string;
  customerRegionEu: string;
  customerRegionCn: string;
  customerNoData: string;
  customerDeleteConfirm: string;
  customerDeleteSuccess: string;
  customerCreateSuccess: string;

  // Templates (Beta) - Corti /templates parity
  templatesTitle: string;
  templatesDesc: string;
  templateBuilder: string;
  viewTemplates: string;
  viewSections: string;
  searchTemplatesPlaceholder: string;
  allTypes: string;
  filter: string;
  builtinBadge: string;
  scopeAllCustomers: string;
  noTemplates: string;
  createTemplate: string;
  templateNamePlaceholder: string;
  templateDescPlaceholder: string;
  templateContentPlaceholder: string;
  templateCategory: string;
  templateLanguage: string;
  templateCategoryInpatient: string;
  templateCategorySurgery: string;
  templateCategoryOutpatient: string;
  templateCategoryEmergency: string;
  templateCategoryConsultation: string;
  templateCategoryCustom: string;
  templateLanguageZh: string;
  templateLanguageEn: string;

  // Tickets Portal - Corti /tickets parity
  ticketsTitle: string;
  ticketsDesc: string;
  ticketsAll: string;
  ticketsCreatedByMe: string;
  ticketsNewTicket: string;
  ticketsSubject: string;
  ticketsDescription: string;
  ticketsPriority: string;
  ticketsStatus: string;
  ticketsColSubject: string;
  ticketsColStatus: string;
  ticketsColPriority: string;
  ticketsColUpdated: string;
  ticketsColActions: string;
  ticketsNoData: string;
  ticketsDeleteConfirm: string;
  ticketsManagedElsewhere: string;
  ticketsStatusOpen: string;
  ticketsStatusInProgress: string;
  ticketsStatusResolved: string;
  ticketsStatusClosed: string;
  ticketsPriorityLow: string;
  ticketsPriorityMedium: string;
  ticketsPriorityHigh: string;

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

  // Phase 3-E - AI Studio Overview
  aiStudioOverviewTitle: string;
  aiStudioOverviewAgentsCard: string;
  aiStudioOverviewAgentsCardDesc: string;
  aiStudioOverviewCodingCard: string;
  aiStudioOverviewCodingCardDesc: string;
  aiStudioOverviewRecentAgents: string;
  aiStudioOverviewViewAll: string;
  aiStudioOverviewRecentRuns: string;

  // Phase 3-E - API Clients Page
  apiClientsLoadFailed: string;
  apiClientsOAuthCreated: string;
  apiClientsCopySecret: string;
  apiClientsClientId: string;
  apiClientsDone: string;
  apiClientsSubtitle: string;
  apiClientsCreateOAuth: string;
  apiClientsTabOAuth: string;
  apiClientsTabKeys: string;
  apiClientsCreateTitle: string;
  apiClientsNamePlaceholder: string;
  apiClientsDescPlaceholder: string;
  apiClientsScopesPlaceholder: string;
  apiClientsCreate: string;
  apiClientsCancel: string;
  apiClientsNoOAuth: string;
  apiClientsNoOAuthHint: string;
  apiClientsNoKeys: string;
  apiClientsConfirmRevokeTitle: string;
  apiClientsRevokeConfirm: string;
  apiClientsRevokeHint: string;
  apiClientsConfirmRevoke: string;
  apiClientsCreateFailed: string;
  apiClientsDeleteFailed: string;

  // Phase 3-E - Release Notes
  releaseNotesTitle: string;
  releaseNotesSubtitle: string;
  releaseNotesApiPolicy: string;

  // Phase 3-E - Reset Password
  resetPasswordTooShort: string;
  resetPasswordMismatch: string;
  resetPasswordNoToken: string;
  resetPasswordSuccess: string;
  resetPasswordFailed: string;
  resetPasswordTitle: string;
  resetPasswordSubtitle: string;
  resetPasswordBackToLogin: string;
  resetPasswordNewPassword: string;
  resetPasswordNewPlaceholder: string;
  resetPasswordConfirm: string;
  resetPasswordConfirmPlaceholder: string;
  resetPasswordLoading: string;
  resetPasswordSubmit: string;

  // Phase 3-E - RunTrace viewer
  runTraceStepUserMessageReceived: string;
  runTraceStepPlannerSelectedExperts: string;
  runTraceStepToolsList: string;
  runTraceStepAuthResolved: string;
  runTraceStepScopeChecked: string;
  runTraceStepToolsCall: string;
  runTraceStepExpertResponse: string;
  runTraceStepOutputGenerated: string;
  runTraceStepCompletion: string;
  runTraceNoMetadata: string;
  runTraceNoRequiredScopes: string;
  runTraceDispatcherDetail: string;
  runTraceRawSafeMetadata: string;
  runTraceSafeMetadata: string;
  runTraceToolCount: string;
  runTraceToolNames: string;
  runTraceToolName: string;
  runTraceHandlerRef: string;
  runTraceStage: string;
  runTraceAuthType: string;
  runTraceInProcessBypass: string;
  runTraceRedactedView: string;
  runTraceGrantedScopes: string;
  runTraceNote: string;
  runTraceScopeDiff: string;
  runTraceArguments: string;
  runTraceArgumentsKeysLabel: string;
  runTraceChars: string;
  runTraceValidated: string;
  runTraceResult: string;
  runTraceResultKeysLabel: string;
  runTraceError: string;
  runTraceMcpErrorCode: string;
  runTraceTotalDispatch: string;
  runTraceTotalDispatchBreakdown: string;
  runTraceTitle: string;
  runTraceRunId: string;
  runTraceSteps: string;
  runTraceOk: string;
  runTraceFailed: string;
  runTraceTotal: string;
  runTraceIntro: string;
  runTraceAuthFilter: string;
  runTraceEmpty: string;
  runTraceEmptyHint: string;
  runTraceRetry: string;
  runTraceNotFound: string;
  runTraceNotFoundHint: string;
  runTraceLoadFailed: string;
  runTraceLoadError: string;
  runTraceBack: string;
  runTraceBackToHub: string;
  runTraceDispatcherHeader: string;
  // Phase 3-D2.5 - Tool Dispatch Detail
  runTraceToolDispatchDetail: string;
  runTraceDispatchMode: string;
  runTraceRoundIndex: string;
  runTraceCaller: string;
  runTraceSchemaValidation: string;
  runTracePhiRedaction: string;
  runTraceScopeCheck: string;
  runTraceHandlerStatus: string;
  runTraceResultShape: string;
  runTraceErrorStage: string;
  runTraceDurationMs: string;

  // Phase 3-E - Agent Chat
  agentChatGreetingMedicalCoding: string;
  agentChatNotFoundToast: string;
  agentChatLoadFailed: string;
  agentChatDefaultGreeting: string;
  agentChatRunComplete: string;
  agentChatRunFailed: string;
  agentChatNotCloned: string;
  agentChatRedirecting: string;
  agentChatBack: string;
  agentChatInput: string;
  agentChatInputPlaceholder: string;
  agentChatCharCount: string;
  agentChatRunning: string;
  agentChatRun: string;
  agentChatRunFailedTitle: string;
  agentChatResult: string;
  agentChatDuration: string;
  agentChatViewRunTrace: string;
  agentChatViewRunTraceHint: string;
  agentChatRenderedTab: string;
  agentChatJsonTab: string;
  // Phase 4-D - Corti naming catalog (en-US matches Corti verbatim)
  agentChatBreadcrumbAgents: string;
  agentChatTextareaPlaceholder: string;
  agentChatAddContext: string;
  agentChatConsumesCredits: string;
  agentChatSettings: string;
  agentChatCode: string;
  agentChatNameLabel: string;
  agentChatSystemPrompt: string;
  agentChatExperts: string;
  agentChatBrowseExpertLibrary: string;
  agentChatCustomExperts: string;
  agentChatAddExpert: string;
  agentChatPinnedMessageParts: string;
  agentChatSdkJavaScript: string;
  agentChatSdkDotNet: string;
  agentChatSdkJsonConfig: string;
  agentChatCopy: string;
  agentChatApiClient: string;
  agentChatRunHistory: string;
  agentChatNewAgent: string;
  agentChatUseAgent: string;
  agentChatCustomize: string;
  agentChatSaved: string;
  agentChatSaveFailed: string;
  agentChatSaving: string;
  agentChatNoExperts: string;
  agentChatNoPinnedParts: string;
  agentChatExpertLibraryStub: string;
  agentChatAddExpertStub: string;
  agentChatBadJson: string;
  agentChatRemoveAttachment: string;

  // Phase 3-E - Workbench Layout
  workbenchLayoutInput: string;
  workbenchLayoutOutput: string;
  workbenchLayoutSettings: string;
  workbenchLayoutEventInspector: string;

  // Phase 3-E - Edit System Prompt Modal
  editSystemPromptTitle: string;
  editSystemPromptSubtitle: string;
  editSystemPromptTemplateHint: string;
  editSystemPromptGenerating: string;
  editSystemPromptAIGenerate: string;
  editSystemPromptCancel: string;
  editSystemPromptSave: string;

  // Phase 3-E - Tool Selector
  toolSelectorLoading: string;
  toolSelectorAvailableTools: string;
  toolSelectorSearchPlaceholder: string;
  toolSelectorTier1Toggle: string;
  toolSelectorCategorySafety: string;
  toolSelectorCategoryExtraction: string;
  toolSelectorCategoryCoding: string;
  toolSelectorCategoryVerification: string;
  toolSelectorCategoryAnalysis: string;
  toolSelectorCategoryReport: string;
  toolSelectorAuto: string;
  toolSelectorId: string;
  toolSelectorPreconditions: string;
  toolSelectorPostconditions: string;
  toolSelectorNoMatch: string;
  toolSelectorSelected: string;
  toolSelectorTier1: string;
  toolSelectorTier2: string;

  // Phase 3-E - Org Switcher
  orgSwitcherNoOrg: string;
  orgSwitcherSelectOrg: string;
  orgSwitcherOrganizations: string;
  orgSwitcherNoOrgsFound: string;
  orgSwitcherCreateManage: string;

  // Phase 3-E - Event Inspector
  eventInspectorTitle: string;
  eventInspectorCreditsConsumed: string;
  eventInspectorNoEvents: string;

  // Phase 3-E - Error Boundary
  errorBoundaryLoadFailed: string;
  errorBoundaryRetry: string;

  // Phase 3-E - TopK Chips
  topKChipsNoCandidates: string;

  // Phase 3-E - Settings Code Tab
  settingsCodeTabSettings: string;
  settingsCodeTabCode: string;
  settingsCodeTabTools: string;

  // Phase 3-E - Code Snippet
  codeSnippetJavaScript: string;
  codeSnippetJSON: string;
  codeSnippetJavaScriptSDK: string;
  codeSnippetPythonSDK: string;
  codeSnippetCurl: string;
  codeSnippetCSharpSDK: string;
  codeSnippetJSONConfig: string;
  codeSnippetCopyCode: string;

  // Phase 3-E - A2A Collaboration
  a2aCollaborationTitle: string;
  a2aCollaborationNAvailable: string;
  a2aCollaborationEmpty: string;

  // Phase 3-E+ - Agent UI i18n extension (cards / buttons / toasts / modal / detail)
  agentCardChatUse: string;
  agentCardCustomize: string;
  agentCardCloning: string;
  agentCardProductionReadyFalse: string;
  agentCardExpertsSuffix: string;
  agentCardToolsSuffix: string;
  agentEnable: string;
  agentDisable: string;
  agentUninstall: string;
  agentConfirmUninstall: string;
  agentEnabledToast: string;
  agentDisabledToast: string;
  agentUninstalledToast: string;
  agentUninstallFailedToast: string;
  agentClonedToDraftToast: string;
  agentCloneFailedToast: string;
  agentClonedEnterChatToast: string;
  agentExistingCloneToast: string;
  agentLoginRequiredToast: string;
  agentNotFoundToast: string;
  agentVersionBumpedToast: string;
  agentVersionBumpFailedToast: string;
  agentSelectTemplate: string;
  agentSearchTemplatePlaceholder: string;
  agentNameLabel: string;
  agentAdvancedSettings: string;
  agentDescriptionLabel: string;
  agentDescriptionPlaceholder: string;
  agentCategoryLabel: string;
  agentSystemPromptLabel: string;
  agentSystemPromptPlaceholder: string;
  agentAiGenerate: string;
  agentChatAgentFallback: string;
  agentChatAgentDescriptionPrefix: string;
  agentChatSourceRef: string;
  agentDetailTestTitle: string;
  agentDetailTestInputPlaceholder: string;
  agentDetailRunTest: string;
  agentDetailRunning: string;
  agentDetailTestFailed: string;
  agentDetailStatus: string;
  agentDetailDuration: string;
  agentDetailSafety: string;
  agentDetailVerified: string;
  agentDetailPrimaryDx: string;
  agentDetailSecondaryDx: string;
  agentDetailProcedures: string;
  agentDetailIssues: string;
  agentDetailRuleChecks: string;
  agentDetailEvalTitle: string;
  agentDetailEvaluating: string;
  agentDetailRunGoldStandard: string;
  agentDetailDxAccuracy: string;
  agentDetailProcAccuracy: string;
  agentDetailExportCsv: string;
  agentDetailHistoryTrend: string;
  agentDetailBasicInfo: string;
  agentDetailOrchestrationStrategy: string;
  agentDetailRoutingStrategy: string;
  agentDetailPermissionPreset: string;
  agentDetailMaxRetriesLabel: string;
  agentDetailConfidenceThresholdLabel: string;
  agentDetailConfidenceLoose: string;
  agentDetailConfidenceStrict: string;
  agentDetailEditCase: string;
  agentDetailEdit: string;
  agentDetailRemove: string;
  agentDetailDragSort: string;
  agentDetailDragHint: string;
  agentDetailExpertCountSuffix: string;
  agentDetailInstalledToast: string;
  agentDetailInstallFailed: string;
  agentDetailOperationFailed: string;
  agentDetailRoutingLlmPlan: string;
  agentDetailRoutingToolNative: string;
  agentDetailRoutingFixedOrder: string;
  agentDetailRoutingParallel: string;
  agentDetailRoutingSingleExpert: string;
  agentDetailRoutingLlmPlanDesc: string;
  agentDetailRoutingToolNativeDesc: string;
  agentDetailRoutingFixedOrderDesc: string;
  agentDetailRoutingParallelDesc: string;
  agentDetailRoutingSingleExpertDesc: string;
  agentDetailPermissionMedicalCoding: string;
  agentDetailPermissionCdiAudit: string;
  agentDetailPermissionDrgAnalysis: string;
  agentDetailPermissionRestrictive: string;
  agentDetailPermissionFullAccess: string;
  agentDetailPermissionMedicalCodingDesc: string;
  agentDetailPermissionCdiAuditDesc: string;
  agentDetailPermissionDrgAnalysisDesc: string;
  agentDetailPermissionRestrictiveDesc: string;
  agentDetailPermissionFullAccessDesc: string;
  agentDetailTestCaseLabel: string;
  agentDetailTestCaseText: string;
  agentDetailCapabilityQuestion: string;

  // Phase 3-E+ - Use case filter dropdown (Corti 5 enum keys)
  useCaseCodingRevenueCycle: string;
  useCaseClinicalEvidenceResearch: string;
  useCasePointOfCare: string;
  useCaseCareCoordination: string;
  useCaseChinaMedicalCompliance: string;

  // Phase 3-E+ - AI Studio Overview (Corti 1:1 replica)
  aiStudioOverviewHeroEyebrow: string;
  aiStudioOverviewHeroTitle: string;
  aiStudioOverviewHeroTagline: string;
  aiStudioOverviewExploreLabel: string;
  aiStudioOverviewExploreDesc: string;
  aiStudioOverviewInspectLabel: string;
  aiStudioOverviewInspectDesc: string;
  aiStudioOverviewConfigureLabel: string;
  aiStudioOverviewConfigureDesc: string;
  aiStudioOverviewExploreCapabilities: string;
  aiStudioOverviewAgentsName: string;
  aiStudioOverviewAgentsDesc: string;
  aiStudioOverviewSttName: string;
  aiStudioOverviewSttDesc: string;
  aiStudioOverviewTextGenName: string;
  aiStudioOverviewTextGenDesc: string;
  aiStudioOverviewEmbeddedName: string;
  aiStudioOverviewEmbeddedDesc: string;
  aiStudioOverviewFactExtractName: string;
  aiStudioOverviewFactExtractDesc: string;
  aiStudioOverviewCodingName: string;
  aiStudioOverviewCodingDesc: string;
  aiStudioOverviewExploreCta: string;
  aiStudioOverviewDocsCta: string;
  aiStudioOverviewDiveIntoCode: string;
  aiStudioOverviewDevQuickstart: string;
  aiStudioOverviewFooterDocs: string;
  aiStudioOverviewFooterAuth: string;
  aiStudioOverviewFooterGuides: string;
  aiStudioOverviewFooterApiRef: string;
  aiStudioOverviewFooterSdks: string;
  aiStudioOverviewFooterJsSdk: string;
  aiStudioOverviewFooterPostman: string;
  aiStudioOverviewFooterAiCoding: string;
  aiStudioOverviewFooterHelp: string;
  aiStudioOverviewFooterChat: string;
  aiStudioOverviewFooterTicket: string;
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
  homeSubtitle: '医疗收入合规 AI 工作台',
  homeFooterHint: '所有工作台支持通过 API Client 程序化访问',
  homeTabTranscribe: '转写',
  homeTabTranscribeDesc: '实时捕捉医患对话,为环境式病历和临床级口述应用提供支持',
  homeTabTranscribeCta: '开始录音',
  homeTabDocument: '文书',
  homeTabDocumentDesc: '基于临床文本自动生成结构化医疗文书',
  homeTabDocumentCta: '生成文书',
  homeTabChat: '对话',
  homeTabChatDesc: '为你的应用嵌入 AI 对话助手',
  homeTabChatCta: '打开助手',
  homeTabCode: '编码',
  homeTabCodeDesc: '基于临床证据生成准确的医学编码(ICD-10-CN / ICD-9-CM-3)',
  homeTabCodeCta: '打开编码工作台',
  homePropRealtime: '实时转写,支持环境式病历',
  homePropDication: '临床级口述应用',
  homePropDetect: '自动识别临床指令',
  homePropTemplate: '可定制文书模板',
  homePropMultilang: '多语言输出',
  homePropStructured: '结构化字段输出',
  homePropEmbed: 'Web Component 嵌入',
  homePropSession: '会话级上下文保持',
  homePropMultimodal: '多模态输入支持',
  homePropIcdCn: '中国编码体系(ICD-10-CN / ICD-9-CM-3)',
  homePropEvidence: '基于证据片段的代码引用',
  homePropRule: '规则引擎校验 + 修复循环',
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
  codingCompliance: '编码合规',
  cdiWorkbench: 'CDI 工作台',
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
  newAgent: '新建智能体',
  all: '全部',
  myAgents: '我的AI智能体',
  prebuiltAgents: 'iCoDer 预置',
  createdBy: '创建者',
  searchAgents: '搜索AI智能体...',
  noAgents: '暂无AI智能体',
  createAgent: '创建AI智能体',
  createAgentSubtitle: '构建医疗AI智能体，在您的业务系统中执行任务',
  useCaseFilter: '使用场景',
  askTheAgent: '咨询AI智能体...',
  agentInputPlaceholder: '我可以帮您什么？',
  messagingConsumesCredits: '与AI智能体对话将消耗额度',
  customizeAgent: '自定义智能体',
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
  codingSystemsInfo: '选择要包含的编码体系（ICD-10 / ICD-9-CM-3 / 限定版）。点击 × 移除，点击 + 添加。',
  addSystem: '+ 添加',
  close: '关闭',
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
  charCount: '{n} 字',
  costEstimate: '约 ¥{n}',
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
  agentChatAvailableCredits: '可用积分',

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

  // Medical Coding pipeline UI (Corti-aligned - was MedCodER pipeline)
  medcoderPipeline: '编码管线',  // deprecated alias
  medcoderMode: '编码模式 (Corti-style)',  // deprecated alias
  enableMedcoder: '启用编码管线',  // deprecated alias
  codingPipeline: '编码管线',
  codingMode: '编码模式 (Corti-style)',
  enableCoding: '启用编码管线',
  evidenceHighlight: '证据高亮',
  topKCandidates: 'Top-K 候选编码',
  overrideCode: '修改编码',
  overridePlaceholder: '输入 ICD-10 编码',
  overrideConfirm: '确定',
  diagnosisCard: '疾病诊断',
  supportingEvidence: '支持证据',
  llmInitialCode: 'LLM 初始编码',
  rerankNotes: '重排说明',
  noExtractedDiagnoses: '无疾病抽取结果',
  pipelineNotes: '管线说明',
  // Per-diagnosis card (C10)
  diagnosisNumber: '诊断 #{{n}}',
  topKClickHint: 'Top-{{k}} 候选 (点击选择)',
  extractedDiagnosesCount: '{{n}} 个诊断',
  noDiseaseName: '(无疾病名)',
  confidencePercent: '置信度 {{p}}%',
  positionRange: '位置 {{start}}-{{end}}',

  // Medical Coding - Corti-aligned extras
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

  // Phase 3-A Section D - Corti-style 8-field output + banners
  mvpBanner: 'MVP - production_ready=false, human_review=required',
  aiAssistedBanner: 'AI-assisted coding - 不替代编码员, 所有编码建议需人工复核',
  reviewSummary: '复核摘要',
  reviewConclusion: '复核结论',
  reviewConclusionPass: '通过',
  reviewConclusionWarning: '警告',
  reviewConclusionFail: '失败',
  manualReviewRequired: '需要人工复核',
  // Note: documentationGaps + validationSummary already declared in Review section above; reused.
  uncodableItems: '无法编码项',
  encounterSummary: '就诊摘要',
  traceRefs: '追踪引用',
  noDocumentationGaps: '无文档缺口',
  noUncodableItems: '无无法编码项',
  rulesPassed: '规则通过',
  rulesFired: '触发规则',
  runId: '运行 ID',
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
  speechToTextBreadcrumb: '语音转录',
  textGenBreadcrumb: '文书生成',
  factExtractionBreadcrumb: '事实抽取',
  embeddedAssistantBreadcrumb: '嵌入助手',
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
  dailyCostChart: '每日成本趋势',
  requests: '请求',

  // Customers
  customersTitle: '客户',
  customersDesc: '管理 Embedded Assistant 的下游客户与终端用户',
  addCustomer: '新建客户',
  searchCustomerPlaceholder: '按名称 / Customer ID / Region / Tenant 搜索',
  clearFilters: '清除筛选',
  customerColName: '名称',
  customerColNfr: 'NFR',
  customerColRegion: '区域',
  customerColCustomerId: 'Customer ID',
  customerColCreated: '创建时间',
  customerColActions: '操作',
  customerIdSuffix: 'Customer ID 后缀',
  customerIdSuffixHelp: '支持字母、数字、-、_（最多 64 字符）',
  customerRegionUs: '美国',
  customerRegionEu: '欧洲',
  customerRegionCn: '中国',
  customerNoData: '未找到客户',
  customerDeleteConfirm: '确定删除该客户？此操作不可撤销。',
  customerDeleteSuccess: '客户已删除',
  customerCreateSuccess: '客户已创建',

  // Templates
  templatesTitle: '模板',
  templatesDesc: '管理用于结构化文档生成的模板与章节',
  templateBuilder: '模板构建器',
  viewTemplates: '模板',
  viewSections: '章节',
  searchTemplatesPlaceholder: '搜索模板',
  allTypes: '所有类型',
  filter: '筛选',
  builtinBadge: 'iCoDer 模板',
  scopeAllCustomers: '所有客户',
  noTemplates: '未找到模板',
  createTemplate: '新建模板',
  templateNamePlaceholder: '例如：出院小结',
  templateDescPlaceholder: '简短描述这个模板的用途',
  templateContentPlaceholder: '模板正文（提示词或结构化模板）',
  templateCategory: '类别',
  templateLanguage: '语言',
  templateCategoryInpatient: '住院',
  templateCategorySurgery: '手术',
  templateCategoryOutpatient: '门诊',
  templateCategoryEmergency: '急诊',
  templateCategoryConsultation: '会诊',
  templateCategoryCustom: '自定义',
  templateLanguageZh: '中文',
  templateLanguageEn: 'English',

  // Tickets
  ticketsTitle: '工单',
  ticketsDesc: '追踪问题与功能请求',
  ticketsAll: '全部',
  ticketsCreatedByMe: '我创建的',
  ticketsNewTicket: '新建工单',
  ticketsSubject: '主题',
  ticketsDescription: '描述',
  ticketsPriority: '优先级',
  ticketsStatus: '状态',
  ticketsColSubject: '主题',
  ticketsColStatus: '状态',
  ticketsColPriority: '优先级',
  ticketsColUpdated: '更新时间',
  ticketsColActions: '操作',
  ticketsNoData: '未找到工单',
  ticketsDeleteConfirm: '确定删除该工单？此操作不可撤销。',
  ticketsStatusOpen: '待处理',
  ticketsStatusInProgress: '处理中',
  ticketsStatusResolved: '已解决',
  ticketsStatusClosed: '已关闭',
  ticketsPriorityLow: '低',
  ticketsPriorityMedium: '中',
  ticketsPriorityHigh: '高',
  ticketsManagedElsewhere: '工单通过帮助台系统进行管理',

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
  devQsNoRequestBody: 'GET 请求 - 无需请求体',
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

  // Phase 3-E - AI Studio Overview
  aiStudioOverviewTitle: 'AI Studio',
  aiStudioOverviewAgentsCard: 'AI 智能体',
  aiStudioOverviewAgentsCardDesc: '管理、创建和市场发现 Agent',
  aiStudioOverviewCodingCard: '医学编码',
  aiStudioOverviewCodingCardDesc: 'ICD-10/ICD-9-CM-3 智能编码',
  aiStudioOverviewRecentAgents: '最近 Agent',
  aiStudioOverviewViewAll: '全部',
  aiStudioOverviewRecentRuns: '最近运行',

  // Phase 3-E - API Clients Page
  apiClientsLoadFailed: '加载失败',
  apiClientsOAuthCreated: 'OAuth 客户端已创建',
  apiClientsCopySecret: '复制 Client Secret - 它不会再次显示。',
  apiClientsClientId: 'Client ID',
  apiClientsDone: '完成',
  apiClientsSubtitle: '管理 API 密钥和 OAuth 2.0 客户端凭证',
  apiClientsCreateOAuth: '创建 OAuth 客户端',
  apiClientsTabOAuth: 'OAuth 2.0 客户端',
  apiClientsTabKeys: 'API 密钥',
  apiClientsCreateTitle: '创建 OAuth 2.0 客户端 (Client Credentials)',
  apiClientsNamePlaceholder: '客户端名称（如：生产环境SDK）',
  apiClientsDescPlaceholder: '描述（可选）',
  apiClientsScopesPlaceholder: 'Scopes（空格分隔）',
  apiClientsCreate: '创建',
  apiClientsCancel: '取消',
  apiClientsNoOAuth: '暂无 OAuth 客户端',
  apiClientsNoOAuthHint: '创建客户端以使用 client_credentials 认证',
  apiClientsNoKeys: '暂无 API 密钥',
  apiClientsConfirmRevokeTitle: '确认撤销',
  apiClientsRevokeConfirm: '撤销 OAuth 客户端',
  apiClientsRevokeHint: '使用此客户端的应用将无法认证。',
  apiClientsConfirmRevoke: '确认撤销',
  apiClientsCreateFailed: '创建失败',
  apiClientsDeleteFailed: '删除失败',

  // Phase 3-E - Release Notes
  releaseNotesTitle: 'Release Notes',
  releaseNotesSubtitle: 'iCoDer 医疗 AI 智能体平台版本变更记录。',
  releaseNotesApiPolicy: 'API 变更策略',

  // Phase 3-E - Reset Password
  resetPasswordTooShort: '密码至少需要 8 位',
  resetPasswordMismatch: '两次输入的密码不一致',
  resetPasswordNoToken: '缺少重置令牌，请从邮箱链接中获取',
  resetPasswordSuccess: '密码重置成功，请使用新密码登录',
  resetPasswordFailed: '重置失败，令牌可能已过期',
  resetPasswordTitle: '重置密码',
  resetPasswordSubtitle: '输入新的登录密码',
  resetPasswordBackToLogin: '返回登录',
  resetPasswordNewPassword: '新密码',
  resetPasswordNewPlaceholder: '至少 8 位字符',
  resetPasswordConfirm: '确认密码',
  resetPasswordConfirmPlaceholder: '再次输入密码',
  resetPasswordLoading: '重置中...',
  resetPasswordSubmit: '重置密码',

  // Phase 3-E - RunTrace viewer
  runTraceStepUserMessageReceived: '1. 用户消息接收',
  runTraceStepPlannerSelectedExperts: '2. Planner 选定 Expert',
  runTraceStepToolsList: '3. 工具列表',
  runTraceStepAuthResolved: '4. 鉴权完成',
  runTraceStepScopeChecked: '5. Scope 校验',
  runTraceStepToolsCall: '6. 工具调用',
  runTraceStepExpertResponse: '7. Expert 响应',
  runTraceStepOutputGenerated: '8. 输出生成',
  runTraceStepCompletion: '9. 完成',
  runTraceNoMetadata: '无 metadata',
  runTraceNoRequiredScopes: '无 required_scopes',
  runTraceDispatcherDetail: 'dispatcher detail',
  runTraceRawSafeMetadata: 'raw safe_metadata',
  runTraceSafeMetadata: 'safe_metadata',
  runTraceToolCount: 'tool_count',
  runTraceToolNames: 'tool_names',
  runTraceToolName: 'tool_name',
  runTraceHandlerRef: 'handler_ref',
  runTraceStage: 'stage',
  runTraceAuthType: 'auth_type',
  runTraceInProcessBypass: '⚠ in-process bypass',
  runTraceRedactedView: 'redacted_view',
  runTraceGrantedScopes: 'granted_scopes',
  runTraceNote: 'note',
  runTraceScopeDiff: 'scope diff (✓ matched / ✗ missing)',
  runTraceArguments: 'arguments',
  runTraceArgumentsKeysLabel: 'keys',
  runTraceChars: 'chars',
  runTraceValidated: 'validated ✓',
  runTraceResult: 'result',
  runTraceResultKeysLabel: 'keys',
  runTraceError: 'error',
  runTraceMcpErrorCode: 'mcp_error_code',
  runTraceTotalDispatch: 'total_dispatch',
  runTraceTotalDispatchBreakdown: '(auth+scope+resolve+handler)',
  runTraceTitle: 'RunTrace',
  runTraceRunId: 'run_id',
  runTraceSteps: 'steps',
  runTraceOk: 'ok',
  runTraceFailed: 'failed',
  runTraceTotal: 'total',
  runTraceIntro: '9 步 Corti-parity 时间线。蓝色边框 = 统一工具调度器 (Dispatcher) 的 4 个步骤。点击任一行展开查看 dispatcher 详情 + raw metadata。',
  runTraceAuthFilter: 'auth_resolved 步骤仅展示 tool_name / auth_type / redacted_view / granted_scopes / note，其余 metadata 一律隐藏（纵深防御）。',
  runTraceEmpty: '运行已完成但尚未发射 trace 事件。',
  runTraceEmptyHint: 'run 存在但 timeline 为空。可能是 trace emit 失败、DB 写入异常，或该 run 走了非 instrumented 路径。点击下方重试或返回 Agent Hub 重新发起。',
  runTraceRetry: '重试加载',
  runTraceNotFound: '未找到 RunTrace',
  runTraceNotFoundHint: '未找到该 run_id 的 trace 事件。该 run 可能尚未触发任何 MCP/Orchestrator 步骤，或仅在 A2A 路径执行（未走 MCP server）。',
  runTraceLoadFailed: '加载 RunTrace 失败',
  runTraceLoadError: '加载失败',
  runTraceBack: '返回',
  runTraceBackToHub: '返回 Agent Hub',
  runTraceDispatcherHeader: '统一工具调度器 / Dispatcher',
  // Phase 3-D2.5 - Tool Dispatch Detail
  runTraceToolDispatchDetail: 'Tool Dispatch Detail',
  runTraceDispatchMode: 'Dispatch Mode',
  runTraceRoundIndex: '轮次 / Round',
  runTraceCaller: '调用者 / Caller',
  runTraceSchemaValidation: 'Schema Validation',
  runTracePhiRedaction: 'PHI Redaction',
  runTraceScopeCheck: 'Scope Check',
  runTraceHandlerStatus: 'Handler Status',
  runTraceResultShape: 'Result Shape',
  runTraceErrorStage: 'Error Stage',
  runTraceDurationMs: 'Duration',

  // Phase 3-E - Agent Chat
  agentChatGreetingMedicalCoding: '请为以下病历文本进行 ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议。',
  agentChatNotFoundToast: '未找到 Agent - 请先从 Hub 克隆',
  agentChatLoadFailed: '加载 Agent 失败',
  agentChatDefaultGreeting: '请输入您的请求。',
  agentChatRunComplete: '运行完成',
  agentChatRunFailed: '运行失败',
  agentChatNotCloned: 'Agent 未克隆',
  agentChatRedirecting: '正在跳转到 Agent Hub，请从那里克隆后再进入对话。',
  agentChatBack: '返回 Agent Hub',
  agentChatInput: '输入',
  agentChatInputPlaceholder: '在此粘贴病历文本或输入您的请求…',
  agentChatCharCount: '字符',
  agentChatRunning: '运行中…',
  agentChatRun: '运行',
  agentChatRunFailedTitle: '运行失败',
  agentChatResult: '运行结果',
  agentChatDuration: '耗时',
  agentChatViewRunTrace: 'View RunTrace',
  agentChatViewRunTraceHint: '查看 RunTrace 9 步时间线',
  agentChatRenderedTab: 'Rendered',
  agentChatJsonTab: 'JSON',
  // Phase 4-D - Corti naming catalog (zh-CN translations)
  agentChatBreadcrumbAgents: '智能体',
  agentChatTextareaPlaceholder: '我能帮你什么？',
  agentChatAddContext: '添加上下文',
  agentChatConsumesCredits: '向智能体发送消息会消耗积分',
  agentChatSettings: '设置',
  agentChatCode: '代码',
  agentChatNameLabel: '名称',
  agentChatSystemPrompt: '系统提示词',
  agentChatExperts: '专家',
  agentChatBrowseExpertLibrary: '浏览专家库',
  agentChatCustomExperts: '自定义专家',
  agentChatAddExpert: '添加专家',
  agentChatPinnedMessageParts: '固定消息片段',
  agentChatSdkJavaScript: 'JavaScript (SDK)',
  agentChatSdkDotNet: '.NET (SDK)',
  agentChatSdkJsonConfig: 'JSON 配置',
  agentChatCopy: '复制',
  agentChatApiClient: 'API 客户端',
  agentChatRunHistory: '近期运行',
  agentChatNewAgent: '新建智能体',
  agentChatUseAgent: '使用智能体',
  agentChatCustomize: '自定义',
  agentChatSaved: '已保存',
  agentChatSaveFailed: '保存失败',
  agentChatSaving: '保存中…',
  agentChatNoExperts: '未配置专家',
  agentChatNoPinnedParts: '无固定消息片段',
  agentChatExpertLibraryStub: '专家库 - 即将推出 (Phase 5)',
  agentChatAddExpertStub: '添加专家 - 即将推出 (Phase 5)',
  agentChatBadJson: '无效 JSON 文件',
  agentChatRemoveAttachment: '移除附件',

  // Phase 3-E - Workbench Layout
  workbenchLayoutInput: 'Input',
  workbenchLayoutOutput: 'Output',
  workbenchLayoutSettings: 'Settings',
  workbenchLayoutEventInspector: 'Event Inspector',

  // Phase 3-E - Edit System Prompt Modal
  editSystemPromptTitle: 'Edit system prompt',
  editSystemPromptSubtitle: "Define the agent's role and style.",
  editSystemPromptTemplateHint: 'Use XML-style tags to structure sections. The <role> and <output_format> sections are required. Include an Example Output block within output_format for guidance.',
  editSystemPromptGenerating: 'Generating...',
  editSystemPromptAIGenerate: 'AI generate',
  editSystemPromptCancel: 'Cancel',
  editSystemPromptSave: 'Save',

  // Phase 3-E - Tool Selector
  toolSelectorLoading: 'Loading tools...',
  toolSelectorAvailableTools: 'Available Tools',
  toolSelectorSearchPlaceholder: 'Search tools...',
  toolSelectorTier1Toggle: 'Auto-inject accuracy guarantee tools (Tier 1)',
  toolSelectorCategorySafety: '安全护栏',
  toolSelectorCategoryExtraction: '信息提取',
  toolSelectorCategoryCoding: '编码',
  toolSelectorCategoryVerification: '验证',
  toolSelectorCategoryAnalysis: '分析',
  toolSelectorCategoryReport: '报告',
  toolSelectorAuto: 'Auto',
  toolSelectorId: 'ID',
  toolSelectorPreconditions: 'Preconditions',
  toolSelectorPostconditions: 'Postconditions',
  toolSelectorNoMatch: 'No tools found matching',
  toolSelectorSelected: 'tools selected',
  toolSelectorTier1: 'Tier 1',
  toolSelectorTier2: 'Tier 2',

  // Phase 3-E - Org Switcher
  orgSwitcherNoOrg: 'No Organization',
  orgSwitcherSelectOrg: 'Select Org',
  orgSwitcherOrganizations: 'Organizations',
  orgSwitcherNoOrgsFound: 'No organizations found',
  orgSwitcherCreateManage: '+ Create or manage organizations',

  // Phase 3-E - Event Inspector
  eventInspectorTitle: 'Event Inspector',
  eventInspectorCreditsConsumed: 'Credits consumed',
  eventInspectorNoEvents: 'No events recorded',

  // Phase 3-E - Error Boundary
  errorBoundaryLoadFailed: '加载失败',
  errorBoundaryRetry: '重试',

  // Phase 3-E - TopK Chips
  topKChipsNoCandidates: 'No candidates',

  // Phase 3-E - Settings Code Tab
  settingsCodeTabSettings: 'Settings',
  settingsCodeTabCode: 'Code',
  settingsCodeTabTools: 'Tools',

  // Phase 3-E - Code Snippet
  codeSnippetJavaScript: 'JavaScript',
  codeSnippetJSON: 'JSON',
  codeSnippetJavaScriptSDK: 'JavaScript (SDK)',
  codeSnippetPythonSDK: 'Python (SDK)',
  codeSnippetCurl: 'curl',
  codeSnippetCSharpSDK: 'C# (.NET SDK)',
  codeSnippetJSONConfig: 'JSON Config',
  codeSnippetCopyCode: 'Copy code',

  // Phase 3-E - A2A Collaboration
  a2aCollaborationTitle: 'A2A Agent 协作',
  a2aCollaborationNAvailable: '个可用',
  a2aCollaborationEmpty: '未发现其他 Agent（需启用 A2A）',

  // Phase 3-E+ - Agent UI i18n extension
  agentCardChatUse: 'Chat / Use Agent',
  agentCardCustomize: 'Customize',
  agentCardCloning: '克隆中…',
  agentCardProductionReadyFalse: 'production_ready=false',
  agentCardExpertsSuffix: '专家',
  agentCardToolsSuffix: '工具',
  agentEnable: '启用',
  agentDisable: '禁用',
  agentUninstall: '卸载',
  agentConfirmUninstall: '确定要卸载吗？',
  agentEnabledToast: '已启用',
  agentDisabledToast: '已禁用',
  agentUninstalledToast: '已卸载',
  agentUninstallFailedToast: '卸载失败',
  agentClonedToDraftToast: '已克隆为草稿',
  agentCloneFailedToast: '克隆失败',
  agentClonedEnterChatToast: '已克隆 - 进入对话',
  agentExistingCloneToast: '已有克隆 - 进入对话',
  agentLoginRequiredToast: '请先登录',
  agentNotFoundToast: 'Agent 不存在',
  agentVersionBumpedToast: '版本号已更新',
  agentVersionBumpFailedToast: '版本更新失败',
  agentSelectTemplate: '选择模板',
  agentSearchTemplatePlaceholder: '搜索模板...',
  agentNameLabel: 'Agent 名称',
  agentAdvancedSettings: '高级设置',
  agentDescriptionLabel: '描述',
  agentDescriptionPlaceholder: 'Agent 的功能描述',
  agentCategoryLabel: '分类',
  agentSystemPromptLabel: '系统提示词',
  agentSystemPromptPlaceholder: '系统提示词...',
  agentAiGenerate: 'AI 生成',
  agentChatAgentFallback: 'Agent',
  agentChatAgentDescriptionPrefix: 'Agent: {desc}',
  agentChatSourceRef: 'source: {ref}',
  agentDetailTestTitle: 'Agent 测试',
  agentDetailTestInputPlaceholder: '输入测试病历，验证 Agent 编码结果...',
  agentDetailRunTest: '运行测试',
  agentDetailRunning: '运行中...',
  agentDetailTestFailed: '测试失败',
  agentDetailStatus: '状态',
  agentDetailDuration: '耗时',
  agentDetailSafety: '安全',
  agentDetailVerified: '已校验',
  agentDetailPrimaryDx: '主诊断',
  agentDetailSecondaryDx: '次要诊断',
  agentDetailProcedures: '手术',
  agentDetailIssues: '问题',
  agentDetailRuleChecks: '规则检查',
  agentDetailEvalTitle: 'Agent 评估',
  agentDetailEvaluating: '评估中...',
  agentDetailRunGoldStandard: '运行金标准评估',
  agentDetailDxAccuracy: '诊断准确率',
  agentDetailProcAccuracy: '手术准确率',
  agentDetailExportCsv: '导出 CSV',
  agentDetailHistoryTrend: '历史趋势',
  agentDetailBasicInfo: '基本信息',
  agentDetailOrchestrationStrategy: '编排策略',
  agentDetailRoutingStrategy: '路由策略',
  agentDetailPermissionPreset: '权限策略 (Deny-First)',
  agentDetailMaxRetriesLabel: '最大重试次数: {n}',
  agentDetailConfidenceThresholdLabel: '置信度阈值: {n}',
  agentDetailConfidenceLoose: '0.0 (宽松)',
  agentDetailConfidenceStrict: '1.0 (严格)',
  agentDetailEditCase: '编辑病例内容',
  agentDetailEdit: '编辑',
  agentDetailRemove: '移除',
  agentDetailDragSort: '拖拽排序',
  agentDetailDragHint: '拖拽专家调整调用优先级',
  agentDetailExpertCountSuffix: '个',
  agentDetailInstalledToast: 'Agent 已安装到 Runtime',
  agentDetailInstallFailed: '安装失败',
  agentDetailOperationFailed: '操作失败，请检查权限',
  agentDetailRoutingLlmPlan: 'LLM 动态规划（推荐）',
  agentDetailRoutingToolNative: 'Tool-Native 合同强制（新）',
  agentDetailRoutingFixedOrder: '固定顺序执行',
  agentDetailRoutingParallel: '并行调用',
  agentDetailRoutingSingleExpert: '单专家直连',
  agentDetailRoutingLlmPlanDesc: '由 AI 分析任务后动态选择专家及调用顺序',
  agentDetailRoutingToolNativeDesc: 'LLM 自主选择工具，Harness 以合同强制验证每次调用',
  agentDetailRoutingFixedOrderDesc: '按列表顺序逐个调用绑定的专家',
  agentDetailRoutingParallelDesc: '同时调用所有专家，聚合结果',
  agentDetailRoutingSingleExpertDesc: '仅调用默认专家，忽略其他绑定',
  agentDetailPermissionMedicalCoding: '医学编码（推荐）',
  agentDetailPermissionCdiAudit: '临床文档审核（只读）',
  agentDetailPermissionDrgAnalysis: 'DRG/DIP 支付分析',
  agentDetailPermissionRestrictive: '严格模式（仅确定性工具）',
  agentDetailPermissionFullAccess: '全量访问（开发/管理）',
  agentDetailPermissionMedicalCodingDesc: '标准编码管道:确定性工具+LLM工具有限使用',
  agentDetailPermissionCdiAuditDesc: '只读分析工具:不允许编码分配',
  agentDetailPermissionDrgAnalysisDesc: '编码+DRG分析:适合医保审核',
  agentDetailPermissionRestrictiveDesc: '仅确定性工具（ICD索引/证据排名等），最大安全性',
  agentDetailPermissionFullAccessDesc: '全部工具可用:仅开发和管理使用',
  agentDetailTestCaseLabel: '腰椎间盘突出症',
  agentDetailTestCaseText: '患者，女，65岁。因腰痛伴左下肢放射痛3月就诊。腰椎MRI示L4/5椎间盘突出，压迫左侧神经根。入院诊断：腰椎间盘突出症。建议行PLIF手术。',
  agentDetailCapabilityQuestion: '你能做什么？请描述你的能力、专长以及如何在医疗编码、临床文档及相关医疗任务中提供帮助。',

  // Phase 3-E+ - Use case filter dropdown (Corti 5 enum keys)
  useCaseCodingRevenueCycle: '编码/收入循环',
  useCaseClinicalEvidenceResearch: '临床证据研究',
  useCasePointOfCare: '即时诊疗',
  useCaseCareCoordination: '诊疗协调',
  useCaseChinaMedicalCompliance: '中国医疗合规',

  // Phase 3-E+ - AI Studio Overview (Corti 1:1 replica)
  aiStudioOverviewHeroEyebrow: 'AI Studio',
  aiStudioOverviewHeroTitle: '总览',
  aiStudioOverviewHeroTagline: '直接在 iCoDer 控制台测试和配置用例',
  aiStudioOverviewExploreLabel: '探索',
  aiStudioOverviewExploreDesc: '构建智能体、生成实时转录、临床文书等',
  aiStudioOverviewInspectLabel: '检查',
  aiStudioOverviewInspectDesc: '通过事件检查器调试, 实时监控积分消耗',
  aiStudioOverviewConfigureLabel: '配置',
  aiStudioOverviewConfigureDesc: '按需精细调整设置, 直接复制代码到您的应用',
  aiStudioOverviewExploreCapabilities: '探索能力',
  aiStudioOverviewAgentsName: '智能体',
  aiStudioOverviewAgentsDesc: '通过添加专家、系统提示词和上下文自定义智能体',
  aiStudioOverviewSttName: '语音转文本',
  aiStudioOverviewSttDesc: '流式传输实时音频, 配置自定义命令并生成转录',
  aiStudioOverviewTextGenName: '文本生成',
  aiStudioOverviewTextGenDesc: '将转录转换为结构化临床笔记, 按需定制',
  aiStudioOverviewEmbeddedName: '嵌入式助手',
  aiStudioOverviewEmbeddedDesc: '配置和测试嵌入式环境抄录助手体验',
  aiStudioOverviewFactExtractName: '事实抽取',
  aiStudioOverviewFactExtractDesc: '从医疗转录和笔记中抽取结构化临床事实',
  aiStudioOverviewCodingName: '医学编码',
  aiStudioOverviewCodingDesc: '将非结构化临床文本转换为结构化医疗编码',
  aiStudioOverviewExploreCta: '探索',
  aiStudioOverviewDocsCta: '文档',
  aiStudioOverviewDiveIntoCode: '准备好深入代码并发起第一个请求了吗？',
  aiStudioOverviewDevQuickstart: '开发者快速开始',
  aiStudioOverviewFooterDocs: '文档',
  aiStudioOverviewFooterAuth: '认证',
  aiStudioOverviewFooterGuides: '指南',
  aiStudioOverviewFooterApiRef: 'API 参考',
  aiStudioOverviewFooterSdks: 'SDK 与工具',
  aiStudioOverviewFooterJsSdk: 'Javascript SDK',
  aiStudioOverviewFooterPostman: 'Postman',
  aiStudioOverviewFooterAiCoding: 'AI 编码工具',
  aiStudioOverviewFooterHelp: '需要帮助？',
  aiStudioOverviewFooterChat: '与我们聊天',
  aiStudioOverviewFooterTicket: '提交工单',
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
  homeSubtitle: 'Medical revenue compliance AI workbench',
  homeFooterHint: 'All workbenches support API access via API Clients.',
  homeTabTranscribe: 'Transcribe',
  homeTabTranscribeDesc: 'Capture conversation in real time for ambient scribes and clinical-grade dictation applications',
  homeTabTranscribeCta: 'Start recording',
  homeTabDocument: 'Document',
  homeTabDocumentDesc: 'Generate structured clinical documentation from clinical text',
  homeTabDocumentCta: 'Generate document',
  homeTabChat: 'Chat',
  homeTabChatDesc: 'Embed an AI assistant into your application',
  homeTabChatCta: 'Open assistant',
  homeTabCode: 'Code',
  homeTabCodeDesc: 'Generate accurate medical codes grounded in clinical evidence (ICD-10-CN / ICD-9-CM-3)',
  homeTabCodeCta: 'Open coding workbench',
  homePropRealtime: 'Real-time transcription for ambient scribes',
  homePropDication: 'Clinical-grade dictation applications',
  homePropDetect: 'Automatic clinical command detection',
  homePropTemplate: 'Customizable document templates',
  homePropMultilang: 'Multi-language output',
  homePropStructured: 'Structured field output',
  homePropEmbed: 'Web Component embedding',
  homePropSession: 'Session-level context retention',
  homePropMultimodal: 'Multi-modal input support',
  homePropIcdCn: 'Chinese coding system (ICD-10-CN / ICD-9-CM-3)',
  homePropEvidence: 'Evidence-based code citations',
  homePropRule: 'Rule engine validation + repair loop',
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
  codingCompliance: 'Coding Compliance',
  cdiWorkbench: 'CDI Workbench',
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
  prebuiltAgents: 'Built by iCoDer',
  createdBy: 'Created by',
  searchAgents: 'Search agents...',
  noAgents: 'No agents found',
  createAgent: 'Create an agent',
  createAgentSubtitle: 'Build healthcare agents to take action across your systems',
  useCaseFilter: 'Use case',
  askTheAgent: 'Ask the agent...',
  agentInputPlaceholder: 'What can I help you with?',
  messagingConsumesCredits: 'Messaging an agent consumes credits',
  customizeAgent: 'Customize agent',
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
  codingSystemsInfo: 'Select coding systems to include (ICD-10 / ICD-9-CM-3 / limited). Click × to remove, + to add.',
  addSystem: '+ Add',
  close: 'Close',
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
  charCount: '{n} chars',
  costEstimate: '~¥{n}',
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
  agentChatAvailableCredits: 'Available credits',

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

  // Medical Coding pipeline UI (Corti-aligned - was MedCodER pipeline)
  medcoderPipeline: 'Coding pipeline',  // deprecated alias
  medcoderMode: 'Coding mode (Corti-style)',  // deprecated alias
  enableMedcoder: 'Enable coding pipeline',  // deprecated alias
  codingPipeline: 'Coding pipeline',
  codingMode: 'Coding mode (Corti-style)',
  enableCoding: 'Enable coding pipeline',
  evidenceHighlight: 'Evidence highlight',
  topKCandidates: 'Top-K candidates',
  overrideCode: 'Override code',
  overridePlaceholder: 'Enter ICD-10 code',
  overrideConfirm: 'Confirm',
  diagnosisCard: 'Diagnosis',
  supportingEvidence: 'Supporting evidence',
  llmInitialCode: 'LLM initial code',
  rerankNotes: 'Re-rank notes',
  noExtractedDiagnoses: 'No extracted diagnoses',
  pipelineNotes: 'Pipeline notes',
  // Per-diagnosis card (C10)
  diagnosisNumber: 'Diagnosis #{{n}}',
  topKClickHint: 'Top-{{k}} candidates (click to select)',
  extractedDiagnosesCount: '{{n}} diagnoses',
  noDiseaseName: '(no disease name)',
  confidencePercent: 'Confidence {{p}}%',
  positionRange: 'Position {{start}}-{{end}}',

  // Medical Coding - Corti-aligned extras
  samples: 'Samples',
  openGuide: 'Open guided demo',
  dismissGuide: 'Dismiss guided demo',
  selectCodingSystem: 'Select coding systems',
  selectCodingSystemDesc: 'Pick the coding systems to use for this prediction (shared with right Settings)',
  guideStepSample: 'Pick a sample document',
  guideStepSystem: 'Pick coding systems',
  guideStepSampleDesc: 'Choose a sample document - the wizard will fill the input and trigger prediction',
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

  // Phase 3-A Section D - Corti-style 8-field output + banners
  mvpBanner: 'MVP - production_ready=false, human_review=required',
  aiAssistedBanner: 'AI-assisted coding - does not replace the coder; all code suggestions require human review',
  reviewSummary: 'Review summary',
  reviewConclusion: 'Review conclusion',
  reviewConclusionPass: 'Pass',
  reviewConclusionWarning: 'Warning',
  reviewConclusionFail: 'Fail',
  manualReviewRequired: 'Manual review required',
  // Note: documentationGaps + validationSummary already declared in Review section above; reused.
  uncodableItems: 'Uncodable items',
  encounterSummary: 'Encounter summary',
  traceRefs: 'Trace refs',
  noDocumentationGaps: 'No documentation gaps',
  noUncodableItems: 'No uncodable items',
  rulesPassed: 'Rules passed',
  rulesFired: 'Rules fired',
  runId: 'Run ID',
  tableDescription: 'Description',
  tableConfidence: 'Conf.',
  medicalCodingBreadcrumb: 'Medical coding',
  speechToTextBreadcrumb: 'Speech to Text',
  textGenBreadcrumb: 'Text Generation',
  factExtractionBreadcrumb: 'Fact Extraction',
  embeddedAssistantBreadcrumb: 'Embedded Assistant',
  tabCode: 'Code',
  failedPrefix: 'Failed',
  completedPrefix: 'Completed -',
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
  dailyCostChart: 'Daily Cost Trend',
  requests: 'requests',

  // Customers
  customersTitle: 'Customers',
  customersDesc: 'Manage your customers and end-users for Embedded Assistant.',
  addCustomer: 'Add customer',
  searchCustomerPlaceholder: 'Search by name, customer ID, region, or tenant',
  clearFilters: 'Clear Filters',
  customerColName: 'Name',
  customerColNfr: 'NFR',
  customerColRegion: 'Region',
  customerColCustomerId: 'Customer ID',
  customerColCreated: 'Created',
  customerColActions: 'Actions',
  customerIdSuffix: 'Customer ID Suffix',
  customerIdSuffixHelp: 'Alphanumeric, dash, or underscore (max 64 chars).',
  customerRegionUs: 'United States',
  customerRegionEu: 'European Union',
  customerRegionCn: 'China',
  customerNoData: 'No customers found',
  customerDeleteConfirm: 'Delete this customer? This cannot be undone.',
  customerDeleteSuccess: 'Customer deleted',
  customerCreateSuccess: 'Customer created',

  // Templates
  templatesTitle: 'Templates',
  templatesDesc: 'Manage templates and sections for generating structured documents.',
  templateBuilder: 'Template builder',
  viewTemplates: 'Templates',
  viewSections: 'Sections',
  searchTemplatesPlaceholder: 'Search',
  allTypes: 'All types',
  filter: 'Filter',
  builtinBadge: 'iCoDer template',
  scopeAllCustomers: 'All customers',
  noTemplates: 'No templates found',
  createTemplate: 'Create template',
  templateNamePlaceholder: 'e.g. Discharge Note',
  templateDescPlaceholder: 'Short description of this template',
  templateContentPlaceholder: 'Template content (prompt or structured template)',
  templateCategory: 'Category',
  templateLanguage: 'Language',
  templateCategoryInpatient: 'Inpatient',
  templateCategorySurgery: 'Surgery',
  templateCategoryOutpatient: 'Outpatient',
  templateCategoryEmergency: 'Emergency',
  templateCategoryConsultation: 'Consultation',
  templateCategoryCustom: 'Custom',
  templateLanguageZh: '中文',
  templateLanguageEn: 'English',

  // Tickets
  ticketsTitle: 'Tickets',
  ticketsDesc: 'Track issues and feature requests.',
  ticketsAll: 'All',
  ticketsCreatedByMe: 'Created by me',
  ticketsNewTicket: 'New ticket',
  ticketsSubject: 'Subject',
  ticketsDescription: 'Description',
  ticketsPriority: 'Priority',
  ticketsStatus: 'Status',
  ticketsColSubject: 'Subject',
  ticketsColStatus: 'Status',
  ticketsColPriority: 'Priority',
  ticketsColUpdated: 'Updated',
  ticketsColActions: 'Actions',
  ticketsNoData: 'No tickets found',
  ticketsDeleteConfirm: 'Delete this ticket? This cannot be undone.',
  ticketsStatusOpen: 'Open',
  ticketsStatusInProgress: 'In progress',
  ticketsStatusResolved: 'Resolved',
  ticketsStatusClosed: 'Closed',
  ticketsPriorityLow: 'Low',
  ticketsPriorityMedium: 'Medium',
  ticketsPriorityHigh: 'High',
  ticketsManagedElsewhere: 'Tickets managed through help desk',

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
  devQsNoRequestBody: 'GET request - no request body',
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

  // Phase 3-E - AI Studio Overview
  aiStudioOverviewTitle: 'AI Studio',
  aiStudioOverviewAgentsCard: 'AI Agents',
  aiStudioOverviewAgentsCardDesc: 'Manage, create, and discover Agents in the marketplace',
  aiStudioOverviewCodingCard: 'Medical Coding',
  aiStudioOverviewCodingCardDesc: 'ICD-10 / ICD-9-CM-3 intelligent coding',
  aiStudioOverviewRecentAgents: 'Recent Agents',
  aiStudioOverviewViewAll: 'View all',
  aiStudioOverviewRecentRuns: 'Recent Runs',

  // Phase 3-E - API Clients Page
  apiClientsLoadFailed: 'Load failed',
  apiClientsOAuthCreated: 'OAuth client created',
  apiClientsCopySecret: 'Copy the Client Secret - it will not be shown again.',
  apiClientsClientId: 'Client ID',
  apiClientsDone: 'Done',
  apiClientsSubtitle: 'Manage API keys and OAuth 2.0 client credentials',
  apiClientsCreateOAuth: 'Create OAuth client',
  apiClientsTabOAuth: 'OAuth 2.0 Clients',
  apiClientsTabKeys: 'API Keys',
  apiClientsCreateTitle: 'Create OAuth 2.0 client (Client Credentials)',
  apiClientsNamePlaceholder: 'Client name (e.g. Production SDK)',
  apiClientsDescPlaceholder: 'Description (optional)',
  apiClientsScopesPlaceholder: 'Scopes (space-separated)',
  apiClientsCreate: 'Create',
  apiClientsCancel: 'Cancel',
  apiClientsNoOAuth: 'No OAuth clients yet',
  apiClientsNoOAuthHint: 'Create a client to use client_credentials authentication',
  apiClientsNoKeys: 'No API keys yet',
  apiClientsConfirmRevokeTitle: 'Confirm revocation',
  apiClientsRevokeConfirm: 'Revoke OAuth client',
  apiClientsRevokeHint: 'Applications using this client will no longer authenticate.',
  apiClientsConfirmRevoke: 'Confirm revoke',
  apiClientsCreateFailed: 'Create failed',
  apiClientsDeleteFailed: 'Delete failed',

  // Phase 3-E - Release Notes
  releaseNotesTitle: 'Release Notes',
  releaseNotesSubtitle: 'iCoDer medical AI agent platform version change log.',
  releaseNotesApiPolicy: 'API change policy',

  // Phase 3-E - Reset Password
  resetPasswordTooShort: 'Password must be at least 8 characters',
  resetPasswordMismatch: 'Passwords do not match',
  resetPasswordNoToken: 'Missing reset token - please open the link from your email',
  resetPasswordSuccess: 'Password reset successful - please log in with the new password',
  resetPasswordFailed: 'Reset failed - token may have expired',
  resetPasswordTitle: 'Reset Password',
  resetPasswordSubtitle: 'Enter the new login password',
  resetPasswordBackToLogin: 'Back to login',
  resetPasswordNewPassword: 'New password',
  resetPasswordNewPlaceholder: 'At least 8 characters',
  resetPasswordConfirm: 'Confirm password',
  resetPasswordConfirmPlaceholder: 'Re-enter password',
  resetPasswordLoading: 'Resetting...',
  resetPasswordSubmit: 'Reset Password',

  // Phase 3-E - RunTrace viewer
  runTraceStepUserMessageReceived: '1. User message received',
  runTraceStepPlannerSelectedExperts: '2. Planner selected experts',
  runTraceStepToolsList: '3. Tools list',
  runTraceStepAuthResolved: '4. Auth resolved',
  runTraceStepScopeChecked: '5. Scope checked',
  runTraceStepToolsCall: '6. Tools call',
  runTraceStepExpertResponse: '7. Expert response',
  runTraceStepOutputGenerated: '8. Output generated',
  runTraceStepCompletion: '9. Completion',
  runTraceNoMetadata: 'No metadata',
  runTraceNoRequiredScopes: 'No required_scopes',
  runTraceDispatcherDetail: 'dispatcher detail',
  runTraceRawSafeMetadata: 'raw safe_metadata',
  runTraceSafeMetadata: 'safe_metadata',
  runTraceToolCount: 'tool_count',
  runTraceToolNames: 'tool_names',
  runTraceToolName: 'tool_name',
  runTraceHandlerRef: 'handler_ref',
  runTraceStage: 'stage',
  runTraceAuthType: 'auth_type',
  runTraceInProcessBypass: '⚠ in-process bypass',
  runTraceRedactedView: 'redacted_view',
  runTraceGrantedScopes: 'granted_scopes',
  runTraceNote: 'note',
  runTraceScopeDiff: 'scope diff (✓ matched / ✗ missing)',
  runTraceArguments: 'arguments',
  runTraceArgumentsKeysLabel: 'keys',
  runTraceChars: 'chars',
  runTraceValidated: 'validated ✓',
  runTraceResult: 'result',
  runTraceResultKeysLabel: 'keys',
  runTraceError: 'error',
  runTraceMcpErrorCode: 'mcp_error_code',
  runTraceTotalDispatch: 'total_dispatch',
  runTraceTotalDispatchBreakdown: '(auth+scope+resolve+handler)',
  runTraceTitle: 'RunTrace',
  runTraceRunId: 'run_id',
  runTraceSteps: 'steps',
  runTraceOk: 'ok',
  runTraceFailed: 'failed',
  runTraceTotal: 'total',
  runTraceIntro: '9-step Corti-parity timeline. Blue border = the 4 steps of the unified Dispatcher. Click any row to expand dispatcher detail + raw metadata.',
  runTraceAuthFilter: 'auth_resolved step only shows tool_name / auth_type / redacted_view / granted_scopes / note; all other metadata is hidden (defense in depth).',
  runTraceEmpty: 'Run completed but no trace events emitted yet.',
  runTraceEmptyHint: 'Run exists but timeline is empty. Possible causes: trace emit failure, DB write error, or the run took a non-instrumented path. Click retry below or return to Agent Hub to start again.',
  runTraceRetry: 'Retry load',
  runTraceNotFound: 'RunTrace not found',
  runTraceNotFoundHint: 'No trace events found for this run_id. The run may not have triggered any MCP/Orchestrator steps, or only executed on the A2A path (without going through the MCP server).',
  runTraceLoadFailed: 'Failed to load RunTrace',
  runTraceLoadError: 'Load failed',
  runTraceBack: 'Back',
  runTraceBackToHub: 'Back to Agent Hub',
  runTraceDispatcherHeader: 'Unified Tool Dispatcher',
  // Phase 3-D2.5 - Tool Dispatch Detail
  runTraceToolDispatchDetail: 'Tool Dispatch Detail',
  runTraceDispatchMode: 'Dispatch Mode',
  runTraceRoundIndex: 'Round',
  runTraceCaller: 'Caller',
  runTraceSchemaValidation: 'Schema Validation',
  runTracePhiRedaction: 'PHI Redaction',
  runTraceScopeCheck: 'Scope Check',
  runTraceHandlerStatus: 'Handler Status',
  runTraceResultShape: 'Result Shape',
  runTraceErrorStage: 'Error Stage',
  runTraceDurationMs: 'Duration',

  // Phase 3-E - Agent Chat
  agentChatGreetingMedicalCoding: 'Please provide ICD-10-CN diagnosis coding and ICD-9-CM-3 procedure coding suggestions for the following medical record text.',
  agentChatNotFoundToast: 'Agent not found - please clone from Hub first',
  agentChatLoadFailed: 'Failed to load Agent',
  agentChatDefaultGreeting: 'Please enter your request.',
  agentChatRunComplete: 'Run completed',
  agentChatRunFailed: 'Run failed',
  agentChatNotCloned: 'Agent not cloned',
  agentChatRedirecting: 'Redirecting to Agent Hub - please clone from there before entering the chat.',
  agentChatBack: 'Back to Agent Hub',
  agentChatInput: 'Input',
  agentChatInputPlaceholder: 'Paste medical record text or enter your request here…',
  agentChatCharCount: 'chars',
  agentChatRunning: 'Running…',
  agentChatRun: 'Run',
  agentChatRunFailedTitle: 'Run failed',
  agentChatResult: 'Run result',
  agentChatDuration: 'Duration',
  agentChatViewRunTrace: 'View RunTrace',
  agentChatViewRunTraceHint: 'View RunTrace 9-step timeline',
  agentChatRenderedTab: 'Rendered',
  agentChatJsonTab: 'JSON',
  // Phase 4-D - Corti naming catalog (en-US matches Corti verbatim)
  agentChatBreadcrumbAgents: 'Agents',
  agentChatTextareaPlaceholder: 'What can I help you with?',
  agentChatAddContext: 'Add context',
  agentChatConsumesCredits: 'Messaging an agent consumes credits',
  agentChatSettings: 'Settings',
  agentChatCode: 'Code',
  agentChatNameLabel: 'Name',
  agentChatSystemPrompt: 'System prompt',
  agentChatExperts: 'Experts',
  agentChatBrowseExpertLibrary: 'Browse Expert Library',
  agentChatCustomExperts: 'Custom experts',
  agentChatAddExpert: 'Add expert',
  agentChatPinnedMessageParts: 'Pinned message parts',
  agentChatSdkJavaScript: 'JavaScript (SDK)',
  agentChatSdkDotNet: '.NET (SDK)',
  agentChatSdkJsonConfig: 'JSON Config',
  agentChatCopy: 'Copy',
  agentChatApiClient: 'API Client',
  agentChatRunHistory: 'Recent runs',
  agentChatNewAgent: 'New Agent',
  agentChatUseAgent: 'Use Agent',
  agentChatCustomize: 'Customize',
  agentChatSaved: 'Saved',
  agentChatSaveFailed: 'Save failed',
  agentChatSaving: 'Saving…',
  agentChatNoExperts: 'No experts configured',
  agentChatNoPinnedParts: 'No pinned message parts',
  agentChatExpertLibraryStub: 'Expert library - coming soon (Phase 5)',
  agentChatAddExpertStub: 'Add expert - coming soon (Phase 5)',
  agentChatBadJson: 'Invalid JSON file',
  agentChatRemoveAttachment: 'Remove attachment',

  // Phase 3-E - Workbench Layout
  workbenchLayoutInput: 'Input',
  workbenchLayoutOutput: 'Output',
  workbenchLayoutSettings: 'Settings',
  workbenchLayoutEventInspector: 'Event Inspector',

  // Phase 3-E - Edit System Prompt Modal
  editSystemPromptTitle: 'Edit system prompt',
  editSystemPromptSubtitle: "Define the agent's role and style.",
  editSystemPromptTemplateHint: 'Use XML-style tags to structure sections. The <role> and <output_format> sections are required. Include an Example Output block within output_format for guidance.',
  editSystemPromptGenerating: 'Generating...',
  editSystemPromptAIGenerate: 'AI generate',
  editSystemPromptCancel: 'Cancel',
  editSystemPromptSave: 'Save',

  // Phase 3-E - Tool Selector
  toolSelectorLoading: 'Loading tools...',
  toolSelectorAvailableTools: 'Available Tools',
  toolSelectorSearchPlaceholder: 'Search tools...',
  toolSelectorTier1Toggle: 'Auto-inject accuracy guarantee tools (Tier 1)',
  toolSelectorCategorySafety: 'Safety',
  toolSelectorCategoryExtraction: 'Extraction',
  toolSelectorCategoryCoding: 'Coding',
  toolSelectorCategoryVerification: 'Verification',
  toolSelectorCategoryAnalysis: 'Analysis',
  toolSelectorCategoryReport: 'Report',
  toolSelectorAuto: 'Auto',
  toolSelectorId: 'ID',
  toolSelectorPreconditions: 'Preconditions',
  toolSelectorPostconditions: 'Postconditions',
  toolSelectorNoMatch: 'No tools found matching',
  toolSelectorSelected: 'tools selected',
  toolSelectorTier1: 'Tier 1',
  toolSelectorTier2: 'Tier 2',

  // Phase 3-E - Org Switcher
  orgSwitcherNoOrg: 'No Organization',
  orgSwitcherSelectOrg: 'Select Org',
  orgSwitcherOrganizations: 'Organizations',
  orgSwitcherNoOrgsFound: 'No organizations found',
  orgSwitcherCreateManage: '+ Create or manage organizations',

  // Phase 3-E - Event Inspector
  eventInspectorTitle: 'Event Inspector',
  eventInspectorCreditsConsumed: 'Credits consumed',
  eventInspectorNoEvents: 'No events recorded',

  // Phase 3-E - Error Boundary
  errorBoundaryLoadFailed: 'Load failed',
  errorBoundaryRetry: 'Retry',

  // Phase 3-E - TopK Chips
  topKChipsNoCandidates: 'No candidates',

  // Phase 3-E - Settings Code Tab
  settingsCodeTabSettings: 'Settings',
  settingsCodeTabCode: 'Code',
  settingsCodeTabTools: 'Tools',

  // Phase 3-E - Code Snippet
  codeSnippetJavaScript: 'JavaScript',
  codeSnippetJSON: 'JSON',
  codeSnippetJavaScriptSDK: 'JavaScript (SDK)',
  codeSnippetPythonSDK: 'Python (SDK)',
  codeSnippetCurl: 'curl',
  codeSnippetCSharpSDK: 'C# (.NET SDK)',
  codeSnippetJSONConfig: 'JSON Config',
  codeSnippetCopyCode: 'Copy code',

  // Phase 3-E - A2A Collaboration
  a2aCollaborationTitle: 'A2A Agent Collaboration',
  a2aCollaborationNAvailable: 'available',
  a2aCollaborationEmpty: 'No other Agents discovered (A2A must be enabled)',

  // Phase 3-E+ - Agent UI i18n extension
  agentCardChatUse: 'Chat / Use Agent',
  agentCardCustomize: 'Customize',
  agentCardCloning: 'Cloning…',
  agentCardProductionReadyFalse: 'production_ready=false',
  agentCardExpertsSuffix: 'experts',
  agentCardToolsSuffix: 'tools',
  agentEnable: 'Enable',
  agentDisable: 'Disable',
  agentUninstall: 'Uninstall',
  agentConfirmUninstall: 'Are you sure you want to uninstall?',
  agentEnabledToast: 'Enabled',
  agentDisabledToast: 'Disabled',
  agentUninstalledToast: 'Uninstalled',
  agentUninstallFailedToast: 'Uninstall failed',
  agentClonedToDraftToast: 'Cloned as draft',
  agentCloneFailedToast: 'Clone failed',
  agentClonedEnterChatToast: 'Cloned - entering chat',
  agentExistingCloneToast: 'Existing clone - entering chat',
  agentLoginRequiredToast: 'Please log in first',
  agentNotFoundToast: 'Agent not found',
  agentVersionBumpedToast: 'Version bumped',
  agentVersionBumpFailedToast: 'Version bump failed',
  agentSelectTemplate: 'Select template',
  agentSearchTemplatePlaceholder: 'Search templates...',
  agentNameLabel: 'Agent name',
  agentAdvancedSettings: 'Advanced settings',
  agentDescriptionLabel: 'Description',
  agentDescriptionPlaceholder: 'Describe the agent\'s function',
  agentCategoryLabel: 'Category',
  agentSystemPromptLabel: 'System prompt',
  agentSystemPromptPlaceholder: 'System prompt...',
  agentAiGenerate: 'AI generate',
  agentChatAgentFallback: 'Agent',
  agentChatAgentDescriptionPrefix: 'Agent: {desc}',
  agentChatSourceRef: 'source: {ref}',
  agentDetailTestTitle: 'Agent Test',
  agentDetailTestInputPlaceholder: 'Enter a test medical record to validate the Agent\'s coding result...',
  agentDetailRunTest: 'Run test',
  agentDetailRunning: 'Running...',
  agentDetailTestFailed: 'Test failed',
  agentDetailStatus: 'Status',
  agentDetailDuration: 'Duration',
  agentDetailSafety: 'Safety',
  agentDetailVerified: 'Verified',
  agentDetailPrimaryDx: 'Primary diagnosis',
  agentDetailSecondaryDx: 'Secondary diagnoses',
  agentDetailProcedures: 'Procedures',
  agentDetailIssues: 'Issues',
  agentDetailRuleChecks: 'Rule checks',
  agentDetailEvalTitle: 'Agent Evaluation',
  agentDetailEvaluating: 'Evaluating...',
  agentDetailRunGoldStandard: 'Run gold-standard evaluation',
  agentDetailDxAccuracy: 'Diagnosis accuracy',
  agentDetailProcAccuracy: 'Procedure accuracy',
  agentDetailExportCsv: 'Export CSV',
  agentDetailHistoryTrend: 'History trend',
  agentDetailBasicInfo: 'Basic info',
  agentDetailOrchestrationStrategy: 'Orchestration strategy',
  agentDetailRoutingStrategy: 'Routing strategy',
  agentDetailPermissionPreset: 'Permission preset (Deny-First)',
  agentDetailMaxRetriesLabel: 'Max retries: {n}',
  agentDetailConfidenceThresholdLabel: 'Confidence threshold: {n}',
  agentDetailConfidenceLoose: '0.0 (loose)',
  agentDetailConfidenceStrict: '1.0 (strict)',
  agentDetailEditCase: 'Edit case content',
  agentDetailEdit: 'Edit',
  agentDetailRemove: 'Remove',
  agentDetailDragSort: 'Drag to sort',
  agentDetailDragHint: 'Drag experts to adjust call priority',
  agentDetailExpertCountSuffix: 'count',
  agentDetailInstalledToast: 'Agent installed to Runtime',
  agentDetailInstallFailed: 'Install failed',
  agentDetailOperationFailed: 'Operation failed, please check permissions',
  agentDetailRoutingLlmPlan: 'LLM dynamic planning (recommended)',
  agentDetailRoutingToolNative: 'Tool-Native contract enforcement (new)',
  agentDetailRoutingFixedOrder: 'Fixed-order execution',
  agentDetailRoutingParallel: 'Parallel invocation',
  agentDetailRoutingSingleExpert: 'Single-expert direct',
  agentDetailRoutingLlmPlanDesc: 'AI analyzes the task, then dynamically selects experts and call order',
  agentDetailRoutingToolNativeDesc: 'LLM picks tools autonomously; Harness enforces contract validation per call',
  agentDetailRoutingFixedOrderDesc: 'Call bound experts in list order',
  agentDetailRoutingParallelDesc: 'Invoke all experts in parallel, aggregate results',
  agentDetailRoutingSingleExpertDesc: 'Only call the default expert, ignore other bindings',
  agentDetailPermissionMedicalCoding: 'Medical coding (recommended)',
  agentDetailPermissionCdiAudit: 'Clinical documentation audit (read-only)',
  agentDetailPermissionDrgAnalysis: 'DRG/DIP payment analysis',
  agentDetailPermissionRestrictive: 'Restrictive (deterministic tools only)',
  agentDetailPermissionFullAccess: 'Full access (dev/admin)',
  agentDetailPermissionMedicalCodingDesc: 'Standard coding pipeline - deterministic tools + limited LLM tool use',
  agentDetailPermissionCdiAuditDesc: 'Read-only analysis tools - coding assignment disallowed',
  agentDetailPermissionDrgAnalysisDesc: 'Coding + DRG analysis - for insurance audit',
  agentDetailPermissionRestrictiveDesc: 'Deterministic tools only (ICD index / evidence ranking etc.), maximum safety',
  agentDetailPermissionFullAccessDesc: 'All tools available - dev/admin only',
  agentDetailTestCaseLabel: 'Lumbar disc herniation',
  agentDetailTestCaseText: 'Female, 65. Lower back pain with left lower limb radiating pain for 3 months. Lumbar MRI shows L4/5 disc herniation compressing the left nerve root. Admission diagnosis: Lumbar disc herniation. PLIF surgery recommended.',
  agentDetailCapabilityQuestion: 'What can you do? Please describe your capabilities, specialties, and how you can help with medical coding, clinical documentation, and related medical tasks.',

  // Phase 3-E+ - Use case filter dropdown (Corti 5 enum keys)
  useCaseCodingRevenueCycle: 'Coding / Revenue cycle',
  useCaseClinicalEvidenceResearch: 'Clinical evidence research',
  useCasePointOfCare: 'Point of care',
  useCaseCareCoordination: 'Care coordination',
  useCaseChinaMedicalCompliance: 'China medical compliance',

  // Phase 3-E+ - AI Studio Overview (Corti 1:1 replica)
  aiStudioOverviewHeroEyebrow: 'AI Studio',
  aiStudioOverviewHeroTitle: 'Overview',
  aiStudioOverviewHeroTagline: 'Test and configure use cases directly from iCoDer Console',
  aiStudioOverviewExploreLabel: 'Explore',
  aiStudioOverviewExploreDesc: 'Build agents, generate live transcripts, clinical documents and more',
  aiStudioOverviewInspectLabel: 'Inspect',
  aiStudioOverviewInspectDesc: 'Debug with the events inspector and monitor live credit consumption',
  aiStudioOverviewConfigureLabel: 'Configure',
  aiStudioOverviewConfigureDesc: 'Fine tune settings for your needs and copy code directly into your application',
  aiStudioOverviewExploreCapabilities: 'Explore capabilities',
  aiStudioOverviewAgentsName: 'Agents',
  aiStudioOverviewAgentsDesc: 'Customize agents by adding experts, system prompts and context',
  aiStudioOverviewSttName: 'Speech to Text',
  aiStudioOverviewSttDesc: 'Stream live audio, configure custom commands and generate transcriptions',
  aiStudioOverviewTextGenName: 'Text Generation',
  aiStudioOverviewTextGenDesc: 'Turn transcriptions into structured clinical notes, customized for your needs',
  aiStudioOverviewEmbeddedName: 'Embedded Assistant',
  aiStudioOverviewEmbeddedDesc: 'Configure and test settings for an embedded ambient scribe experience',
  aiStudioOverviewFactExtractName: 'Fact Extraction',
  aiStudioOverviewFactExtractDesc: 'Extract structured clinical facts from medical transcriptions and notes',
  aiStudioOverviewCodingName: 'Medical Coding',
  aiStudioOverviewCodingDesc: 'Convert unstructured clinical text into structured medical codes',
  aiStudioOverviewExploreCta: 'Explore',
  aiStudioOverviewDocsCta: 'Docs',
  aiStudioOverviewDiveIntoCode: 'Ready to dive into code and make your first request?',
  aiStudioOverviewDevQuickstart: 'Developer quickstart',
  aiStudioOverviewFooterDocs: 'DOCUMENTATION',
  aiStudioOverviewFooterAuth: 'Authentication',
  aiStudioOverviewFooterGuides: 'Guides',
  aiStudioOverviewFooterApiRef: 'API Reference',
  aiStudioOverviewFooterSdks: 'SDKS AND TOOLS',
  aiStudioOverviewFooterJsSdk: 'Javascript SDK',
  aiStudioOverviewFooterPostman: 'Postman',
  aiStudioOverviewFooterAiCoding: 'AI coding tools',
  aiStudioOverviewFooterHelp: 'NEED HELP?',
  aiStudioOverviewFooterChat: 'Chat with us',
  aiStudioOverviewFooterTicket: 'Open a ticket',
};

export const locales: Record<Locale, LocaleDict> = {
  'zh-CN': zhCN,
  'en-US': enUS,
};
