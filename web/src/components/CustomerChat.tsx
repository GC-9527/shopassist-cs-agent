import { useEffect, useRef, useState } from "react";
import ConfirmationCard from "./ConfirmationCard";
import {
  attachmentObjectUrl,
  closeConversation,
  fetchConversationMessages,
  fetchConversationSession,
  fetchLatestConversation,
  fetchMyOrders,
  submitCsat,
  uploadAttachment,
} from "../api";
import { useChatSession } from "../useChatSession";
import { statusLabel } from "../useChatSession";
import { CUSTOMER_COPY, MAX_MESSAGE_LENGTH, SHOP_COPY, formatTime } from "../i18n";
import type { Lang } from "../i18n";
import type { ConversationSession, MessageAttachment, OrderSummary } from "../types";

interface Props {
  chat: ReturnType<typeof useChatSession>;
  loginError: string | null;
  tenantId: string;
  userId: string;
  lang: Lang;
  account: string;
  accounts: readonly { id: string; label: string }[];
  onAccountChange: (value: string) => void;
  onLangChange: (value: Lang) => void;
}

const STATUS_TONE: Record<string, string> = {
  paid: "amber",
  shipped: "blue",
  delivered: "green",
  cancelled: "grey",
  refunded: "grey",
};

function productIcon(product: string | null, lang: Lang): string {
  const text = (product ?? "").toLowerCase();
  if (text.includes("耳机") || text.includes("earbud") || text.includes("headphone")) {
    return "🎧";
  }
  if (text.includes("kindle") || text.includes("阅读")) return "📖";
  return lang === "zh" ? "📦" : "📦";
}

/**
 * C 端客服工作台。
 *
 * 结构：顶栏（搜索 / 悬浮窗）→ 二级导航 → 客服卡片
 * （Agent 头部 / 锁定订单条 / 加密会话横幅 / 开场消息与订单选择卡 / 消息流 / 快捷胶囊 / 输入区）。
 * 内部证据（引用打分、工具回执）只出现在运营后台。
 */
