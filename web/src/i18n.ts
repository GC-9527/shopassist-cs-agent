export type Lang = "zh" | "en";

export interface CustomerCopy {
  title: string;
  subtitle: string;
  online: string;
  newChat: string;
  greeting: string;
  greetingSub: string;
  orders: string;
  noOrders: string;
  loadError: string;
  orderLabel: string;
  status: Record<string, string>;
  track: string;
  returnItem: string;
  reportIssue: string;
  otherTopics: string;
  returnPolicy: string;
  refundTiming: string;
  talkToHuman: string;
  placeholder: string;
  fallbackProduct: string;
  assistantName: string;
  connected: string;
  handedOff: string;
  endChat: string;
  callback: string;
  reset: string;
  opening: string;
  orderPickerTitle: string;
  promptTrack: (orderId: string) => string;
  promptReturn: (orderId: string, product: string) => string;
  promptIssue: (orderId: string, product: string) => string;
  promptReturnTopic: string;
  promptRefundTopic: string;
  promptHuman: string;
  promptConsultOrder: (orderId: string) => string;
  promptPrice: (orderId: string) => string;
  attachmentOnly: string;
  uploadFailed: string;
  csatTitle: string;
  csatSub: string;
  csatCommentPlaceholder: string;
  csatSubmit: string;
  csatThanks: string;
  csatFailed: string;
  csatScoreLabels: [string, string, string, string, string];
  csatTagLabels: Record<"fast" | "clear" | "friendly" | "resolved" | "needs_work", string>;
  sessionWaiting: (position: number | null) => string;
  sessionHuman: (agent: string | null) => string;
  sessionReview: string;
  sessionClosed: string;
}

/**
 * C 端文案。中文版放在第一位：演示给中文面试官看，英文版对应出海场景。
 * 两种语言会同时切换界面文案、租户和知识库，互不混用。
 */
