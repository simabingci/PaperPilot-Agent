# PaperPilot Agent

[English](README.en.md) · [十分钟上手](docs/quickstart.md) · [Agent 接入](docs/integrations.md) · [架构](docs/architecture.md) · [复现流程](docs/reproduction.md) · [部署](docs/deployment.md) · [测试](docs/testing.md)

[![Tests](https://github.com/simabingci/PaperPilot-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/simabingci/PaperPilot-Agent/actions/workflows/ci.yml)

**在已有 Agent 中读懂论文，连接方法、代码与实验。**

不需要额外模型 Key：把 PaperPilot 接进你正在用的 Agent，它负责推理，PaperPilot 负责
可追溯的证据、版本与实验记录。

```bash
paperpilot connect --agent deepseek-harness   # 写入客户端配置（自动备份），重启客户端即可
```

PaperPilot 为个人和课题组提供本地科研学习工作区。沿用已有 Agent 的推理能力，
保存论文依据、逐轮讲解、真实回答与反馈；原文和笔记可以在同一个页面对照阅读。
没有作者代码，也可以先学习方法并整理独立实现所需的条件。

![原创教学材料的实际阅读页面](docs/screenshots/learning-reader.jpg)

截图来自原创教学示例，不代表真实论文分析效果或学习测评结果。

## 核心体验

- **一起读**：一次解释一个概念，提出一个理解题，等待实际回答；可明确跳过。
- **对照原文**：保留物理页码，直接渲染公式与图表；可导出按页标记的全文。
- **继续学习**：恢复当前问题、回答、反馈与待复习概念，不伪造“已经掌握”。
- **连接代码**：固定公开仓库版本，引用代码行号，区分作者实现和独立实现。
- **核对实验**：受控执行已审阅的配方，记录真实指标，并按协议与论文结果比较。

0.3.0 面向个人工作区，同门各自安装与保存数据，不提供共享账号或云端同步。
学习流程无需额外模型 Key；调用方 Agent 自身的账户与用量仍按其服务计量。
实验环境、指标适配器和未公开细节仍需使用者与 Agent 准备，不保证任意论文一键复现。

## 安装（一次）

Python 3.12+。在独立虚拟环境安装：

```bash
git clone https://github.com/simabingci/PaperPilot-Agent.git
cd PaperPilot-Agent
python -m venv .venv
# 激活环境：Windows PowerShell 用 .\.venv\Scripts\Activate.ps1；macOS/Linux 用 source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
```

也可以让已有 Agent 完成安装，再进入自己的科研项目目录安装下方 Skill。

## 使用方式

### 在已有 Agent 中学懂论文（有无源码均可）

安装项目后，在自己的科研项目目录运行 `paperpilot skill-install`，将
`paperpilot-study` 和当前 Python 运行信息安装到该目录的 `.agents/skills/`，在新的 Codex 会话中使用。
无需再配置 PaperPilot 模型 Key。

使用其他客户端时，替换安装命令即可：

```bash
paperpilot skill-install --agent claude-code
paperpilot skill-install --agent deepseek-harness
paperpilot skill-install --agent workbuddy
```

Claude Code/Harness 安装项目 Skill；WorkBuddy 生成供本机上传的 Skill ZIP。
同一个 `--data-dir` 可顺序跨客户端继续学习。另提供 MCP 配置导出，不改全局配置。
这些适配已做安装与真实协议调用测试，三种原生客户端尚未逐一对话验收；
步骤与边界见 [Agent 接入](docs/integrations.md)。

示例请求：

> 使用 paperpilot-study 带我读这篇论文。一次只讲一个概念，结合原文解释，
> 问一个理解题，等我回答后再继续；保存学习记录。这篇论文没有源码。

```bash
paperpilot --data-dir ./data learn start --pdf paper.pdf --goal "读懂方法与实验"
paperpilot --data-dir ./data notebook
```

Agent 提供讲解和反馈，CLI 保存带原文摘录的概念、真实回答和反馈，网页用于回顾。
学习目录由使用者单独管理；不是多人共享账户或云同步系统。没有作者实现时，先
整理方法与缺失设置，再准备独立实现，不能把补充假设当作论文事实。
详细命令与边界见 [论文学习](docs/learning.md)。

### 已有 Agent：Skill + CLI

Python 3.12+，在项目根目录安装：

```bash
python -m venv .venv
# 激活虚拟环境；Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e .
paperpilot --help
```

将 `agent-skills/paperpilot-reproduce` 放到 Agent 支持的 Skills 目录，或让 Agent
读取该 SKILL.md。CLI 证据流程不调用模型，不需要额外 API key，也不要求启动 Web。

```bash
paperpilot init --pdf paper.pdf --repo https://github.com/owner/repo --title "目标实验"
paperpilot evidence --study STUDY_ID --query "method dataset split training evaluation"
paperpilot schema recipe
```

使用已有 Agent 讲解联合证据、编写配方与适配器。主机需要 Docker 才能运行实验：

```bash
paperpilot inspect recipe.json
# 核对配方、适配器、镜像、代码版本和资源预算，批准后填入完整摘要：
paperpilot run recipe.json --approve APPROVAL_DIGEST
paperpilot compare data/runs/RUN_ID/comparison-input.json --output data/comparison.md
paperpilot record data/runs/RUN_ID/comparison-input.json --study STUDY_ID
```

完整可运行案例见 [TCN Adding Problem](examples/tcn-adding/README.md)。

[真实联合报告](docs/examples/tcn-study-report.md)保留模型对论文、代码和导入结果的原始分析。

![真实 CPU 运行结果与论文基准对照](docs/screenshots/reproduction-results.jpg)

[查看联合分析完成页面](docs/screenshots/joint-study.jpg)。截图来自实际部署页面，未修改显示值。

### Web：联合研究与结果工作台

```bash
docker compose up -d --build --wait
```

打开 `http://localhost:8501`，API 文档在 `http://localhost:8000/docs`。
依次导入 PDF 和公开仓库，建立工作区，选择讲解、复现规划或差异排查任务。
运行完成后可上传 `comparison-input.json`，查看并下载结果对照表。

默认 Mock 模式执行真实解析和 MCP 检索，仅输出明确标记的证据预览。
Web 联合推理需配置 OpenAI 兼容模型，再逐任务确认数据传输：

```dotenv
PAPERPILOT_MODE=live
OPENAI_BASE_URL=https://your-compatible-provider/v1
OPENAI_MODEL=your-model
OPENAI_API_KEY=your-private-key
```

从 `.env.example` 创建本地 `.env`，不要提交密钥。Ollama 可使用其 `/v1` 兼容
地址与 `ollama` key；具体本地模型尚未实机验证。Windows 原生启动、供应商参数、
SSH 访问与镜像下载见 [部署说明](docs/deployment.md)。

## 工作原理

```mermaid
flowchart LR
    P[论文 PDF] --> S[联合工作区 / SQLite]
    C[公开代码 / 固定 commit] --> S
    S --> E[MCP 联合证据检索]
    E --> A[已有 Agent / Web LangGraph]
    A --> X[讲解 / 方法映射 / 实验草案]
    X --> R[审阅配方与批准摘要]
    R --> D[CPU Docker Runner]
    D --> M[真实指标与日志]
    M --> V[协议 / 单位 / 容差比较]
    V --> T[结果工作台与 Markdown]
```

Web 使用单个 LangGraph Agent，含确认、规划、MCP 工具循环、生成、引用审核五个
节点。联合报告的每条方法映射分别引用论文和代码。非法引用最多纠正一次；模型
失败直接报告错误。SQLite checkpoint 保存待确认状态，事件记录保留工具过程。

检索使用 CPU 字符 2–4 gram 稀疏哈希向量及余弦相似度，无独立向量数据库。
它是词面检索，跨语言问题应补充英文关键词。MCP 使用官方 Python SDK **2.3.0**
与真实 stdio 通信。详细数据结构和执行边界见 [架构说明](docs/architecture.md)。

## 边界与结果解释

| 项目 | 当前范围 |
|---|---|
| PDF | 可提取文字，最多 20 MB / 150 页；无 OCR、图表视觉理解 |
| 仓库分析 | 最多 24 个选定文件，每文件前 100 KB、总索引 2 MB；不是全仓覆盖 |
| Runner | 独立主机 CLI、Linux CPU 容器、无网络或 GPU；预算最多 30 分钟 / 4 CPU / 8 GB |
| 环境 | 需要预先构建的本地镜像；不自动安装依赖、修补仓库或无限重试 |
| 结果可信度 | 保存原始指标、日志和哈希；API 上传结果标记为外部提交，不认证执行真实性 |
| 复现结论 | 协议按提交内容核对；引用存在或数值接近均不能单独证明完整复现 |
| 部署 | 单用户共享工作区，无登录和租户隔离；端口默认仅绑定本机 |

Web 容器不挂载 Docker socket。运行数据、学习笔记、上传原文和模型密钥不进入 Git。原 PDF 保存在本地数据目录，供原页阅读。
Runner 适用于经过审阅的代码，不是面向恶意代码的托管沙箱服务。

## 开发

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check .
```

测试涵盖真实 MCP、联合来源、映射引用、确认恢复、结果协议、批准摘要、执行失败
和 API 持久化。CI 在 Windows/Linux、Python 3.12/3.13 上运行，并构建和启动 Web
容器。实际论文训练需要额外的实验镜像，见 [测试说明](docs/testing.md)。

技术依据：[LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api)、
[MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)、
[Agent Skills](https://agentskills.io/specification)、
[Docker 运行参数](https://docs.docker.com/engine/containers/run/)。

MIT License。被分析的论文、代码和数据遵循各自的权利与许可。
