import { useCallback, useRef, useState } from "react";
import { decideConfirmation, streamChat } from "./api";
import type { ConversationMessage, DemoSession } from "./api";
import type { MessageAttachment } from "./types";
import type {
  AgentPlan,
  AnswerEvent,
  ChatMessage,
  KnowledgeChunk,
  PendingConfirmation,
  RunEvidence,
  ToolCall,
  ToolResult,
  TraceStep,
} from "./types";

export const EMPTY_EVIDENCE: RunEvidence = {
  status: "",
  knowledge: [],
  toolCalls: [],
  toolResults: [],
  trace: [],
  plan: null,
  pending: null,
  handoff: null,
};

const STATUS_ZH: Record<string, string> = {
  completed: "已完成",
  needs_clarification: "需要澄清",
  waiting_confirmation: "等待确认",
  waiting_human: "等待人工",
  human_active: "人工处理中",
};

export function statusLabel(status: string): string {
  return STATUS_ZH[status] ?? status;
}

/** 一轮对话的完整状态机：发送、接收 SSE、处理确认。C 端和后台调试共用。 */
export function useChatSession(session: DemoSession | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [evidence, setEvidence] = useState<RunEvidence>(EMPTY_EVIDENCE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ids.current 给请求用；state 供 UI 观察"当前是哪个会话"，驱动状态轮询。
  const [conversationId, setConversationId] = useState<string | null>(null);
  const ids = useRef<{ conversationId?: string; threadId?: string }>({});

  const patch = useCallback((update: Partial<RunEvidence>) => {
    setEvidence((current) => ({ ...current, ...update }));
  }, []);

  const send = useCallback(
    async (question: string, attachments: MessageAttachment[] = []) => {
      const text = question.trim();
      if (!text || busy || !session) return;
      setBusy(true);
      setError(null);
      setEvidence(EMPTY_EVIDENCE);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "user", text, createdAt: Date.now(), attachments },
      ]);

      try {
        await streamChat(
          {
            tenant_id: session.tenant_id,
            user_id: session.user_id,
            question: text,
            conversation_id: ids.current.conversationId,
            thread_id: ids.current.threadId,
            attachments,
          },
          ({ event, data }) => {
            switch (event) {
              case "trace":
                setEvidence((current) => ({
                  ...current,
                  trace: [...current.trace, data as TraceStep],
                }));
                break;
              case "plan":
                patch({ plan: data as AgentPlan });
                break;
              case "knowledge":
                setEvidence((current) => ({
                  ...current,
                  knowledge: [...current.knowledge, data as KnowledgeChunk],
                }));
                break;
              case "tool_call":
                setEvidence((current) => ({
                  ...current,
                  toolCalls: [...current.toolCalls, data as ToolCall],
                }));
                break;
              case "tool_result":
                setEvidence((current) => ({
                  ...current,
                  toolResults: [...current.toolResults, data as ToolResult],
                }));
                break;
              case "confirmation_required":
                patch({ pending: data as PendingConfirmation });
                break;
              case "answer": {
                const answer = data as AnswerEvent;
                ids.current = {
                  conversationId: answer.conversation_id,
                  threadId: answer.thread_id ?? undefined,
                };
                setConversationId(answer.conversation_id);
                patch({ status: answer.status });
                setMessages((current) => [
                  ...current,
                  {
                    id: crypto.randomUUID(),
                    role: "assistant",
                    text: answer.answer,
                    status: answer.status,
                    createdAt: Date.now(),
                  },
                ]);
                break;
              }
              case "done": {
                const done = data as { status: string };
                patch({ status: done.status });
                break;
              }
            }
          },
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [busy, patch, session],
  );

  const decide = useCallback(
    async (action: "approve" | "reject") => {
      const pending = evidence.pending;
      if (!pending || busy || !session) return;
      setBusy(true);
      setError(null);
      try {
        const decision = await decideConfirmation(
          session.tenant_id,
          session.user_id,
          pending.id,
          action,
        );
        const receipts = (decision.tool_results ?? []).map(
          (item) => `${item.name} ${item.ok ? "成功" : "失败"}`,
        );
        const answer =
          decision.answer && decision.answer !== pending.confirmation_prompt
            ? decision.answer
            : decision.message;
        const text = receipts.length ? `${answer}\n\n工具回执：${receipts.join("；")}` : answer;
        patch({
          pending: decision.next_confirmation ?? null,
          status: decision.graph_status || decision.status,
          toolResults: decision.tool_results?.length ? decision.tool_results : evidence.toolResults,
          trace: decision.trace?.length ? decision.trace : evidence.trace,
          plan: decision.plan ?? evidence.plan,
        });
        setMessages((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text:
              text ||
              (action === "approve"
                ? "已批准，但没有返回可展示的答复。"
                : "已拒绝该操作，未产生任何业务副作用。"),
            status: decision.graph_status || decision.status,
            createdAt: Date.now(),
          },
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [
      busy,
      evidence.pending,
      evidence.plan,
      evidence.toolResults,
      evidence.trace,
      patch,
      session,
    ],
  );

  /** 用服务端历史恢复一段会话：接上原 conversation 与 thread，消息按时间回放。 */
  const hydrate = useCallback(
    (
      conversationId: string,
      threadId: string | null,
      history: {
        id: string;
        role: string;
        content: string;
        created_at: string | null;
        metadata?: { attachments?: MessageAttachment[] } & Record<string, unknown>;
      }[],
    ) => {
      ids.current = { conversationId, threadId: threadId ?? undefined };
      setConversationId(conversationId);
      setEvidence(EMPTY_EVIDENCE);
      setError(null);
      setMessages(
        history
          .filter((item) => item.role === "user" || item.role === "assistant")
          .map((item) => ({
            id: item.id,
            role: item.role as "user" | "assistant",
            text: item.content,
            createdAt: item.created_at ? Date.parse(item.created_at) : Date.now(),
            attachments: item.metadata?.attachments ?? [],
            channel:
              item.metadata?.channel === "human_support" ? ("human" as const) : undefined,
            agentId:
              typeof item.metadata?.agent_id === "string" ? item.metadata.agent_id : undefined,
          })),
      );
    },
    [],
  );

  /** 轮询补进来的坐席消息：只取人工通道、且本地还没有的条目。 */
  const appendHistory = useCallback((history: ConversationMessage[]) => {
    setMessages((current) => {
      const known = new Set(current.map((item) => item.id));
      const extra = history
        .filter(
          (item) =>
            item.role === "assistant" &&
            item.metadata?.channel === "human_support" &&
            !known.has(item.id),
        )
        .map((item) => ({
          id: item.id,
          role: "assistant" as const,
          text: item.content,
          createdAt: item.created_at ? Date.parse(item.created_at) : Date.now(),
          attachments: item.metadata?.attachments ?? [],
          channel: "human" as const,
          agentId:
            typeof item.metadata?.agent_id === "string" ? item.metadata.agent_id : undefined,
        }));
      return extra.length ? [...current, ...extra] : current;
    });
  }, []);

  const getConversationId = useCallback(() => ids.current.conversationId, []);

  const reset = useCallback(() => {
    ids.current = {};
    setConversationId(null);
    setMessages([]);
    setEvidence(EMPTY_EVIDENCE);
    setError(null);
  }, []);

  return {
    messages,
    evidence,
    busy,
    error,
    send,
    decide,
    reset,
    hydrate,
    appendHistory,
    getConversationId,
    setError,
    conversationId,
  };
}
