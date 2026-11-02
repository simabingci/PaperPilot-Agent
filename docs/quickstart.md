# 十分钟上手

目标：从干净环境出发，十分钟内拿到第一份可核对的分析报告。

## 1. 安装（约 3 分钟）

```bash
git clone https://github.com/simabingci/PaperPilot-Agent.git
cd PaperPilot-Agent
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
```

验证安装：

```bash
paperpilot --help
paperpilot doctor      # 检查 Python、数据目录、PDF 依赖、Docker、模型配置与鉴权
```

`doctor` 对每一项给出 `ok` / `warn` / `fail` 和一句处理建议；退出码非 0 表示有必须
先修的问题。

## 2. 建一个工作区（约 2 分钟）

只需要论文 PDF 和一个公开仓库地址。

```bash
paperpilot init --pdf paper.pdf --repo https://github.com/owner/repo --title "目标实验"
```

输出里的 `id` 就是 study ID，先记下来。默认数据目录是 `./data`，想换位置就加
`--data-dir PATH`，且后续每条命令都要带同一个。

## 3. 取证据（约 1 分钟）

```bash
paperpilot evidence --study STUDY_ID --query "method dataset split training evaluation"
```

这条命令不联网调用模型、不产生费用：它启动真实的 MCP 子进程，同时检索论文页和固定
commit 的代码行，把带页码/行号的证据打印成 JSON。

## 4. 拿到报告

### 方式 A（推荐，零模型 Key）：接进你已有的 Agent

如果你在用 Codex、Claude Code 或 DeepSeek Harness，**不需要任何 API Key**：PaperPilot
把证据通过 MCP 交给你的 Agent，推理用它自己的模型。

```bash
paperpilot connect --agent deepseek-harness --data-dir ./data
```

这条命令只做一件事：把 `paperpilot` 的 MCP 条目写进该客户端的配置（先备份原文件），
然后提示你重启客户端。重启后在新会话里直接说：

> 用 paperpilot 读这篇论文，讲清方法、实验条件和缺失信息。

其他客户端用导出方式，不改你的配置：

```bash
paperpilot mcp-config --agent claude-code --output mcp.json
```

### 方式 B：用内置 Web 工作台（需要模型 Key）

```bash
docker compose up -d --build --wait
# 打开 http://localhost:8501
```

打开后先看页面顶部：如果是 **MOCK**，系统不会调用模型，你看到的只是检索片段，不是分析
结论。在左侧「接入模型（切到 LIVE）」填入地址、模型名和 Key，写入 `.env` 后重启 API，
刷新页面顶部变成 **LIVE** 才会生成真正的讲解。Live 模式每个任务开始前都会暂停一次，
等你确认是否发送数据。

## 5. 跑一次受控实验（可选，需要 Docker）

```bash
paperpilot schema recipe          # 配方与结果的数据契约
paperpilot inspect recipe.json    # 查看命令、适配器哈希、镜像 ID、预算
paperpilot run recipe.json --approve APPROVAL_DIGEST
```

`inspect` 输出的 `approval_digest` 绑定配方、适配器内容和本地镜像 ID；任何一项变化
都必须重新审阅。运行在无网络、非 root、只读代码的 CPU 容器里。

## 6. 出问题时先看这里

| 现象 | 含义 | 处理 |
|---|---|---|
| `模型输出无法解析为 ...` | 模型两次都没给出合法结构化输出 | 缩小问题范围或减少证据；事件里保留了每次尝试 |
| 状态 `failed`，`error_code=model_output_invalid` | 同上，来自 Web 接口 | 查看任务事件的 `model_response` 记录 |
| `批准摘要不匹配` | 配方、适配器或镜像变了 | 重新 `inspect` 并核对内容 |
| 报告明显偏短 | 可能触发了截断降级 | 检查事件里的 `finish_reason` |
| 检索结果不相关 | 词面检索对跨语言不敏感 | 查询里补上英文方法名和标识符 |

## 7. 边界（读一次，免得后面踩坑）

- PDF 只支持可提取文字，最多 150 页，无 OCR。
- 仓库索引最多 24 个文件、每文件前 100 KB、总计 2 MB，不是全仓覆盖。
- Runner 只支持 Linux CPU 容器、无 GPU、无网络；时间上限 30 分钟。
- 结果比较按提交的协议文本判断可比性，不证明协议声明为真。
- 单用户工作区，无登录与租户隔离；不要把无鉴权实例暴露到公网。
  必须对外时，设置 `PAPERPILOT_API_TOKEN`，除 `/health`、`/metrics` 外的接口都会要求
  `Authorization: Bearer <token>`。

对应实现与测试见 [架构](architecture.md)、[复现流程](reproduction.md)、[测试](testing.md)。