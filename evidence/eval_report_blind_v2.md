# 分层评测报告

生成时间：2026-11-08T05:57:04+00:00

## 数据集

- 评测集版本：`eval_set_blind_v2`，语料版本：`v1`
- 独立语义种子：40 条；表达变体：每条 10 种；合计 400 条
- 切分：开发 160 条 / 封闭测试 240 条，按种子分组切分，同一 seed 的变体不会跨侧
- 其中模型改写失败的种子走了确定性模板兜底：3 条

> 说明：400 条由 40 条独立语义扩展而来，**真正独立的语义只有 40 条**。变体衡量的是表达鲁棒性，不是知识覆盖度。

## 检索

- 参与检索评测的样本：340 条（另有 60 条为工具/超纲/越权项，无知识来源期望）
- 总体 Hit@5：**0.956**，MRR：**0.889**
- 只看原句（34 条）：Hit@5 0.971，MRR 0.922

### 按类别

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| after_sales | 60 | 0.833 | 0.724 |
| enterprise_sla | 40 | 1.000 | 0.983 |
| logistics | 50 | 1.000 | 0.917 |
| policy | 70 | 0.971 | 0.902 |
| risk_security | 50 | 0.940 | 0.813 |
| troubleshooting | 70 | 1.000 | 1.000 |

### 按表达变体

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| background | 34 | 0.941 | 0.892 |
| bilingual | 34 | 0.912 | 0.848 |
| colloquial | 34 | 0.971 | 0.848 |
| emotional | 34 | 0.971 | 0.858 |
| filler | 34 | 0.971 | 0.887 |
| formal | 34 | 0.941 | 0.922 |
| original | 34 | 0.971 | 0.922 |
| polite | 34 | 0.971 | 0.922 |
| synonym | 34 | 0.941 | 0.854 |
| terse | 34 | 0.971 | 0.941 |

### 按切分

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| dev | 130 | 0.977 | 0.897 |
| test | 210 | 0.943 | 0.884 |

### 按风险等级

| 分组 | 样本 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| high | 40 | 0.975 | 0.854 |
| normal | 300 | 0.953 | 0.894 |

## 路由判定

- 可判定的样本：370 条
- 路由准确率：**0.995**

| 类别 | 样本 | 路由准确率 |
| --- | ---: | ---: |
| after_sales | 60 | 1.000 |
| enterprise_sla | 40 | 1.000 |
| logistics | 50 | 1.000 |
| policy | 70 | 1.000 |
| risk_security | 50 | 1.000 |
| tool_realtime | 30 | 0.933 |
| troubleshooting | 70 | 1.000 |

## 失败样本

| seed | 变体 | 问题 | 期望 | 实际命中 |
| --- | --- | --- | --- | --- |
| c001 | synonym | 商品存在缺陷时，可采用哪些解决方式？ | policies/质量问题退换货政策.md | benefits/会员售后权益.md, announcements/618价保活动公告.md |
| c002 | bilingual | Refund 是不是要 wait for warehouse acceptance pass 才能 initiate？ | policies/七天无理由退货政策.md | faq/退款到账常见问题.md, sop/退款申请处理流程.md |
| c020 | original | 执行写操作前要先给用户看什么摘要？ | policies/质量问题退换货政策.md | sla/重大故障升级机制.md, risk/账户与支付安全提醒.md |
| c020 | colloquial | 执行写操作前，得先给用户看个啥摘要啊？ | policies/质量问题退换货政策.md | sla/重大故障升级机制.md, risk/账户与支付安全提醒.md |
| c020 | terse | 写操作前要展示什么摘要？ | policies/质量问题退换货政策.md | risk/账户与支付安全提醒.md, sop/投诉升级与转人工流程.md |
| c020 | polite | 您好，请问执行写操作前需要先向用户展示什么摘要呢？ | policies/质量问题退换货政策.md | sop/投诉升级与转人工流程.md, sla/重大故障升级机制.md |
| c020 | background | 我在做写操作之前，习惯性地会先看看用户能看到啥摘要，所以想确认下这个摘要具体是啥？ | policies/质量问题退换货政策.md | sop/投诉升级与转人工流程.md, sla/重大故障升级机制.md |
| c020 | synonym | 在发起写入动作之前，应当向用户呈现何种概要信息？ | policies/质量问题退换货政策.md | risk/账户与支付安全提醒.md, sop/投诉升级与转人工流程.md |
| c020 | bilingual | 执行 write operation 前，要先 show 用户 what summary？ | policies/质量问题退换货政策.md | sop/退款申请处理流程.md, merchant/平台介入处理规则.md |
| c020 | emotional | 急急急！写操作前到底要给用户看哪个摘要啊？ | policies/质量问题退换货政策.md | risk/账户与支付安全提醒.md, sop/投诉升级与转人工流程.md |
| c020 | formal | 请问在执行写操作之前，须向用户展示何种摘要信息？ | policies/质量问题退换货政策.md | sla/重大故障升级机制.md, sop/投诉升级与转人工流程.md |
| c020 | filler | 就是那个，执行写操作前，要先给用户看啥摘要来着？ | policies/质量问题退换货政策.md | sla/重大故障升级机制.md, risk/账户与支付安全提醒.md |
| c029 | background | 用户的重要隐私数据应当采取何种方式保存？ | risk/异常退款与凭证规则.md | benefits/企业客户服务权益.md, benefits/会员售后权益.md |
| c029 | bilingual | 用户的sensitive information应该怎么storage？ | risk/异常退款与凭证规则.md | benefits/会员售后权益.md, risk/账户与支付安全提醒.md |
| c030 | formal | 请问客服人员是否具备权限向用户直接披露其账户被判定为风险账户？ | risk/异常退款与凭证规则.md | risk/账户与支付安全提醒.md, risk/账户与支付安全提醒.md |
