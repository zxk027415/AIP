const fs = require('fs');

function applyReplacements(filePath, replacements) {
  let content = fs.readFileSync(filePath, 'utf8');
  let count = 0;
  for (const [oldStr, newStr] of replacements) {
    if (content.includes(oldStr)) {
      content = content.split(oldStr).join(newStr);
      count++;
    }
  }
  fs.writeFileSync(filePath, content);
  console.log(`${filePath}: ${count} replacements applied`);
}

// ============ ABTestPage.tsx ============
applyReplacements('AIP-service/frontend/src/pages/ABTestPage.tsx', [
  // Move QUICK_COMMANDS inside component - replace the const outside
  ["const QUICK_COMMANDS: QuickCommand[] = [\n  { label: '分析所有进行中测试'", "const QUICK_COMMANDS_DATA: QuickCommand[] = [\n  { label: '分析所有进行中测试'"],
  // message calls
  ["message.warning('请输入分析指令')", "message.warning(t('abTest.enterPrompt'))"],
  ["message.success('AI 分析完成')", "message.success(t('abTest.aiAnalysisDone'))"],
  ["message.success('A/B 测试创建成功')", "message.success(t('abTest.testCreated'))"],
  ["message.loading('正在暂停测试...', 1)", "message.loading(t('abTest.pausingTest'), 1)"],
  ["message.success('测试已暂停')", "message.success(t('abTest.testPaused'))"],
  ["message.success('测试已结束')", "message.success(t('abTest.testEnded'))"],
  // Modal.confirm
  ["title: '确认结束测试'", "title: t('abTest.confirmEndTest')"],
  ["content: '确定要提前结束此 A/B 测试吗？'", "content: t('abTest.confirmEndTestContent')"],
  // Table columns
  ["title: '测试名称'", "title: t('abTest.testName')"],
  ["title: '场景',", "title: t('abTest.scenario'),"],
  ["title: '流量分配'", "title: t('abTest.trafficSplit')"],
  ["title: '开始时间'", "title: t('abTest.startTime')"],
  // Result column
  ["title: '结果'", "title: t('abTest.result')"],
  // Status column - be careful with context
  ["title: '状态',\n      dataIndex: 'status',\n      key: 'status',", "title: t('abTest.status'),\n      dataIndex: 'status',\n      key: 'status',"],
  // Action column
  ["title: '操作',\n      key: 'action',", "title: t('abTest.action'),\n      key: 'action',"],
  // Tag text
  ["<Tag>待定</Tag>", "<Tag>{t('abTest.pending')}</Tag>"],
  ["<Tag color=\"blue\" icon={<TrophyOutlined />}>A 胜出</Tag>", "<Tag color=\"blue\" icon={<TrophyOutlined />}>{t('abTest.aWinsResult')}</Tag>"],
  ["<Tag color=\"green\" icon={<TrophyOutlined />}>B 胜出</Tag>", "<Tag color=\"green\" icon={<TrophyOutlined />}>{t('abTest.bWinsResult')}</Tag>"],
  ["<Tag>无差异</Tag>", "<Tag>{t('abTest.noDifference')}</Tag>"],
  // Buttons
  [">详情</Button>", ">{t('abTest.detail')}</Button>"],
  [" danger onClick={() => handleStopTest()}>结束</Button>", " danger onClick={() => handleStopTest()}>{t('abTest.end')}</Button>"],
  // Tab labels
  ["label: '进行中测试'", "label: t('abTest.runningTests')"],
  ["label: '测试结果'", "label: t('abTest.testResults')"],
  ["label: '历史记录'", "label: t('abTest.historyRecords')"],
  // Card titles
  ["title=\"实时指标趋势\"", "title={t('abTest.realtimeTrend')}"],
  ["title=\"样本量累积\"", "title={t('abTest.sampleAccumulation')}"],
  ["title=\"指标对比\"", "title={t('abTest.metricsCompare')}"],
  ["title=\"统计显著性\"", "title={t('abTest.statisticalSignificance')}"],
  ["title=\"AI 决策建议\"", "title={t('abTest.aiDecisionAdvice')}"],
  // Statistic titles
  ["title=\"置信水平\"", "title={t('abTest.confidenceLevel')}"],
  ["title=\"效应量 (Cohen's d)\"", "title={t('abTest.effectSize')}"],
  ["title=\"统计功效\"", "title={t('abTest.statisticalPower')}"],
  ["title=\"总测试数\"", "title={t('abTest.totalTests')}"],
  ["title=\"进行中\"", "title={t('abTest.running')}"],
  ["title=\"已完成\"", "title={t('abTest.completed')}"],
  ["title=\"A 胜出\"", "title={t('abTest.aWins')}"],
  ["title=\"B 胜出\"", "title={t('abTest.bWins')}"],
  // AI section
  ["<Text strong>AI 分析入口</Text>", "<Text strong>{t('abTest.aiAnalysisEntry')}</Text>"],
  ["<Text type=\"secondary\">输入自然语言指令，AI 将自动分析 A/B 测试</Text>", "<Text type=\"secondary\">{t('abTest.aiAnalysisDesc')}</Text>"],
  ["placeholder=\"请描述您的 A/B 测试需求，例如：分析当前运行的负荷预测 A/B 测试结果\"", "placeholder={t('abTest.placeholder')}"],
  // Send button
  [">\n              发送\n            </Button>", ">\n              {t('abTest.send')}\n            </Button>"],
  // Management card
  ["title=\"A/B 测试管理\"", "title={t('abTest.management')}"],
  // Select options
  ["{ value: 'all', label: '全部状态' }", "{ value: 'all', label: t('abTest.allStatus') }"],
  ["{ value: 'running', label: '进行中' }", "{ value: 'running', label: t('abTest.statusRunning') }"],
  ["{ value: 'completed', label: '已完成' }", "{ value: 'completed', label: t('abTest.statusCompleted') }"],
  ["{ value: 'paused', label: '已暂停' }", "{ value: 'paused', label: t('abTest.statusPaused') }"],
  // Create button
  [">\n              创建测试\n            </Button>", ">\n              {t('abTest.createTest')}\n            </Button>"],
  // Advice text
  ["<Text strong>建议：采纳模型 B (v2.1)</Text>", "<Text strong>{t('abTest.adviceAdoptB')}</Text>"],
  ["模型 B 在精度上提升 2.3%，延迟降低 12.5%，错误率降低 40%。\n                统计显著性达到 95% 置信水平 (p=0.023)，效应量为 0.85（大效应）。\n                建议全量切换到模型 B。", "{t('abTest.adviceDetail')}"],
  // Buttons
  [">采纳 B 模型</Button>", ">{t('abTest.adoptBModel')}</Button>"],
  [">延长测试</Button>", ">{t('abTest.extendTest')}</Button>"],
  // Modal
  ["title=\"创建 A/B 测试\"", "title={t('abTest.createABTest')}"],
  // Form items
  ["label=\"测试名称\"", "label={t('abTest.testNameLabel')}"],
  ["placeholder=\"例如：光伏预测 v2.1 vs v2.0\"", "placeholder={t('abTest.testNamePlaceholder')}"],
  ["label=\"控制组模型 (A)\"", "label={t('abTest.controlModel')}"],
  ["label=\"实验组模型 (B)\"", "label={t('abTest.experimentModel')}"],
  ["placeholder=\"选择模型\"", "placeholder={t('abTest.selectModel')}"],
  ["label=\"流量分配 (A 的比例)\"", "label={t('abTest.trafficSplitLabel')}"],
  ["label=\"测试时长\"", "label={t('abTest.testDuration')}"],
  ["addonAfter=\"天\"", "addonAfter={t('abTest.days')}"],
  // Drawer
  ["selectedTest?.test_name || '测试详情'", "selectedTest?.test_name || t('abTest.testDetail')"],
  ["title=\"基本信息\"", "title={t('abTest.basicInfo')}"],
  ["title=\"快捷操作\"", "title={t('abTest.quickActions')}"],
  // Drawer labels
  ["<Text type=\"secondary\">测试ID：</Text>", "<Text type=\"secondary\">{t('abTest.testId')}</Text>"],
  ["<Text type=\"secondary\">场景：</Text>", "<Text type=\"secondary\">{t('abTest.scenarioLabel')}</Text>"],
  ["<Text type=\"secondary\">模型 A：</Text>", "<Text type=\"secondary\">{t('abTest.modelA')}</Text>"],
  ["<Text type=\"secondary\">模型 B：</Text>", "<Text type=\"secondary\">{t('abTest.modelB')}</Text>"],
  ["<Text type=\"secondary\">流量分配：</Text>", "<Text type=\"secondary\">{t('abTest.trafficLabel')}</Text>"],
  ["<Text type=\"secondary\">状态：</Text>", "<Text type=\"secondary\">{t('abTest.statusLabel')}</Text>"],
  // Drawer buttons
  [">查看详细报告</Button>", ">{t('abTest.viewDetailReport')}</Button>"],
  [">暂停测试</Button>", ">{t('abTest.pauseTest')}</Button>"],
  [">结束测试</Button>", ">{t('abTest.endTest')}</Button>"],
]);

console.log('ABTestPage done');
