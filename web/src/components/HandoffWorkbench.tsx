import { useCallback, useEffect, useRef, useState } from "react";
import {
  assignHandoff,
  confirmHumanResolution,
  fetchConversationMessages,
  sendHumanMessage,
  submitHumanResolution,
} from "../api";
import type { ConversationMessage } from "../api";
import type { HumanHandoff } from "../types";

const STATUS_ZH: Record<string, string> = {
  waiting_assignment: "等待接入",
  assigned: "已接单",
  in_service: "处理中",
  resolution_submitted: "待确认",
  resolved: "已解决",
  cancelled: "已取消",
};

const RESOLUTION_CODES: { value: string; label: string }[] = [
  { value: "replacement_created", label: "换货 / 换新" },
  { value: "refund_approved", label: "退款 / 退货" },
  { value: "information_provided", label: "已告知处理方式" },
  { value: "escalated", label: "已升级到专员" },
  { value: "other", label: "其他" },
];

const POLL_INTERVAL_MS = 4000;

/** 后端时间带时区，转成本地 HH:MM。 */
function formatStamp(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

interface Props {
  item: HumanHandoff;
  tenantId: string;
  agentId: string;
  roles: string[];
  onChanged: () => void;
  onBack: () => void;
}

/**
 * 坐席处理面板。
 *
 * 把转人工的完整操作放进 React 后台：接入、回复、提交处理结果；
 * 运营角色还可以确认结果，让会话回到机器人或直接结束。
 */
export default function HandoffWorkbench({
  item,
  tenantId,
  agentId,
  roles,
  onChanged,
  onBack,
}: Props) {
  const isOperator = roles.some((role) => role === "operator" || role === "admin");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [reply, setReply] = useState("");
  const [resolutionCode, setResolutionCode] = useState(RESOLUTION_CODES[0].value);
  const [summary, setSummary] = useState("");
  const [nextMode, setNextMode] = useState<"resume_bot" | "close_conversation">("resume_bot");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadMessages = useCallback(async () => {
    try {
      const history = await fetchConversationMessages(
        item.conversation_id,
        tenantId,
        item.user_id,
      );
      setMessages(history);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [item.conversation_id, item.user_id, tenantId]);

  useEffect(() => {
    setError(null);
    setReply("");
    setSummary("");
    void loadMessages();
    const timer = window.setInterval(() => void loadMessages(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadMessages]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await loadMessages();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const canAssign = item.status === "waiting_assignment";
  const canWork =
    (item.status === "assigned" || item.status === "in_service") &&
    (isOperator || item.assigned_agent_id === agentId);
  const canConfirm = item.status === "resolution_submitted" && isOperator;
  const actorId = item.assigned_agent_id ?? agentId;

  return (
    <div className="handoff-workbench">
      <div className="handoff-toolbar">
        <button className="btn" onClick={onBack}>
          ← 返回调试对话
        </button>
        <span className="handoff-title">人工会话 · {item.user_id}</span>
        <span className="badge petrol">{STATUS_ZH[item.status] ?? item.status}</span>
        <span className={item.priority === "urgent" ? "badge brick" : "badge"}>
          {item.priority}
        </span>
      </div>

      <div className="handoff-meta">
        <div>
          <span>转接原因</span>
          <strong>{item.reason || "（未填写）"}</strong>
        </div>
        <div>
          <span>队列</span>
          <strong>{item.queue_name}</strong>
        </div>
        <div>
          <span>坐席</span>
          <strong>{item.assigned_agent_id ?? "未分配"}</strong>
        </div>
        <div>
          <span>会话</span>
          <strong>{item.conversation_id.slice(0, 8)}</strong>
        </div>
      </div>

      <div className="handoff-thread" ref={scrollRef}>
        {messages.length === 0 ? (
          <p className="empty-note">还没有可展示的消息。</p>
        ) : (
          messages
            .filter((message) => message.role === "user" || message.role === "assistant")
            .map((message) => (
              <div className={`handoff-msg ${message.role}`} key={message.id}>
                <div className="handoff-msg-who">
                  {message.role === "user"
                    ? "客户"
                    : message.metadata?.channel === "human_support"
                      ? `坐席 ${String(message.metadata?.agent_id ?? "")}`.trim()
                      : "机器人"}
                  {message.created_at ? ` · ${formatStamp(message.created_at)}` : ""}
                </div>
                <div className="handoff-msg-body">{message.content}</div>
              </div>
            ))
        )}
      </div>

      {error ? <div className="error-line">{error}</div> : null}

      {canAssign ? (
        <div className="handoff-action">
          <p className="handoff-hint">该会话还在排队，接入后客户会看到"人工坐席已接入"。</p>
          <button
            className="send"
            disabled={busy}
            onClick={() =>
              void run(() =>
                assignHandoff(item.id, tenantId, agentId, item.version),
              )
            }
          >
            {busy ? "接入中…" : "接入会话"}
          </button>
        </div>
      ) : null}

      {canWork ? (
        <>
          <div className="handoff-composer">
            <textarea
              value={reply}
              placeholder="以人工坐席身份回复客户，Enter 发送"
              onChange={(event) => setReply(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  const text = reply.trim();
                  if (!text || busy) return;
                  void run(async () => {
                    await sendHumanMessage(item.id, tenantId, actorId, text);
                    setReply("");
                  });
                }
              }}
            />
            <button
              className="send"
              disabled={busy || !reply.trim()}
              onClick={() =>
                void run(async () => {
                  await sendHumanMessage(item.id, tenantId, actorId, reply.trim());
                  setReply("");
                })
              }
            >
              {busy ? "发送中" : "回复"}
            </button>
          </div>

          <div className="handoff-resolution">
            <div className="handoff-resolution-title">提交处理结果</div>
            <div className="handoff-resolution-row">
              <label>
                处理方式
                <select
                  value={resolutionCode}
                  onChange={(event) => setResolutionCode(event.target.value)}
                >
                  {RESOLUTION_CODES.map((code) => (
                    <option key={code.value} value={code.value}>
                      {code.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                处理完成后
                <select
                  value={nextMode}
                  onChange={(event) =>
                    setNextMode(event.target.value as "resume_bot" | "close_conversation")
                  }
                >
                  <option value="resume_bot">转回机器人</option>
                  <option value="close_conversation">结束会话</option>
                </select>
              </label>
            </div>
            <textarea
              value={summary}
              placeholder="给客户看的处理结果摘要，例如：已创建换货申请，48 小时内寄出新品。"
              onChange={(event) => setSummary(event.target.value)}
            />
            <button
              className="btn"
              disabled={busy || !summary.trim()}
              onClick={() =>
                void run(() =>
                  submitHumanResolution(item.id, tenantId, actorId, {
                    resolution_code: resolutionCode,
                    summary: summary.trim(),
                    next_mode: nextMode,
                  }),
                )
              }
            >
              提交处理结果
            </button>
          </div>
        </>
      ) : null}

      {canConfirm ? (
        <div className="handoff-action">
          <div className="handoff-resolution-title">待确认的处理结果</div>
          <p className="handoff-summary">{item.resolution_summary ?? "（无摘要）"}</p>
          <button
            className="send"
            disabled={busy}
            onClick={() =>
              void run(() =>
                confirmHumanResolution(item.id, tenantId, agentId, item.version),
              )
            }
          >
            {busy
              ? "确认中…"
              : item.next_mode === "close_conversation"
                ? "确认并结束会话"
                : "确认并恢复 Bot"}
          </button>
        </div>
      ) : null}

      {item.status === "resolution_submitted" && !isOperator ? (
        <p className="handoff-hint">
          处理结果已提交，等待运营确认。换成运营账号（u004）即可确认。
        </p>
      ) : null}
    </div>
  );
}
