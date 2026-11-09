# 检索消融记录

> 本文件只报告**实际跑出来的数字**。没有跑过的指标一律不写。

## 实验条件

| 项 | 值 |
| --- | --- |
| 语料 | `knowledge_base/`，20 篇 Markdown 文档，切分后 59 个 chunk |
| Embedding | 阿里云百炼 `text-embedding-v4`，1024 维 |
| 向量库 | Qdrant 1.18（collection `ecom_customer_service_knowledge`） |
| 词法索引 | OpenSearch 2.17.1，`cjk` 分析器，BM25 |
| 重排 | 百炼 `gte-rerank-v2`（`DashScopeKnowledgeReranker`） |
| 评测集 | `knowledge_base/evaluation_queries.json`，20 条，含 exact / semantic 两类 |
| top_k | 5 |
| 候选倍数 | `HYBRID_CANDIDATE_MULTIPLIER=3`（每路召回 15，RRF 融合 `k=60`） |
| 指标 | Hit@5（期望文档是否出现在前 5）、MRR（首个命中位置的倒数均值） |
| 时间 | 2026-11-08，租户 `default` |

## 结果

| 阶段 | 配置 | Hit@5 | MRR | 变化原因 |
| --- | --- | --- | --- | --- |
| ① 初始 | dense | 0.65 | 0.60 | 基线 |
| ② 修复路由误判 | dense | 0.65 | 0.625 | 两条查询不再被误判为实时查询而跳过检索 |
| ③ 修复过期语料 | dense | 0.70 | 0.675 | 两篇公告的 `expires_at` 早于今天，被生命周期正确排除 |
| ④ 修复文档类型白名单 | dense | **1.00** | **0.95** | 公告 / 手册 / SLA / 权益类文档不再在召回阶段被静默过滤 |
| ⑤ 加 BM25 混合召回 | hybrid | 1.00 | 0.95 | 本语料下无额外增益 |
| ⑥ 加百炼重排 | hybrid + rerank | 1.00 | **1.00** | 只提升排序，不改变召回 |

## 三个真实缺陷

### 1. 路由把"问流程"误判成"查实时数据"

`真正帮用户创建退款前要做哪些步骤？` 和 `机器客服什么情况必须转人工？` 因为有"创建""转人工"这类动作词，被判成 `realtime_tool`，检索直接短路返回空。

修复：区分**指向具体业务实体**（"我的订单"、8 位以上单号）与**询问规则**（"步骤""什么情况""流程"）。指向具体订单时仍走实时工具，问规则时走知识库。

### 2. 语料与评测集版本不一致

两篇公告的 `expires_at` 分别是 2026-03-10 和 2026-07-20，早于评测日期。知识生命周期按设计把它们排除了，但评测集仍期望这两篇。

这不是检索退化，而是**评测集没有跟着语料版本走**。排查时如果不看生命周期清单，很容易误判成"向量库召回不行"。

### 3. 文档类型白名单静默丢召回

`QuestionRouter._document_types()` 对政策类问题只放 `policy / matrix / faq / sop` 四类，不含 `announcement / manual / sla / benefit / troubleshooting`。结果是文档明明收录了，却在召回阶段被过滤掉，表现为"知识库里有、就是检索不到"。

这类 bug 最危险的地方是**没有任何报错**：召回数量正常、分数正常，只是正确答案不在里面。修复后 Hit@5 从 0.70 直接到 1.00。

## 如何迁移到生产

- 20 条自建评测集规模太小，且查询由作者本人编写，**乐观偏差明显**，不能当作线上效果。真实上线需要用脱敏工单 + 客服复核构建分层评测集，并按来源分组切分。
- 本语料下 dense 已经足够，BM25 与重排没有带来 Hit@5 增益。只有在语料规模变大、或存在大量型号/规则编码类查询时，混合召回与重排的收益才会体现——这需要用真实分布验证，不能直接沿用本表。
- 重排会增加一次外部调用与相应延迟，是否开启应由**质量增益是否覆盖成本**决定。

## 复现命令

```bash
# ① 纯向量
OPENSEARCH_ENABLED=false RERANK_ENABLED=false \
  .venv/Scripts/python.exe scripts/evaluate_retrieval.py \
  --queries knowledge_base/evaluation_queries.json --tenant-id default --top-k 5

# ② 混合召回
OPENSEARCH_ENABLED=true RERANK_ENABLED=false \
  .venv/Scripts/python.exe scripts/evaluate_retrieval.py \
  --queries knowledge_base/evaluation_queries.json --tenant-id default --top-k 5

# ③ 混合召回 + 重排
OPENSEARCH_ENABLED=true RERANK_ENABLED=true \
  .venv/Scripts/python.exe scripts/evaluate_retrieval.py \
  --queries knowledge_base/evaluation_queries.json --tenant-id default --top-k 5 --rerank
```
