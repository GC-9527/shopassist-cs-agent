import type { PendingConfirmation } from "../types";

interface Props {
  pending: PendingConfirmation;
  busy: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}

/**
 * 高风险操作的确认卡片。
 *
 * C 端和后台都要显示：这是用户自己在授权一次写入，不是内部信息。
 * 但**不展示**工具名、risk_level 这类内部字段给 C 端——
 * 由 `showInternals` 控制，只有后台看得到。
 */
export default function ConfirmationCard({ pending, busy, onDecide, showInternals }: Props & { showInternals?: boolean }) {
  return (
    <div className="confirm">
      <div className="confirm-title">
        <span className="badge amber">需要你确认</span>
        {showInternals ? "高风险操作" : "提交前请确认"}
      </div>
      <p className="confirm-prompt">{pending.confirmation_prompt}</p>
      {showInternals ? (
        <div className="confirm-meta">
          <span>
            工具 <code>{pending.tool_name}</code>
          </span>
          <span>风险 {pending.risk_level}</span>
          <span>操作 {pending.action_type}</span>
        </div>
      ) : null}
      <div className="confirm-actions">
        <button className="btn primary" onClick={() => onDecide("approve")} disabled={busy}>
          {busy ? "提交中…" : "确认提交"}
        </button>
        <button className="btn" onClick={() => onDecide("reject")} disabled={busy}>
          取消
        </button>
      </div>
    </div>
  );
}
