import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHandoffQueue } from "../api";
import type { HumanHandoff } from "../types";

const STATUS_ZH: Record<string, string> = {
  queued: "排队中",
  waiting: "等待接手",
  assigned: "已接单",
  in_progress: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

const POLL_INTERVAL_MS = 10_000;

interface Props {
  tenantId: string;
  onCountChange?: (count: number) => void;
  onItemsChange?: (items: HumanHandoff[]) => void;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
  refreshToken?: number;
}

/**
 * 待处理会话队列。
 *
 * 每 10 秒轮询一次，新到会话高亮并触发角标提醒。
 * 点击一行会把它交给右侧的处理面板；坐席操作完成后通过 refreshToken 立即刷新。
 * 生产环境应该换成服务端推送（WebSocket / SSE），轮询只是为了演示链路。
 */
export default function HandoffQueue({
  tenantId,
  onCountChange,
  onItemsChange,
  onSelect,
  selectedId,
  refreshToken = 0,
}: Props) {
  const [items, setItems] = useState<HumanHandoff[]>([]);
  const [freshIds, setFreshIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const known = useRef<Set<string>>(new Set());

  const load = useCallback(
    async (manual = false) => {
      if (manual) setLoading(true);
      try {
        const next = await fetchHandoffQueue(tenantId);
        const incoming = next.filter((item) => !known.current.has(item.id));
        known.current = new Set(next.map((item) => item.id));
        setItems(next);
        onItemsChange?.(next);
        setError(null);
        onCountChange?.(next.length);
        if (incoming.length > 0) {
          setFreshIds(new Set(incoming.map((item) => item.id)));
          window.setTimeout(() => setFreshIds(new Set()), 6000);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (manual) setLoading(false);
      }
    },
    [onCountChange, onItemsChange, tenantId],
  );

  useEffect(() => {
    known.current = new Set();
    void load();
    const timer = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  // 坐席操作完成后立即刷新，不必等下一个轮询周期。
  useEffect(() => {
    if (refreshToken > 0) void load();
    // 只在显式刷新令牌变化时触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  return (
    <div>
      <div className="rail-heading">
        待处理会话
        <span className="count">{items.length}</span>
        <button
          className="btn"
          style={{ marginLeft: "auto" }}
          onClick={() => void load(true)}
          disabled={loading}
        >
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>

      {error ? (
        <p className="empty-note">读取失败：{error}</p>
      ) : items.length === 0 ? (
        <p className="empty-note">
          当前没有转人工会话。机器人处理中的会话不会出现在这里；每 10 秒自动刷新。
        </p>
      ) : (
        items.map((item) => (
          <button
            type="button"
            className={`queue-row ${freshIds.has(item.id) ? "fresh" : ""} ${selectedId === item.id ? "selected" : ""}`}
            key={item.id}
            onClick={() => onSelect?.(item.id)}
          >
            <div>
              <div className="queue-reason">{item.reason || "（未填写转接原因）"}</div>
              <div className="queue-id">
                {item.user_id} · {item.queue_name} · {item.id.slice(0, 8)}
              </div>
            </div>
            <div className="queue-side">
              <span className={item.priority === "urgent" ? "badge brick" : "badge"}>
                {item.priority}
              </span>
              <span className="badge petrol">{STATUS_ZH[item.status] ?? item.status}</span>
            </div>
          </button>
        ))
      )}
    </div>
  );
}
