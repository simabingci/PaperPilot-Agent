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
- 两类 Skill 加载、提示注入及工具约束。
- LangGraph 多步工具执行、确认拒绝和 checkpoint 恢复。
- 非法引用的一次纠正与最终拒绝、模型错误直接失败。
- FastAPI 来源导入、任务状态与 Markdown 下载。

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