export const CUSTOMER_COPY: Record<Lang, CustomerCopy> = {
  zh: {
    title: "客户服务中心",
    subtitle: "充电与音频产品 · 订单、退换货与售后",
    online: "在线 · 通常立即回复",
    newChat: "新会话",
    greeting: "你好，需要什么帮助？",
    greetingSub: "可以先从你的订单开始，也可以直接描述问题。",
    orders: "你的订单",
    noOrders: "当前账号名下没有可展示的订单。",
    loadError: "订单读取失败：",
    orderLabel: "订单",
    status: {
      paid: "待发货",
      shipped: "已发货",
      delivered: "已签收",
      cancelled: "已取消",
      refunded: "已退款",
    },
    track: "查询物流",
    returnItem: "申请退货",
    reportIssue: "商品有问题",
    otherTopics: "其他问题",
    returnPolicy: "退换货政策",
    refundTiming: "退款到账时间",
    talkToHuman: "联系人工客服",
    placeholder: "描述你的问题…",
    fallbackProduct: "商品",
    assistantName: "智能客服助手",
    connected: "已接入在线客服",
    handedOff: "已为您转接人工客服",
    endChat: "结束",
    callback: "我想预约电话回拨",
    opening:
      "您好！我是智能客服助手。已经同步了您的订单信息，可以直接帮您查物流、申请退货，或转接人工客服。",
    orderPickerTitle: "请点选你要处理的订单：",
    reset: "重置会话",
    promptTrack: (orderId) => `帮我查一下订单 ${orderId} 的物流到哪了`,
    promptReturn: (orderId, product) => `订单 ${orderId} 的${product}我想申请退货退款`,
    promptIssue: (orderId, product) =>
      `订单 ${orderId} 的${product}出现质量问题，要怎么申请售后？`,
    promptReturnTopic: "七天无理由退货的条件是什么？",
    promptRefundTopic: "退款一般多久能到账？",
    promptHuman: "我要转人工客服",
    promptConsultOrder: (orderId) => `我需要咨询订单 ${orderId}。`,
    promptPrice: (orderId) => `订单 ${orderId} 能申请价保退差价吗？`,
    attachmentOnly: "请查看我上传的图片。",
    uploadFailed: "图片上传失败：",
    csatTitle: "这次服务您满意吗？",
    csatSub: "评价会直接进入客服质量看板，帮我们改进。",
    csatCommentPlaceholder: "还有什么想告诉我们的？（选填）",
    csatSubmit: "提交评价",
    csatThanks: "感谢评价，我们会继续改进。",
    csatFailed: "评价提交失败：",
    csatScoreLabels: ["很不满意", "不满意", "一般", "满意", "非常满意"],
    csatTagLabels: {
      fast: "响应很快",
      clear: "说明清楚",
      friendly: "态度友好",
      resolved: "问题解决了",
      needs_work: "还需要改进",
    },
    sessionWaiting: (position) =>
      position && position > 1
        ? `正在为您转接人工客服 · 前面还有 ${position - 1} 位`
        : "正在为您转接人工客服 · 即将接入",
    sessionHuman: (agent) => (agent ? `人工坐席 ${agent} 已接入` : "人工坐席已接入"),
    sessionReview: "坐席已提交处理结果，请确认",
    sessionClosed: "会话已结束",
  },
  en: {
    title: "Support Center",
    subtitle: "Charging & audio products · orders, returns, warranty",
    online: "Online · usually replies right away",
    newChat: "New chat",
    greeting: "Hi, how can we help?",
    greetingSub: "Start from an order below, or just describe the problem.",
    orders: "Your orders",
    noOrders: "No orders found for this account.",
    loadError: "Could not load your orders: ",
    orderLabel: "Order",
    status: {
      paid: "Processing",
      shipped: "Shipped",
      delivered: "Delivered",
      cancelled: "Cancelled",
      refunded: "Refunded",
    },
    track: "Track order",
    returnItem: "Start a return",
    reportIssue: "Report an issue",
    otherTopics: "Other topics",
    returnPolicy: "Return policy",
    refundTiming: "Refund timing",
    talkToHuman: "Talk to a person",
    placeholder: "Describe your issue…",
    fallbackProduct: "this item",
    assistantName: "Support Assistant",
    connected: "Connected to support",
    handedOff: "Transferring you to a specialist",
    endChat: "End",
    callback: "Please schedule a callback for me",
    opening:
      "Hi! I'm your support assistant. I can check your order status, start a return, or hand you to a human agent.",
    orderPickerTitle: "Select the order you need help with:",
    reset: "Reset conversation",
    promptTrack: (orderId) => `Where is my order ${orderId}?`,
    promptReturn: (orderId, product) => `I want to return ${product} from order ${orderId}.`,
    promptIssue: (orderId, product) =>
      `There is a quality issue with ${product} from order ${orderId}. How do I start a warranty claim?`,
    promptReturnTopic: "What is your return policy?",
    promptRefundTopic: "How long do refunds take?",
    promptHuman: "I want to talk to a human",
    promptConsultOrder: (orderId) => `I need help with order ${orderId}.`,
    promptPrice: (orderId) => `Can I get a price adjustment on order ${orderId}?`,
    attachmentOnly: "Please check the photos I uploaded.",
    uploadFailed: "Upload failed: ",
    csatTitle: "How did we do?",
    csatSub: "Your rating goes straight to our service quality board.",
    csatCommentPlaceholder: "Anything else you'd like to tell us? (optional)",
    csatSubmit: "Submit rating",
    csatThanks: "Thanks for the feedback — it helps us improve.",
    csatFailed: "Could not submit rating: ",
    csatScoreLabels: ["Very poor", "Poor", "Okay", "Good", "Excellent"],
    csatTagLabels: {
      fast: "Fast reply",
      clear: "Clear answers",
      friendly: "Friendly",
      resolved: "Issue resolved",
      needs_work: "Needs work",
    },
    sessionWaiting: (position) =>
      position && position > 1
        ? `Connecting you to a specialist · ${position - 1} ahead of you`
        : "Connecting you to a specialist · almost there",
    sessionHuman: (agent) => (agent ? `Specialist ${agent} joined the chat` : "A specialist joined the chat"),
    sessionReview: "Your specialist submitted a resolution for review",
    sessionClosed: "Chat ended",
  },
};

export const SHELL_COPY = {
  zh: { support: "客服窗口", console: "运营后台", demoAccount: "演示账号", ready: "服务就绪", down: "服务未就绪", checking: "检查中" },
  en: { support: "Support", console: "Console", demoAccount: "Demo account", ready: "service ready", down: "service unavailable", checking: "checking" },
} as const;

export const MAX_MESSAGE_LENGTH = 1000;

