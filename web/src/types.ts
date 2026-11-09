export interface KnowledgeChunk {
  id: string;
  source: string;
  title: string;
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  tool_call_id: string;
  name: string;
  ok: boolean;
  payload: Record<string, unknown>;
}

export interface TraceStep {
  stage: string;
  detail: string;
  metadata: Record<string, unknown>;
}

export interface PlanStep {
  step_id: string;
  title: string;
  action_type: string;
  tool_name: string | null;
  requires_confirmation: boolean;
  status?: string;
}

export interface AgentPlan {
  plan_id: string;
  steps: PlanStep[];
  max_steps: number;
}

export interface PendingConfirmation {
  id: string;
  tenant_id: string;
  user_id: string;
  action_type: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: string;
  risk_level: string;
  confirmation_prompt: string;
  expired: boolean;
  result: Record<string, unknown>;
}

export interface OrderSummary {
  order_id: string;
  status: string;
  product: string | null;
  amount: number | null;
  logistics_company: string | null;
  tracking_number: string | null;
  destination: string | null;
}

export interface HumanHandoff {
  id: string;
  status: string;
  tenant_id: string;
  user_id: string;
  conversation_id: string;
  queue_name: string;
  priority: string;
  reason: string;
  assigned_agent_id?: string | null;
  resolution_code?: string | null;
  resolution_summary?: string | null;
  next_mode?: string | null;
  requested_at: string;
  updated_at?: string;
  version: number;
}

export interface ConfirmationDecision {
  confirmation_id: string;
  status: string;
  message: string;
  answer: string;
  graph_status: string;
  result: Record<string, unknown>;
  conversation_id?: string | null;
  thread_id?: string | null;
  next_confirmation: PendingConfirmation | null;
  tool_results?: ToolResult[];
  trace?: TraceStep[];
  plan?: AgentPlan | null;
}

export interface AnswerEvent {
  conversation_id: string;
  thread_id: string | null;
  run_id: string | null;
  status: string;
  answer: string;
}

export interface RunEvidence {
  status: string;
  knowledge: KnowledgeChunk[];
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
  trace: TraceStep[];
  plan: AgentPlan | null;
  pending: PendingConfirmation | null;
  handoff: HumanHandoff | null;
}

export interface MessageAttachment {
  id: string;
  filename: string;
  content_type: string;
  url: string;
  size?: number;
}

export interface CsatView {
  id: string;
  conversation_id: string;
  score: number;
  comment: string | null;
  tags: string[];
  created_at: string | null;
}

export interface CsatComment {
  conversation_id: string;
  user_id: string;
  score: number;
  comment: string | null;
  tags: string[];
  created_at: string | null;
}

export interface CsatSummary {
  tenant_id: string;
  days: number;
  total: number;
  average: number | null;
  positive_rate: number | null;
  distribution: Record<string, number>;
  tag_counts: Record<string, number>;
  recent: CsatComment[];
}

export interface HandoffState {
  id: string;
  status: "waiting_assignment" | "assigned" | "in_service" | "resolution_submitted" | "resolved" | "cancelled";
  queue_name: string;
  priority: string;
  reason: string;
  assigned_agent_id: string | null;
  queue_position: number | null;
  resolution_summary: string | null;
  updated_at: string | null;
}

export interface ConversationSession {
  conversation_id: string;
  status: string;
  service_mode: "bot" | "waiting_human" | "human" | "resolution_review" | string;
  handoff: HandoffState | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: string;
  createdAt: number;
  attachments?: MessageAttachment[];
  // 人工通道的消息要换署名，不能标成"智能客服 Agent"。
  channel?: "bot" | "human";
  agentId?: string;
}

export interface SseEvent {
  event: string;
  data: unknown;
}
