# 架构与数据流

PaperPilot 将联合证据、Agent 推理、实验执行和指标比较分开。已有 Agent 可以
通过 CLI/MCP 复用工具；Web 提供基于 LangGraph 的联合分析与结果工作台。

## 工作区与存储

`ingest.py` 导入文字 PDF 或公开 GitHub 快照。PDF 分块保留物理页码；GitHub API
解析固定 commit，官方归档在内存中读取主要文件，保留路径和行号。
`Store.add_study` 关联一篇 paper 和一个 repository，冻结这两个来源的元数据、
PDF 哈希与 commit；不会把两种来源混成失去定位信息的一段文本。

SQLite 包含 sources、chunks、jobs、events 和 results；新增 results 表可直接在
原数据库上创建，已有来源和任务保留。LangGraph 使用独立的 SQLite checkpoint。
上传 PDF 二进制不由应用持久化，提取文本和元数据会保留。

## 联合检索与报告

MCP stdio 工具有 `source_overview`、`paper_search`、`code_search`、`study_search`、
`list_sources`、`study_results`。`study_search` 分别在论文与代码中取最多 5 个词面
匹配分块，返回 `source_kind` 和原定位信息。CLI evidence 和 Web 都实际调用 MCP。

检索采用字符 2–4 gram 的 HashingVectorizer、2^18 特征和 L2 归一化，按余弦
相似度选择分数至少 0.015 的分块；向量按查询从 SQLite 文本重建。它不保证跨语言
语义召回，查询应包含领域英文词。

Web 工作流仍为五个 LangGraph 节点：

| 节点 | 职责 |
|---|---|
| consent | Live 模式 interrupt，等待数据发送确认 |
| plan | 根据来源类型加载内置 Skill，生成 2–6 步合法工具计划 |
| execute | MCP 工具循环，登记证据 ID、来源类型及失败事件 |
| synthesize | 生成结构化报告；联合来源使用 StudyReport |
| audit | 校验引用存在性和方法映射两端的来源类型，最多一次纠正 |

`StudyReport` 在普通引用报告之上增加 `method_map` 和 `experiments`。方法映射必须
同时含 paper 与 repository 证据 ID，交换类型也会被审核拒绝。实验目标含数据与
划分、指标、论文值、页码和未执行命令；无精确数值时为 null。Schema 枚举只包含
本次真实检索 ID。引用审核不验证语义蕴含，也不认证模型生成的超参数。

已导入的比较通过 study_results 返回为 experiment 类型证据。工具最多返回最近
三条、每条 16000 字符并标明截断；不按指标优劣筛选。报告可以联合解释实际数值
和协议差异，但不能把外部上传结果说成服务端认证。完整记录仍可通过 API 获取。

内置 `paper-reproduction` Skill 约束这一结构；外部
`agent-skills/paperpilot-reproduce` 给已有 Agent 提供完整 CLI 工作流。后者不调用
项目模型 API。两种入口共享证据与配方契约，不需要伪多智能体架构。

## 实验执行边界

`runner.py` 是独立主机 CLI，由用户在有 Docker 的机器运行。Web 和 MCP 不提供
执行仓库代码的接口，不挂载 Docker socket。Recipe 固定公开仓库 URL、完整 SHA、
本地镜像、相对适配器、argv 和 CPU/内存/时间预算。

inspect 将配方规范化 JSON、适配器 SHA-256 和解析后的镜像 ID 一起哈希。
run 必须收到相同的批准摘要；之后下载该 commit 的官方归档，限制压缩和解压规模，
拒绝路径穿越与符号链接。代码与适配器只读挂载；独立输出目录可写，临时目录
使用 tmpfs。容器无网络、无 GPU、删除 capabilities、使用非 root 用户并设置
CPU、内存、进程数和日志限制。镜像不自动构建或拉取。

容器退出码为 0 后，适配器必须提供合法的 metrics.json。超时、下载失败、非零
退出或缺失指标均记为失败，不生成成功对照。run.json 保存审阅内容、归档哈希、
状态、耗时和日志哈希；原始指标包含在独立 output 目录。
这一实现适用于已审阅代码，不等价于恶意代码的强隔离平台，也不限制输出卷总容量。

## 确定性结果比较

`experiments.py` 的 ResultSubmission 包含论文基准、实测协议/指标、实验范围、
代码 commit、原始指标哈希和基准复核标记。比较不调用模型。

- 按 dataset、split、preprocessing、model、training_budget、evaluation 精确匹配
  声明值；任一差异或 unknown 均作为不可比原因。
- 核对指标名称与单位；缺失指标和非有限数值不会成为成功结果。
- smoke 或未经核对的论文基准不能直接比较。
- 声明条件对齐时，以 `max(绝对容差, abs(论文值) × 相对容差)` 检查绝对差。

这些字段由适配器与使用者声明，程序不能证明它们真实；数值一致也不证明完整
复现或统计显著性。API 导入时验证工作区 commit 并重新计算对照，所有上传结果
均标为外部提交，不能伪装成由 API 认证的运行。

## 部署与恢复

默认单 API worker，队列最多 8 个任务、最多 2 个同时分析。等待确认的 checkpoint
可恢复；服务重启时执行中的分析任务标为失败。主机 Runner 需单独管理，当前不
实现 Web 调度、GPU 调度、自动修复或断点训练。单实例来源和历史共享，应使用
私有 SSH 隧道，当前无多租户权限隔离。
