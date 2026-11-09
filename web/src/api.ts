import type {
  ConfirmationDecision,
  ConversationSession,
  CsatSummary,
  CsatView,
  HumanHandoff,
  MessageAttachment,
  OrderSummary,
  SseEvent,
} from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

function withAuth(extra: Record<string, string> = {}): Record<string, string> {
  return authToken ? { ...extra, Authorization: `Bearer ${authToken}` } : extra;
}

export interface DemoSession {
  access_token: string;
  token_type: string;
  expires_in: number;
  tenant_id: string;
  user_id: string;
  roles: string[];
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body === "string") return body;
    if (body?.message) return body.message;
    if (body?.detail) {
      return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export async function loginDemo(userId: string, tenantId: string): Promise<DemoSession> {
  const response = await fetch("/api/v1/auth/demo-token", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ user_id: userId, tenant_id: tenantId }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function streamChat(
  body: {
    tenant_id: string;
    user_id: string;
    question: string;
    conversation_id?: string;
    thread_id?: string;
    attachments?: MessageAttachment[];
  },
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: withAuth(jsonHeaders),
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(await readError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const name = /^event:\s*(.+)$/m.exec(frame)?.[1]?.trim();
      const payload = /^data:\s*(.+)$/m.exec(frame)?.[1];
      if (name && payload) {
        onEvent({ event: name, data: JSON.parse(payload) });
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function decideConfirmation(
  tenantId: string,
  userId: string,
  confirmationId: string,
  decision: "approve" | "reject",
  reason?: string,
): Promise<ConfirmationDecision> {
  const response = await fetch(`/api/v1/confirmations/${confirmationId}/${decision}`, {
    method: "POST",
    headers: withAuth(jsonHeaders),
    body: JSON.stringify({ tenant_id: tenantId, user_id: userId, reason }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchMyOrders(tenantId: string): Promise<OrderSummary[]> {
  const url = `/api/v1/orders?tenant_id=${encodeURIComponent(tenantId)}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export interface ConversationSummary {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string;
  status: string;
  service_mode: string;
  thread_id: string | null;
  updated_at: string | null;
}

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  created_at: string | null;
  metadata?: { attachments?: MessageAttachment[] } & Record<string, unknown>;
}

export async function fetchLatestConversation(
  tenantId: string,
  userId: string,
): Promise<ConversationSummary | null> {
  const url = `/api/v1/conversations/latest?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchConversationMessages(
  conversationId: string,
  tenantId: string,
  userId: string,
): Promise<ConversationMessage[]> {
  const url = `/api/v1/conversations/${conversationId}/messages?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchConversationSession(
  conversationId: string,
  tenantId: string,
  userId: string,
): Promise<ConversationSession> {
  const url = `/api/v1/conversations/${conversationId}/session?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function closeConversation(
  conversationId: string,
  tenantId: string,
  userId: string,
): Promise<void> {
  const url = `/api/v1/conversations/${conversationId}/close?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`;
  const response = await fetch(url, { method: "POST", headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
}

export async function submitCsat(
  conversationId: string,
  tenantId: string,
  userId: string,
  payload: { score: number; comment?: string; tags?: string[] },
): Promise<CsatView> {
  const url = `/api/v1/conversations/${conversationId}/csat?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { ...jsonHeaders, ...withAuth() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchCsatSummary(
  tenantId: string,
  days = 30,
): Promise<CsatSummary> {
  const url = `/api/v1/csat/summary?tenant_id=${encodeURIComponent(tenantId)}&days=${days}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function uploadAttachment(
  tenantId: string,
  file: File,
): Promise<MessageAttachment> {
  const form = new FormData();
  form.append("file", file);
  const url = `/api/v1/uploads?tenant_id=${encodeURIComponent(tenantId)}`;
  const response = await fetch(url, { method: "POST", headers: withAuth(), body: form });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

const attachmentUrls = new Map<string, string>();

/** 图片接口需要鉴权，<img> 带不了 header，这里取 blob 再转成本地 object URL。 */
export async function attachmentObjectUrl(attachmentId: string): Promise<string> {
  const cached = attachmentUrls.get(attachmentId);
  if (cached) return cached;
  const response = await fetch(`/api/v1/uploads/${attachmentId}`, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  attachmentUrls.set(attachmentId, objectUrl);
  return objectUrl;
}

export async function fetchHandoffQueue(tenantId: string): Promise<HumanHandoff[]> {
  const url = `/api/v1/human-support/queue?tenant_id=${encodeURIComponent(tenantId)}`;
  const response = await fetch(url, { headers: withAuth() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

async function handoffAction(
  handoffId: string,
  action: string,
  body: Record<string, unknown>,
): Promise<HumanHandoff> {
  const response = await fetch(
    `/api/v1/human-support/${handoffId}/${action}`,
    {
      method: "POST",
      headers: { ...jsonHeaders, ...withAuth() },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export function assignHandoff(
  handoffId: string,
  tenantId: string,
  agentId: string,
  expectedVersion: number,
): Promise<HumanHandoff> {
  return handoffAction(handoffId, "assign", {
    tenant_id: tenantId,
    agent_id: agentId,
    expected_version: expectedVersion,
  });
}

export function sendHumanMessage(
  handoffId: string,
  tenantId: string,
  agentId: string,
  content: string,
): Promise<HumanHandoff> {
  return handoffAction(handoffId, "messages", {
    tenant_id: tenantId,
    agent_id: agentId,
    content,
  });
}

export function submitHumanResolution(
  handoffId: string,
  tenantId: string,
  agentId: string,
  payload: {
    resolution_code: string;
    summary: string;
    next_mode: "resume_bot" | "close_conversation";
  },
): Promise<HumanHandoff> {
  return handoffAction(handoffId, "resolution", {
    tenant_id: tenantId,
    agent_id: agentId,
    ...payload,
  });
}

export function confirmHumanResolution(
  handoffId: string,
  tenantId: string,
  operatorId: string,
  expectedVersion: number,
): Promise<HumanHandoff> {
  return handoffAction(handoffId, "resolution/confirm", {
    tenant_id: tenantId,
    operator_id: operatorId,
    expected_version: expectedVersion,
  });
}

export async function fetchHealth(): Promise<{ ready: boolean; detail: Record<string, unknown> }> {
  const response = await fetch("/health/ready");
  const detail = await response.json();
  return { ready: detail.status === "ok", detail };
}