/** 把毫秒时间戳格式化成 HH:MM，用于气泡时间。 */
export function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** 工作台（左栏 + 聊天气泡）文案。 */
export const WORKBENCH_COPY = {
  zh: {
    engine: "客服引擎在线",
    badge: "AI",
    human: "转人工",
    contextOrder: "当前关联订单",
    switchOrder: "切换订单",
    skillsTitle: "快捷服务",
    send: "发送",
    chatHint: "点击左侧订单，或用下面的快捷按钮，也可以直接描述问题。",
    skills: [
      { title: "查询物流", sub: "实时轨迹与派送节点", topic: "logistics" },
      { title: "申请退货", sub: "30 天售后期内可提交", topic: "return" },
      { title: "商品有问题", sub: "质量检测与换新", topic: "defect" },
      { title: "转人工客服", sub: "坐席接手，无需重复描述", topic: "human" },
    ],
    pills: ["查询物流", "申请退货", "转人工"],
  },
  en: {
    engine: "Support engine online",
    badge: "AI",
    human: "Human agent",
    contextOrder: "Linked order",
    switchOrder: "Switch",
    skillsTitle: "Quick actions",
    send: "Send",
    chatHint: "Pick an order on the left, use a shortcut below, or just describe the issue.",
    skills: [
      { title: "Track order", sub: "Live status and delivery", topic: "logistics" },
      { title: "Start a return", sub: "Within the 30-day window", topic: "return" },
      { title: "Report an issue", sub: "Quality check and replacement", topic: "defect" },
      { title: "Talk to a person", sub: "Agent takes over with context", topic: "human" },
    ],
    pills: ["Track order", "Start a return", "Human agent"],
  },
} as const;

/** 客服工作台外框文案：顶栏、二级导航、Agent 头部、订单卡。 */
export const SHOP_COPY = {
  zh: {
    deliverTo: "配送至",
    searchScope: "客服搜索",
    searchPlaceholder: "输入订单问题，如：包裹到哪了、我要退货",
    modeToggle: "切换右下角悬浮窗模式",
    workspace: "ShopAssist 智能客服工作台",
    nav: ["国际直邮追踪", "极速先退免寄回", "30天自动价保", "1分钟极速电话回拨"],
    engine: "ShopAssist Agent 引擎实时在线",
    agentTitle: "ShopAssist 智能客服 Agent",
    humanAgent: "人工坐席",
    agentBadge: "AI 驱动",
    agentSubtitle: "已授权访问您的订单、物流与售后工具",
    callBack: "电话回拨",
    transfer: "转人工",
    end: "结束对话",
    contextPrefix: "当前锁定订单",
    reset: "重置会话",
    banner: (time: string) => `今天 ${time} · 端到端加密客服会话`,
    resumed: (time: string) => `已恢复上次会话 · 上次活动 ${time}`,
    pickerTitle: "请点击需要处理的近期订单：",
    pickerTag: "专属通道",
    selectOrder: "选择此单",
    send: "发送",
    composerPlaceholder: "向 ShopAssist 智能客服提问，例如：退差价、极速退款、包裹到哪了…",
    pillTrack: "物流催件",
    pillRefund: "破损极速先退",
    pillPrice: "退差价",
    pillHuman: "转接人工客服",
    chatEnded: "会话已结束",
  },
  en: {
    deliverTo: "Deliver to",
    searchScope: "Support",
    searchPlaceholder: "Ask about an order, e.g. where is my parcel",
    modeToggle: "Floating window",
    workspace: "ShopAssist Support Workspace",
    nav: ["Track international parcel", "Instant refund", "30-day price protection", "Call back in 1 minute"],
    engine: "ShopAssist Agent engine online",
    agentTitle: "ShopAssist Support Agent",
    humanAgent: "Specialist",
    agentBadge: "AI",
    agentSubtitle: "Authorised to access your orders, shipping and support tools",
    callBack: "Call back",
    transfer: "Human agent",
    end: "End chat",
    contextPrefix: "Locked order",
    reset: "Reset chat",
    banner: (time: string) => `Today ${time} · end-to-end encrypted support session`,
    resumed: (time: string) => `Resumed your previous chat · last active ${time}`,
    pickerTitle: "Select the order you need help with:",
    pickerTag: "Priority lane",
    selectOrder: "Select",
    send: "Send",
    composerPlaceholder: "Ask ShopAssist anything, e.g. refund, price match, where is my parcel…",
    pillTrack: "Chase delivery",
    pillRefund: "Instant refund",
    pillPrice: "Price match",
    pillHuman: "Human agent",
    chatEnded: "Chat ended",
  },
} as const;