export default function CustomerChat({
  chat,
  loginError,
  tenantId,
  userId,
  lang,
  account,
  accounts,
  onAccountChange,
  onLangChange,
}: Props) {
  const { messages, evidence, busy, error, send, decide, setError } = chat;
  const t = CUSTOMER_COPY[lang];
  const s = SHOP_COPY[lang];
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [activeOrderId, setActiveOrderId] = useState<string | null>(null);
  const [floating, setFloating] = useState(false);
  const [resumedAt, setResumedAt] = useState<string | null>(null);
  const [pendingFiles, setPendingFiles] = useState<MessageAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [thumbUrls, setThumbUrls] = useState<Record<string, string>>({});
  // 结束会话后出现的满意度卡片：只针对刚刚结束的那条会话。
  const [csatTarget, setCsatTarget] = useState<string | null>(null);
  const [csatScore, setCsatScore] = useState(0);
  const [csatComment, setCsatComment] = useState("");
  const [csatTags, setCsatTags] = useState<string[]>([]);
  const [csatBusy, setCsatBusy] = useState(false);
  const [csatDone, setCsatDone] = useState(false);
  const [csatError, setCsatError] = useState<string | null>(null);
  // 服务端会话状态：谁在处理（bot/人工）、排队位置、是否已结束。
  const [session, setSession] = useState<ConversationSession | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const openedAt = useRef(Date.now()).current;
  const resumedKey = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setOrders([]);
    setActiveOrderId(null);
    fetchMyOrders(tenantId)
      .then((next) => {
        if (cancelled) return;
        setOrders(next);
        setActiveOrderId(next[0]?.order_id ?? null);
      })
      .catch(() => {
        // 订单读取失败时对话框照常可用。
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, userId]);

  // 打开页面时接上最近一段会话（受后端恢复窗口限制）。
  useEffect(() => {
    if (!tenantId || !userId) return;
    const key = `${tenantId}:${userId}`;
    if (resumedKey.current === key) return;
    resumedKey.current = key;
    let cancelled = false;
    fetchLatestConversation(tenantId, userId)
      .then(async (conversation) => {
        if (!conversation || cancelled) return;
        const history = await fetchConversationMessages(conversation.id, tenantId, userId);
        if (cancelled) return;
        chat.hydrate(conversation.id, conversation.thread_id, history);
        setResumedAt(conversation.updated_at);
      })
      .catch(() => {
        // 恢复失败就当作新会话，不影响正常提问。
      });
    return () => {
      cancelled = true;
    };
    // chat 每次渲染都是新对象，用 resumedKey 防重复
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, userId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  const activeOrder = orders.find((order) => order.order_id === activeOrderId) ?? orders[0] ?? null;

  const submit = () => {
    const text = draft.trim();
    if (sessionClosed) return;
    if (!text && pendingFiles.length === 0) return;
    const attachments = pendingFiles;
    setDraft("");
    setPendingFiles([]);
    void send(text || t.attachmentOnly, attachments);
  };

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const uploaded: MessageAttachment[] = [];
      for (const file of Array.from(files)) {
        uploaded.push(await uploadAttachment(tenantId, file));
      }
      setPendingFiles((current) => [...current, ...uploaded]);
    } catch (err) {
      setError(t.uploadFailed + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const search = () => {
    const text = query.trim();
    if (!text) return;
    setQuery("");
    void send(text);
  };

  const promptFor = (topic: "logistics" | "return" | "defect" | "price"): string => {
    if (!activeOrder) return t.promptReturnTopic;
    const name = activeOrder.product || t.fallbackProduct;
    if (topic === "logistics") return t.promptTrack(activeOrder.order_id);
    if (topic === "return") return t.promptReturn(activeOrder.order_id, name);
    if (topic === "price") return t.promptPrice(activeOrder.order_id);
    return t.promptIssue(activeOrder.order_id, name);
  };

  const pickOrder = (order: OrderSummary) => {
    setActiveOrderId(order.order_id);
    void send(t.promptConsultOrder(order.order_id));
  };

  const endChat = async () => {
    const conversationId = chat.getConversationId();
    let closed = false;
    if (conversationId) {
      try {
        await closeConversation(conversationId, tenantId, userId);
        closed = true;
      } catch {
        // 关闭失败不阻塞本地重置
      }
    }
    chat.reset();
    setResumedAt(null);
    // 只有真的关掉了服务端会话，才让客户评价；否则后端也会以 409 拒绝。
    if (conversationId && closed) {
      setCsatTarget(conversationId);
      setCsatScore(0);
      setCsatComment("");
      setCsatTags([]);
      setCsatDone(false);
      setCsatError(null);
    } else {
      setCsatTarget(null);
    }
  };

  // 客户重新开口才进入新一轮会话；轮询补进来的坐席消息不算（末条是 assistant）。
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (last?.role === "user") {
      setCsatTarget(null);
      setCsatDone(false);
    }
    // 只在消息数量变化时触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  // 轮询会话状态：人工接管、排队位置、结束等变化不用等客户再发一条消息。
  useEffect(() => {
    const conversationId = chat.conversationId;
    if (!conversationId) {
      setSession(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const state = await fetchConversationSession(conversationId, tenantId, userId);
        if (cancelled) return;
        setSession(state);
        // 人工通道的消息不走 SSE，只有轮询能拿到。
        if (state.service_mode !== "bot" || state.status === "closed") {
          const history = await fetchConversationMessages(conversationId, tenantId, userId);
          if (!cancelled) chat.appendHistory(history);
        }
        if (state.status === "closed") {
          setCsatTarget((current) => current ?? conversationId);
        }
      } catch {
        // 状态轮询失败不打断正在进行的对话。
      } finally {
        if (!cancelled) timer = window.setTimeout(tick, 4000);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
    // chat 每次渲染都是新对象，只跟踪会话 ID 与稳定的 appendHistory
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.conversationId, tenantId, userId]);

  const toggleCsatTag = (tag: string) => {
    setCsatTags((current) =>
      current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag].slice(0, 5),
    );
  };

  const submitRating = async () => {
    if (!csatTarget || csatScore === 0) return;
    setCsatBusy(true);
    setCsatError(null);
    try {
      await submitCsat(csatTarget, tenantId, userId, {
        score: csatScore,
        comment: csatComment.trim() || undefined,
        tags: csatTags,
      });
      setCsatDone(true);
    } catch (err) {
      setCsatError(t.csatFailed + (err instanceof Error ? err.message : String(err)));
    } finally {
      setCsatBusy(false);
    }
  };

  // 图片接口要鉴权，统一换成 object URL 再渲染。
  const allAttachments = [
    ...pendingFiles,
    ...messages.flatMap((message) => message.attachments ?? []),
  ];
  useEffect(() => {
    let cancelled = false;
    const missing = allAttachments.filter((item) => !thumbUrls[item.id]);
    if (missing.length === 0) return;
    missing.forEach((item) => {
      attachmentObjectUrl(item.id)
        .then((url) => {
          if (!cancelled) setThumbUrls((current) => ({ ...current, [item.id]: url }));
        })
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
    // 缩略图按 id 缓存，缺一个补一个
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allAttachments.length, thumbUrls]);

  const handedOff =
    evidence.status === "waiting_human" || evidence.status.startsWith("human");
  // 已结束的会话不能再发消息；人工模式下快捷胶囊也不该再触发 Bot 动作。
  const sessionClosed = session?.status === "closed";
  const humanMode = session !== null && session.service_mode !== "bot";
  const destination = activeOrder?.destination ?? (lang === "zh" ? "上海市 静安区 200040" : "Seattle, WA");

  return (
    <div className={`shop ${floating ? "floating" : ""}`}>
      <header className="shop-top">
        <div className="shop-brand">
          ShopAssist
          <span className="shop-brand-tag">Support</span>
        </div>

        <div className="shop-locate">
          <span className="shop-locate-pin">◉</span>
          <div>
            <div className="shop-locate-label">{s.deliverTo}</div>
            <div className="shop-locate-value">{destination}</div>
          </div>
        </div>

        <div className="shop-search">
          <span className="shop-search-scope">{s.searchScope}</span>
          <input
            value={query}
            placeholder={s.searchPlaceholder}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                search();
              }
            }}
          />
          <button className="shop-search-btn" onClick={search} aria-label="search">
            ⌕
          </button>
        </div>

        <div className="shop-top-actions">
          <div className="shop-lang">
            <button
              type="button"
              className={lang === "zh" ? "active" : ""}
              onClick={() => onLangChange("zh")}
            >
              中文
            </button>
            <button
              type="button"
              className={lang === "en" ? "active" : ""}
              onClick={() => onLangChange("en")}
            >
              EN
            </button>
          </div>
          <select
            className="shop-account"
            value={account}
            onChange={(event) => onAccountChange(event.target.value)}
          >
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <button className="shop-mode" onClick={() => setFloating((value) => !value)}>
            {floating ? (lang === "zh" ? "返回全屏模式" : "Full screen") : s.modeToggle}
          </button>
        </div>
      </header>

      <nav className="shop-subnav">
        <span className="shop-subnav-title">✦ {s.workspace}</span>
        {s.nav.map((label, index) => (
          <button
            key={label}
            className="shop-subnav-link"
            onClick={() => {
              if (index === 0) void send(promptFor("logistics"));
              else if (index === 1) void send(promptFor("defect"));
              else if (index === 2) void send(promptFor("price"));
              else void send(t.callback);
            }}
          >
            {label}
          </button>
        ))}
        <span className="shop-engine">
          <span className="online-dot" />
          {s.engine}
        </span>
      </nav>

      <section className="chat-card">
        <header className="chat-head">
          <span className="agent-avatar">
            ✦
            <span className="avatar-online" />
          </span>
          <div className="chat-head-text">
            <div className="chat-head-title">
              {s.agentTitle}
              <span className="chat-badge">{s.agentBadge}</span>
            </div>
            <div className="chat-head-sub">
              {handedOff ? statusLabel(evidence.status) : s.agentSubtitle}
            </div>
          </div>
          <div className="chat-head-actions">
            <button className="chat-head-btn" onClick={() => void send(t.callback)}>
              ☎ {s.callBack}
            </button>
            <button className="chat-head-btn" onClick={() => void send(t.promptHuman)}>
              👤 {s.transfer}
            </button>
            <button className="chat-end-btn" onClick={() => void endChat()}>
              {s.end}
            </button>
          </div>
        </header>

        <div className="chat-context">
          <span className="chat-context-icon">◎</span>
          <span className="chat-context-text">
            {s.contextPrefix}:{" "}
            {activeOrder ? (
              <>
                <strong>{activeOrder.order_id}</strong>
                {activeOrder.product ? ` · ${activeOrder.product}` : ""}
              </>
            ) : (
              lang === "zh" ? "尚未关联订单" : "no order linked"
            )}
          </span>
          <button className="chat-context-link" onClick={() => void endChat()}>
            {s.reset}
          </button>
        </div>

        {session && session.status !== "closed" && session.service_mode !== "bot" ? (
          <div className={`chat-session-strip ${session.service_mode}`} role="status">
            <span className="chat-session-dot" />
            <span>
              {session.service_mode === "waiting_human"
                ? t.sessionWaiting(session.handoff?.queue_position ?? null)
                : session.service_mode === "human"
                  ? t.sessionHuman(session.handoff?.assigned_agent_id ?? null)
                  : t.sessionReview}
            </span>
          </div>
        ) : null}

        <div className="chat-scroll" ref={scrollRef} aria-live="polite">
          <div className="chat-time-banner">
            {resumedAt
              ? s.resumed(formatTime(Date.parse(resumedAt)))
              : s.banner(formatTime(openedAt))}
          </div>

          {messages.length === 0 && !csatTarget ? (
            <>
              <div className="bubble-row assistant">
                <span className="avatar bot">✦</span>
                <div className="bubble-col">
                  <div className="bubble-meta">
                    {s.agentTitle} · {formatTime(openedAt)}
                  </div>
                  <div className="bubble assistant">
                    <div className="bubble-body">{t.opening}</div>
                  </div>
                </div>
              </div>

              {orders.length > 0 ? (
                <div className="chat-order-card">
                  <div className="chat-order-card-head">
                    <span>{s.pickerTitle}</span>
                    <span className="chat-order-card-tag">{s.pickerTag}</span>
                  </div>
                  {orders.map((order) => (
                    <div
                      key={order.order_id}
                      className={`chat-order-item ${order.order_id === activeOrder?.order_id ? "active" : ""}`}
                    >
                      <span className="chat-order-icon">{productIcon(order.product, lang)}</span>
                      <div className="chat-order-main">
                        <div className="chat-order-top">
                          <span className={`status-chip ${STATUS_TONE[order.status] ?? "grey"}`}>
                            {t.status[order.status] ?? order.status}
                          </span>
                          <span className="chat-order-id">{order.order_id}</span>
                        </div>
                        <div className="chat-order-name">{order.product || t.orderLabel}</div>
                      </div>
                      <button className="chat-order-btn" onClick={() => pickOrder(order)}>
                        {s.selectOrder}
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}

          {messages.map((message) => (
            <div className={`bubble-row ${message.role}`} key={message.id}>
              {message.role === "assistant" ? (
                <span className={`avatar ${message.channel === "human" ? "human" : "bot"}`}>
                  {message.channel === "human" ? "人" : "✦"}
                </span>
              ) : null}
              <div className="bubble-col">
                {message.role === "assistant" ? (
                  <div className="bubble-meta">
                    {message.channel === "human"
                      ? `${s.humanAgent}${message.agentId ? ` ${message.agentId}` : ""}`
                      : s.agentTitle}{" "}
                    · {formatTime(message.createdAt)}
                  </div>
                ) : null}
                <div className={`bubble ${message.role}`}>
                  <div className="bubble-body">{message.text}</div>
                  {message.attachments && message.attachments.length > 0 ? (
                    <div className="bubble-attachments">
                      {message.attachments.map((file) => (
                        <a
                          key={file.id}
                          href={thumbUrls[file.id] ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {thumbUrls[file.id] ? (
                            <img src={thumbUrls[file.id]} alt={file.filename} />
                          ) : (
                            <span className="bubble-attach-name">{file.filename}</span>
                          )}
                        </a>
                      ))}
                    </div>
                  ) : null}
                  {message.role === "user" ? (
                    <div className="bubble-time">{formatTime(message.createdAt)}</div>
                  ) : null}
                </div>
              </div>
            </div>
          ))}

          {busy ? (
            <div className="bubble-row assistant">
              <span className="avatar bot">✦</span>
              <div className="typing" aria-label="typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          ) : null}

          {csatTarget ? (
            <div className="chat-csat" role="group" aria-label={t.csatTitle}>
              <div className="chat-csat-head">
                <span className="chat-csat-check">✓</span>
                <div>
                  <div className="chat-csat-ended">{s.chatEnded}</div>
                  {!csatDone ? <div className="chat-csat-title">{t.csatTitle}</div> : null}
                </div>
              </div>

              {csatDone ? (
                <div className="chat-csat-done">{t.csatThanks}</div>
              ) : (
                <>
                  <div className="chat-csat-sub">{t.csatSub}</div>
                  <div className="chat-csat-stars">
                    {[1, 2, 3, 4, 5].map((value) => (
                      <button
                        key={value}
                        type="button"
                        className={`chat-csat-star ${csatScore >= value ? "on" : ""}`}
                        aria-label={t.csatScoreLabels[value - 1]}
                        aria-pressed={csatScore === value}
                        onClick={() => setCsatScore(value)}
                      >
                        ★
                      </button>
                    ))}
                    <span className="chat-csat-score-label">
                      {csatScore > 0 ? t.csatScoreLabels[csatScore - 1] : ""}
                    </span>
                  </div>
                  <div className="chat-csat-tags">
                    {(
                      ["fast", "clear", "friendly", "resolved", "needs_work"] as const
                    ).map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        className={`chat-csat-tag ${csatTags.includes(tag) ? "on" : ""}`}
                        aria-pressed={csatTags.includes(tag)}
                        onClick={() => toggleCsatTag(tag)}
                      >
                        {t.csatTagLabels[tag]}
                      </button>
                    ))}
                  </div>
                  <textarea
                    className="chat-csat-comment"
                    value={csatComment}
                    maxLength={500}
                    placeholder={t.csatCommentPlaceholder}
                    onChange={(event) => setCsatComment(event.target.value)}
                  />
                  {csatError ? <div className="chat-csat-error">{csatError}</div> : null}
                  <button
                    type="button"
                    className="chat-csat-submit"
                    disabled={csatScore === 0 || csatBusy}
                    onClick={() => void submitRating()}
                  >
                    {csatBusy ? "…" : t.csatSubmit}
                  </button>
                </>
              )}
            </div>
          ) : null}
        </div>

        {evidence.pending ? (
          <div className="chat-confirm">
            <ConfirmationCard pending={evidence.pending} busy={busy} onDecide={decide} />
          </div>
        ) : null}

        <div className="chat-pills">
          <button
            className="chat-pill"
            disabled={humanMode || sessionClosed}
            onClick={() => void send(promptFor("logistics"))}
          >
            📦 {s.pillTrack}
          </button>
          <button
            className="chat-pill"
            disabled={humanMode || sessionClosed}
            onClick={() => void send(promptFor("defect"))}
          >
            ⚡ {s.pillRefund}
          </button>
          <button
            className="chat-pill"
            disabled={humanMode || sessionClosed}
            onClick={() => void send(promptFor("price"))}
          >
            💰 {s.pillPrice}
          </button>
          <button
            className="chat-pill accent"
            disabled={humanMode || sessionClosed}
            onClick={() => void send(t.promptHuman)}
          >
            👩‍💼 {s.pillHuman}
          </button>
        </div>

        {pendingFiles.length > 0 ? (
          <div className="chat-attach-row">
            {pendingFiles.map((file) => (
              <span className="chat-attach-chip" key={file.id}>
                {thumbUrls[file.id] ? <img src={thumbUrls[file.id]} alt={file.filename} /> : null}
                <span className="chat-attach-name">{file.filename}</span>
                <button
                  type="button"
                  onClick={() =>
                    setPendingFiles((current) => current.filter((item) => item.id !== file.id))
                  }
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="chat-compose">
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            hidden
            onChange={(event) => void handleFiles(event.target.files)}
          />
          <button
            type="button"
            className="chat-clip"
            title={lang === "zh" ? "上传图片" : "Upload image"}
            onClick={() => fileRef.current?.click()}
            disabled={uploading || sessionClosed}
          >
            {uploading ? "…" : "📎"}
          </button>
          <div className="chat-input-wrap">
            <textarea
              value={draft}
              maxLength={MAX_MESSAGE_LENGTH}
              placeholder={sessionClosed ? t.sessionClosed : s.composerPlaceholder}
              disabled={sessionClosed}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
            <span className="chat-spark">✦</span>
          </div>
          <button
            className="send-pill"
            onClick={submit}
            disabled={
              busy || uploading || sessionClosed || (!draft.trim() && pendingFiles.length === 0)
            }
          >
            {s.send}
          </button>
        </div>
        {draft.length > 0 ? (
          <div className="chat-counter">
            {draft.length}/{MAX_MESSAGE_LENGTH}
          </div>
        ) : null}
        {error ?? loginError ? <div className="error-line">{error ?? loginError}</div> : null}
      </section>
    </div>
  );
}
