# 分层评测报告

生成时间：2026-11-08T12:44:20+00:00

## 数据集

- 评测集版本：`eval_set_us_v1`，语料版本：`us-v1`
- 独立语义种子：40 条；表达变体：每条 10 种；合计 400 条
- 切分：开发 160 条 / 封闭测试 240 条，按种子分组切分，同一 seed 的变体不会跨侧
- 其中模型改写失败的种子走了确定性模板兜底：3 条

> 说明：400 条由 40 条独立语义扩展而来，**真正独立的语义只有 40 条**。变体衡量的是表达鲁棒性，不是知识覆盖度。

## 检索

- 参与检索评测的样本：360 条（另有 40 条为工具/超纲/越权项，无知识来源期望）
- 总体 Hit@5：**0.964**，MRR：**0.909**
- 只看原句（36 条）：Hit@5 0.972，MRR 0.936

### 按类别

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| after_sales | 40 | 0.925 | 0.819 |
| logistics | 70 | 0.857 | 0.857 |
| policy | 130 | 1.000 | 0.960 |
| risk_security | 30 | 1.000 | 0.933 |
| troubleshooting | 90 | 1.000 | 0.909 |

### 按表达变体

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| background | 36 | 0.972 | 0.915 |
| bilingual | 36 | 0.972 | 0.958 |
| colloquial | 36 | 0.917 | 0.853 |
| emotional | 36 | 0.972 | 0.915 |
| filler | 36 | 0.972 | 0.936 |
| formal | 36 | 0.972 | 0.894 |
| original | 36 | 0.972 | 0.936 |
| polite | 36 | 0.944 | 0.908 |
| synonym | 36 | 0.972 | 0.881 |
| terse | 36 | 0.972 | 0.897 |

### 按切分

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| dev | 140 | 0.993 | 0.976 |
| test | 220 | 0.946 | 0.867 |

### 按风险等级

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| high | 20 | 1.000 | 0.640 |
| normal | 340 | 0.962 | 0.925 |

## 路由判定

- 可判定的样本：380 条
- 路由准确率：**0.968**

| 类别 | 样本 | 路由准确率 |
| --- | ---: | ---: |
| after_sales | 40 | 0.950 |
| logistics | 70 | 0.857 |
| policy | 130 | 1.000 |
| risk_security | 30 | 1.000 |
| tool_realtime | 20 | 1.000 |
| troubleshooting | 90 | 1.000 |

## 失败样本

| seed | 变体 | 问题 | 期望 | 实际命中 |
| --- | --- | --- | --- | --- |
| u012 | original | My tracking has not updated for two days, what now? | faq/orders-and-shipping.md | （空） |
| u012 | colloquial | My tracking hasn’t updated in two days—what do I do now? | faq/orders-and-shipping.md | （空） |
| u012 | terse | Tracking hasn’t updated for two days. What now? | faq/orders-and-shipping.md | （空） |
| u012 | polite | Excuse me, my tracking hasn’t updated for two days—could you please advise what I should do next? | faq/orders-and-shipping.md | （空） |
| u012 | background | I’ve been checking my package every morning, and my tracking hasn’t updated for two days—what now? | faq/orders-and-shipping.md | （空） |
| u012 | synonym | My shipment status has remained unchanged for forty-eight hours—what should I do at this point? | faq/orders-and-shipping.md | （空） |
| u012 | bilingual | 我的tracking has not updated for two days，what now? | faq/orders-and-shipping.md | （空） |
| u012 | emotional | Ugh, my tracking hasn’t updated for two days—what do I do *right now*?! | faq/orders-and-shipping.md | （空） |
| u012 | formal | My package tracking information has not been updated for a period of two days; what course of action is recommended? | faq/orders-and-shipping.md | （空） |
| u012 | filler | So, like, my tracking has not updated for two days—what now? | faq/orders-and-shipping.md | （空） |
| u030 | colloquial | When do I need to pass a case over to a real person? | support/escalation-and-handoff.md | （空） |
| u030 | polite | Could you please let me know when a case should be escalated to a human agent? | support/escalation-and-handoff.md | （空） |
| u033 | colloquial | Which orders should we cancel instead of giving refunds? | support/refund-workflow-sop.md | policies/returns-refund-policy.md, faq/refunds-and-payments.md |
