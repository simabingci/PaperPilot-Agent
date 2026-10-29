# 架构与数据流

PaperPilot 使用一个 LangGraph Agent，FastAPI 管理来源和任务，Streamlit 提供交互。
SQLite 保存文本分块、任务事件和图 checkpoint；检索与工具调用运行在 CPU 上。

## 来源导入

`paperpilot/ingest.py` 负责外部输入校验与解析。PDF 按物理页提取文字，再通过
LangChain 分块；分块保留页码。公开 GitHub 仓库通过 API 确定 commit，读取
该 commit 的官方归档，在内存中选取根配置与主要代码文件，保留路径和行号。
归档中的脚本不会执行。具体大小与文件数限制见 README。

`paperpilot/store.py` 将来源、文本及定位元数据写入 SQLite。原始上传 PDF
不作为应用运行数据持久保存，提取文本、文件名和哈希会保留。

## Agent 工作流

`paperpilot/workflow.py` 的五个节点分别承担以下职责：

| 节点 | 行为 |
|---|---|
| consent | Live 模式通过 LangGraph interrupt 暂停，等待发送数据的确认 |
| plan | 按来源加载 Skill，生成 2–5 步工具计划并校验工具名称 |
| execute | 通过 MCP stdio 客户端逐步调用工具，收集证据与失败事件 |
| synthesize | 使用检索证据生成符合 Pydantic schema 的报告 |
| audit | 核对引用 ID；非法引用最多反馈纠正一次，仍无效则失败 |

正常 Live 任务调用模型两次，引用纠正最多额外一次。网络请求不自动重试。
Mock 模式采用确定性的工具计划并输出证据预览，始终显示模拟标识；Live 错误
不会触发 Mock 回退。

任务和工具事件追加到数据库，页面可查看进度。等待确认的 checkpoint 可以在
重建图后继续；服务重启时，执行中的任务明确标为失败。当前采用单 API worker，
最多 8 个排队及处理中任务，最多 2 个同时执行。

## RAG、MCP 与 Skills

`paperpilot/retrieval.py` 使用字符 2–4 gram 的 HashingVectorizer，生成
L2 归一化稀疏向量，以余弦相似度取前 5 个、分数至少 0.015 的分块。
向量按查询从文本重建，无需单独的向量数据库。这是词面检索，缺乏跨语言语义保证。

`paperpilot/mcp_server.py` 使用官方 MCP Python SDK 提供 `source_overview`、
`paper_search` 和 `code_search`。Agent 通过实际 stdio 子进程连接它；子进程环境
不传入模型密钥。工具返回带定位信息的结构化结果。

`paperpilot/skills/` 下的两个 SKILL.md 包含论文与仓库分析要求、名称和允许工具。
`paperpilot/skills.py` 加载其元数据和正文，正文进入规划及报告提示，允许工具约束
实际计划。它们随 Python 包分发，测试检查加载、路由和提示使用。

## 报告边界

报告引用绑定到本次真实检索的证据 ID，再渲染成 PDF 页码或固定 commit 的代码行号。
校验保证来源存在，不保证每条结论都由引用充分支持。没有 OCR、任意网页搜索、
代码执行或多租户权限隔离。部署应限定在个人工作区，模型配置与运行数据不进入 Git。
