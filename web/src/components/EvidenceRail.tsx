import ConfirmationCard from "./ConfirmationCard";
import type { RunEvidence } from "../types";

interface Props {
  evidence: RunEvidence;
  busy: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}

function shortJson(value: unknown, limit = 220): string {
  const text = JSON.stringify(value);
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function sourceLabel(source: string): string {
  return source.replace(/\.md$/, "").split("/").slice(-2).join("/");
}

export default function EvidenceRail({ evidence, busy, onDecide }: Props) {
  const { knowledge, toolCalls, toolResults, trace, plan, pending } = evidence;
  const resultByName = new Map(toolResults.map((item) => [item.tool_call_id, item]));

  return (
    <>
      {pending ? (
        <ConfirmationCard pending={pending} busy={busy} onDecide={onDecide} showInternals />
      ) : null}

      <div className="rail-section">
        <div className="rail-heading">
          知识引用 <span className="count">{knowledge.length}</span>
        </div>
        {knowledge.length === 0 ? (
          <p className="empty-note">
            本轮没有命中知识库。订单、物流这类实时事实不走知识库，请看下面的工具回执。
          </p>
        ) : (
          knowledge.map((chunk) => (
            <div className="citation" key={`${chunk.id}-${chunk.source}`}>
              <div className="citation-source">{sourceLabel(chunk.source)}</div>
              <div className="citation-body">
                <p className="citation-title">{chunk.title}</p>
                <p className="citation-text">{chunk.content}</p>
                <span className="citation-score">score {chunk.score.toFixed(3)}</span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="rail-section">
        <div className="rail-heading">
          工具回执 <span className="count">{Math.max(toolCalls.length, toolResults.length)}</span>
        </div>
        {toolCalls.length === 0 && toolResults.length === 0 ? (
          <p className="empty-note">本轮没有调用业务工具。</p>
        ) : toolCalls.length === 0 ? (
          // 审批执行产生的回执没有对应的 tool_call 事件，直接按回执渲染。
          toolResults.map((result) => (
            <div className="tool-row" key={result.tool_call_id}>
              <div>
                <span className="tool-name">{result.name}</span>{" "}
                <span className={result.ok ? "badge petrol" : "badge brick"}>
                  {result.ok ? "成功" : "失败"}
                </span>
              </div>
              <pre className="tool-payload">回执 {shortJson(result.payload)}</pre>
            </div>
          ))
        ) : (
          toolCalls.map((call) => {
            const result = resultByName.get(call.id);
            return (
              <div className="tool-row" key={call.id}>
                <div>
                  <span className="tool-name">{call.name}</span>{" "}
                  {result ? (
                    <span className={result.ok ? "badge petrol" : "badge brick"}>
                      {result.ok ? "成功" : "失败"}
                    </span>
                  ) : (
                    <span className="badge">未返回</span>
                  )}
                </div>
                <pre className="tool-payload">
                  入参 {shortJson(call.arguments, 120)}
                  {"\n"}
                  回执 {result ? shortJson(result.payload) : "—"}
                </pre>
              </div>
            );
          })
        )}
      </div>

      {plan && plan.steps.length > 0 ? (
        <div className="rail-section">
          <div className="rail-heading">
            计划 <span className="count">{plan.steps.length}</span>
          </div>
          {plan.steps.map((step) => (
            <div className="trace-row" key={step.step_id}>
              <span className="trace-stage">{step.action_type}</span>
              <span>
                {step.title}
                {step.requires_confirmation ? "（需确认）" : ""}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="rail-section">
        <div className="rail-heading">
          执行轨迹 <span className="count">{trace.length}</span>
        </div>
        {trace.length === 0 ? (
          <p className="empty-note">还没有执行记录。</p>
        ) : (
          trace.map((step, index) => (
            <div className="trace-row" key={`${step.stage}-${index}`}>
              <span className="trace-stage">{step.stage}</span>
              <span>{step.detail}</span>
            </div>
          ))
        )}
      </div>

      <p className="rail-footnote">
        这一栏只展示后端真实返回的证据。回答里没有出处、没有工具回执的内容，不要当作已核实的业务结果。
      </p>
    </>
  );
}
