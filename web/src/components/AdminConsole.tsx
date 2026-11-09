import { useEffect, useState } from "react";
import CsatPanel from "./CsatPanel";
import EvidenceRail from "./EvidenceRail";
import HandoffQueue from "./HandoffQueue";
import HandoffWorkbench from "./HandoffWorkbench";
import type { useChatSession } from "../useChatSession";
import { statusLabel } from "../useChatSession";
import type { HumanHandoff } from "../types";

interface Props {
  chat: ReturnType<typeof useChatSession>;
  tenantId: string;
  agentId: string;
  roles: string[];
}

type Tab = "queue" | "debug" | "csat";

/**
 * 坐席 / 运营后台。
 *
 * 这里才是看内部信息的地方：转人工队列（轮询提醒）、引用与工具回执、执行轨迹。
 * C 端窗口不展示这些。
 */
export default function AdminConsole({ chat, tenantId, agentId, roles }: Props) {
  const [tab, setTab] = useState<Tab>("queue");
  const [pendingCount, setPendingCount] = useState(0);
  const [draft, setDraft] = useState("");
  const [queueItems, setQueueItems] = useState<HumanHandoff[]>([]);
  const [selectedHandoffId, setSelectedHandoffId] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { messages, evidence, busy, error, send, setError } = chat;

  const selectedHandoff =
    queueItems.find((item) => item.id === selectedHandoffId) ?? null;

  useEffect(() => {
    // 处理完成后该任务会离开队列，右侧面板随之收起到调试对话。
    if (selectedHandoffId && !queueItems.some((item) => item.id === selectedHandoffId)) {
      setSelectedHandoffId(null);
    }
  }, [queueItems, selectedHandoffId]);

  const submit = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void send(text);
  };

  // 处理面板和满意度看板不需要右侧证据轨，主区域占满即可。
  const twoColumn = tab === "csat" || (tab === "queue" && selectedHandoff !== null);

  return (
    <div className={`admin-shell ${twoColumn ? "csat-mode" : ""}`}>
      <aside className="admin-side">
        <div className="rail-tabs">
          <button
            className="rail-tab"
            aria-selected={tab === "queue"}
            onClick={() => setTab("queue")}
          >
            待处理会话
            {pendingCount > 0 ? <span className="tab-badge">{pendingCount}</span> : null}
          </button>
          <button
            className="rail-tab"
            aria-selected={tab === "debug"}
            onClick={() => setTab("debug")}
          >
            调试对话
          </button>
          <button
            className="rail-tab"
            aria-selected={tab === "csat"}
            onClick={() => setTab("csat")}
          >
            满意度
          </button>
        </div>
        <div className="rail-body">
          {tab === "queue" ? (
            <HandoffQueue
              tenantId={tenantId}
              onCountChange={setPendingCount}
              onItemsChange={setQueueItems}
              onSelect={setSelectedHandoffId}
              selectedId={selectedHandoffId}
              refreshToken={refreshToken}
            />
          ) : null}
          {tab === "debug" ? (
            <p className="empty-note">
              在右侧向机器人提问，可以同时看到它引用了哪些知识、调用了哪些工具。
              这个视图只给坐席和运营使用。
            </p>
          ) : null}
          {tab === "csat" ? (
            <p className="empty-note">
              客户结束会话后会在对话框里评分。这里按租户和时间窗口汇总，
              评价只读——后台不能改写客户的评分。
            </p>
          ) : null}
        </div>
      </aside>

      <section className="admin-main">
        {tab === "queue" && selectedHandoff ? (
          <HandoffWorkbench
            item={selectedHandoff}
            tenantId={tenantId}
            agentId={agentId}
            roles={roles}
            onChanged={() => setRefreshToken((value) => value + 1)}
            onBack={() => setSelectedHandoffId(null)}
          />
        ) : tab === "csat" ? (
          <CsatPanel tenantId={tenantId} />
        ) : (
          <>
        <div className="admin-toolbar">
          <span className="admin-title">会话调试</span>
          {evidence.status ? (
            <span className="badge">{statusLabel(evidence.status)}</span>
          ) : null}
          <button
            className="btn"
            style={{ marginLeft: "auto" }}
            onClick={() => {
              chat.reset();
              setError(null);
            }}
          >
            新会话
          </button>
        </div>

        <div className="admin-transcript">
          {messages.length === 0 ? (
            <p className="empty-note">
              用机器人跑一遍用户会问的问题，右边是它拿到的证据。
            </p>
          ) : (
            messages.map((message) => (
              <article className={`turn ${message.role}`} key={message.id}>
                <div className="turn-who">{message.role === "user" ? "用户" : "机器人"}</div>
                <div>
                  <div className="turn-body">{message.text}</div>
                  {message.status ? (
                    <div className="turn-status">
                      <span className="badge">{statusLabel(message.status)}</span>
                    </div>
                  ) : null}
                </div>
              </article>
            ))
          )}
          {busy && messages.length > 0 ? (
            <article className="turn assistant">
              <div className="turn-who">机器人</div>
              <div className="turn-body" style={{ color: "var(--ink-3)" }}>
                正在处理…
              </div>
            </article>
          ) : null}
        </div>

        <div className="admin-composer">
          <textarea
            value={draft}
            placeholder="以当前身份向机器人提问，Enter 发送"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
          />
          <button className="send" onClick={submit} disabled={busy || !draft.trim()}>
            {busy ? "处理中" : "发送"}
          </button>
        </div>
        {error ? <div className="error-line">{error}</div> : null}
          </>
        )}
      </section>

      {twoColumn ? null : (
      <aside className="rail">
        <div className="rail-tabs">
          <button className="rail-tab" aria-selected>
            证据
          </button>
        </div>
        <div className="rail-body">
          <EvidenceRail evidence={evidence} busy={busy} onDecide={chat.decide} />
        </div>
      </aside>
      )}
    </div>
  );
}
