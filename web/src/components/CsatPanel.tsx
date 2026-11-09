import { useEffect, useState } from "react";
import { fetchCsatSummary } from "../api";
import type { CsatSummary } from "../types";

const TAG_LABELS: Record<string, string> = {
  fast: "响应快",
  clear: "说明清楚",
  friendly: "态度友好",
  resolved: "问题解决",
  needs_work: "需改进",
};

const SCORE_HINTS: Record<number, string> = {
  5: "非常满意",
  4: "满意",
  3: "一般",
  2: "不满意",
  1: "很不满意",
};

/** 后端返回的是带时区的 ISO 时间，转成本地时间显示。 */
function formatStamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface Props {
  tenantId: string;
}

/**
 * 满意度看板。
 *
 * 数据来自 C 端结束会话后提交的评价；这里只做聚合展示，
 * 不提供修改入口——客户的评价不应该被后台改写。
 */
export default function CsatPanel({ tenantId }: Props) {
  const [summary, setSummary] = useState<CsatSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    let cancelled = false;
    fetchCsatSummary(tenantId, days)
      .then((next) => {
        if (!cancelled) {
          setSummary(next);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, days]);

  return (
    <div className="csat-panel">
      <div className="csat-head">
        <span className="csat-title">客户满意度</span>
        <div className="csat-range">
          {[7, 30, 90].map((value) => (
            <button
              key={value}
              className="csat-range-btn"
              aria-pressed={days === value}
              onClick={() => setDays(value)}
            >
              {value} 天
            </button>
          ))}
        </div>
      </div>

      {error ? <p className="error-line">满意度读取失败：{error}</p> : null}

      {summary && summary.total === 0 ? (
        <p className="empty-note">
          这段时间还没有评价。客户结束会话后会在对话框里看到评价卡片。
        </p>
      ) : null}

      {summary && summary.total > 0 ? (
        <>
          <div className="csat-stats">
            <div className="csat-stat">
              <span className="csat-stat-value">{summary.average?.toFixed(2)}</span>
              <span className="csat-stat-label">平均分</span>
            </div>
            <div className="csat-stat">
              <span className="csat-stat-value">{summary.total}</span>
              <span className="csat-stat-label">评价数</span>
            </div>
            <div className="csat-stat">
              <span className="csat-stat-value">
                {summary.positive_rate === null ? "—" : `${Math.round(summary.positive_rate * 100)}%`}
              </span>
              <span className="csat-stat-label">好评率</span>
            </div>
          </div>
          <p className="csat-hint">5 分制 · 好评 = 4-5 星</p>

          <div className="csat-distribution">
            {[5, 4, 3, 2, 1].map((score) => {
              const count = summary.distribution[String(score)] ?? 0;
              const width = summary.total ? (count / summary.total) * 100 : 0;
              return (
                <div className="csat-bar-row" key={score}>
                  <span className="csat-bar-label">
                    {score}★ <em>{SCORE_HINTS[score]}</em>
                  </span>
                  <span className="csat-bar-track">
                    <span
                      className={`csat-bar-fill ${score >= 4 ? "good" : score === 3 ? "mid" : "bad"}`}
                      style={{ width: `${width}%` }}
                    />
                  </span>
                  <span className="csat-bar-count">{count}</span>
                </div>
              );
            })}
          </div>

          {Object.keys(summary.tag_counts).length > 0 ? (
            <div className="csat-tags">
              {Object.entries(summary.tag_counts)
                .sort((a, b) => b[1] - a[1])
                .map(([tag, count]) => (
                  <span className="csat-tag" key={tag}>
                    {TAG_LABELS[tag] ?? tag}
                    <b>{count}</b>
                  </span>
                ))}
            </div>
          ) : null}

          <div className="csat-recent">
            <div className="csat-recent-title">最近评价</div>
            {summary.recent.map((item) => (
              <article className="csat-comment" key={item.conversation_id}>
                <div className="csat-comment-head">
                  <span className="csat-comment-score">{"★".repeat(item.score)}</span>
                  <span className="csat-comment-meta">
                    {item.user_id} · {formatStamp(item.created_at)}
                  </span>
                </div>
                {item.comment ? <p className="csat-comment-text">{item.comment}</p> : null}
                {item.tags.length > 0 ? (
                  <div className="csat-comment-tags">
                    {item.tags.map((tag) => (
                      <span key={tag}>{TAG_LABELS[tag] ?? tag}</span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
