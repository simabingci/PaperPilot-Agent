# 测试与运行验证

## 离线测试

在项目虚拟环境中安装开发依赖后运行：

```bash
python -m pip install -r requirements.lock
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check .
```

测试使用临时数据库和模型替身，不需要模型密钥或外网。覆盖范围包括：

- PDF 解析、物理页码、分块与检索。
- GitHub 地址校验、固定 commit、文件采样和截断边界。
- MCP 进程内调用和真实 stdio 客户端通信。
- 三类内置 Skill 加载、提示使用及工具约束。
- 联合检索同时包含论文和代码；文件过滤不丢弃论文证据。
- 方法映射必须同时引用论文与代码，调换来源类型会被拒绝。
- LangGraph 多步工具执行、确认拒绝和 checkpoint 恢复。
- 非法引用的一次纠正与最终拒绝、模型错误直接失败。
- FastAPI 来源导入、任务状态与 Markdown 下载。
- 实验协议、单位、缺失指标、未知条件、smoke 与容差比较。
- 配方批准摘要绑定适配器、镜像及预算；变化后旧摘要不可执行。
- Runner 下载失败、超时、缺失指标时保留失败记录，不生成成功对照。
- 结果导入绑定工作区 commit，持久化并由 API 重新计算对照。
- 本地 CLI 记录结果不依赖 Web/模型；已导入指标通过 MCP 进入图的可引用证据。

模型替身验证工作流契约，不代表真实模型的分析质量。CI 在 Windows、Linux
及 Python 3.12、3.13 上执行测试，并构建、启动 Docker 服务检查健康状态。
最新结果见 [GitHub Actions](https://github.com/simabingci/PaperPilot-Agent/actions/workflows/ci.yml)。

## 示例输入

[原创示例 PDF](../examples/retrieval-study.pdf) 是两页教育测试材料，
不是发表过的科研成果。预期事实见 [examples/expected.md](../examples/expected.md)。
安装开发依赖后，可用 `python scripts/make_example.py` 重新生成。

启动默认 Mock 模式的 API 后运行：

```bash
python scripts/smoke.py
```

该脚本上传示例 PDF、访问公开的 `pallets/click` 仓库并提交任务，需要网络。
Mock 模式仍执行真实导入、检索和 MCP 调用，输出明确标记为证据预览。
已运行的 Live 示例见 [PDF 报告](examples/paper-report.md) 和
[仓库报告](examples/repository-report.md)。示例报告不保证后续模型输出逐字相同。

## Live 与浏览器检查

按 [部署说明](deployment.md) 配置模型并重启 API。打开 Web 页面后：

1. 上传示例 PDF，提问“实验使用什么优化器和学习率？”。
2. 发起任务并确认向配置的模型服务发送内容。
3. 检查计划、工具事件、完成状态及原始来源。优化器应为 Adam，学习率为 0.001，来源在第 2 页。
4. 下载 Markdown，核对报告引用与页面证据一致。
5. 导入公开 GitHub 仓库，检查报告的固定 commit、文件路径和行号。

Live 检查会调用实际模型，可能产生费用。引用存在性检查不等于人工核实结论，
应另外抽查报告是否忠实表达原文。Ollama 配置兼容，但尚未对具体本地模型完成实机验证。

## 容器检查

```bash
docker compose up -d --build --wait
curl --fail http://localhost:8000/health
curl --fail http://localhost:8501/_stcore/health
docker compose logs --tail=80
docker compose down
```

停止容器默认保留命名数据卷。完整端到端验证还需执行上述浏览器步骤；健康检查
本身只能证明服务已就绪。项目尚无高并发容量或检索质量基准。

## 联合工作区与实际实验

使用 [TCN 案例](../examples/tcn-adding/README.md) 验证真实论文、作者代码和
实际数值。案例运行与离线 pytest 分开，需 Docker 镜像和一次具体执行批准。
原始结果保存在案例的 results/，完整训练未执行。

Web 中将两种材料关联为工作区，确认模型数据传输，检查联合报告包含方法映射
和目标实验；对每条映射核对 PDF 页码和代码行号。再上传案例的
`comparison-input.json`，确认 commit 匹配且显示“不可直接比较”，原因包含
split、training_budget 和 smoke 范围。下载报告后与原始 metrics.json 对照。

可运行 `paperpilot evidence --study ID --query "Adding Prob. 600 loss Table 4"`
验证已有 Agent 的无额外模型 API 路径；返回应同时有 paper 和 repository 证据。
文件定向检索可加 `--code-path TCN/adding_problem/add_test.py`。

测试替身覆盖失败分支；真实 TCN CPU 运行验证成功生命周期。不能把其中任意一项
单独当作任意恶意代码隔离、所有论文可复现或模型结论正确的证明。
