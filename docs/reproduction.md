# 从论文到实验结果

## 选择入口

已有 Agent 可读取 [复现 Skill](../agent-skills/paperpilot-reproduce/SKILL.md)，
使用 CLI 的联合证据、配方与比较能力，无需额外模型 key。希望直接在页面完成
联合讲解时，启动 API/Web，配置 Live 模型；Mock 只显示真实证据预览。

## 1. 建立联合工作区

```bash
paperpilot init --pdf paper.pdf --repo https://github.com/owner/repo --title "目标实验"
paperpilot evidence --study STUDY_ID --query "method dataset split preprocessing training evaluation"
```

可以指定 `--commit`。若使用非默认数据目录，写作 `paperpilot --data-dir PATH init ...`。
Web 中选择已导入的论文和代码，建立工作区可得到相同结构。CLI 的 SQLite 在主机，
Compose 的 SQLite 在容器数据卷，二者默认是独立工作区；不要混用它们的 ID。

MCP 配置示例（将路径换成实际绝对路径）：

```json
{
  "mcpServers": {
    "paperpilot": {
      "command": "/absolute/venv/bin/python",
      "args": ["-m", "paperpilot.mcp_server"],
      "env": {"PAPERPILOT_MODE": "mock", "PAPERPILOT_DATA_DIR": "/absolute/workspace/data"}
    }
  }
}
```

Windows 将 command 替换成虚拟环境的 `Scripts/python.exe`。不同 Agent 的 MCP
配置容器格式可能不同；以上为工具定义示例，工具参数以 server/discover 为准。

## 2. 讲解与实验目标

先确认要复现哪张表或哪项评估，再阅读联合证据。记录方法→函数/类/配置的映射，
分别引用论文与代码。核对数据、划分、预处理、模型变体、训练预算和指标定义。
论文未提供、仓库未覆盖或当前未读到的信息均列为未知，不能由模型自动补齐。

Web 输出结构化 StudyReport 与 Markdown，包括方法映射、实验目标和命令草案。
已有 Agent 可以根据 CLI 证据生成同类说明。草案命令没有执行，不应当作已验证命令。

## 3. 准备配方与环境

```bash
paperpilot schema recipe
paperpilot schema result
```

按 Schema 创建 recipe.json 和相对路径的 Python 适配器。适配器挂载为
`/recipe/adapter.py`，作者仓库挂载为 `/workspace`。适配器运行真实算法并将指标
写到 `/output/metrics.json`，同时声明这次真正使用的协议。参考
[TCN 配方](../examples/tcn-adding/recipe.json) 与
[适配器](../examples/tcn-adding/adapter.py)。

环境依赖预先放入本地 Docker 镜像。Runner 无网络且不安装依赖；需要数据或权重
的项目应在审阅后的镜像构建中准备，或编写显式的数据准备方案。当前 Runner 不提供
额外主机数据卷、GPU 或任意容器选项，不能直接适配所有大规模论文。

## 4. 审阅与运行

```bash
paperpilot inspect recipe.json
paperpilot run recipe.json --approve APPROVAL_DIGEST
```

批准摘要绑定配方、适配器内容和本地镜像 ID。改动后需要重新审阅。预算包括
墙钟时间、CPU 和内存；超时会终止容器。仓库快照压缩后最多 20 MB、解压后最多
100 MB / 10000 文件。时间预算约束容器阶段，不含下载与镜像构建。

主机 Runner 与 Web 独立运行。代码只读，临时目录和输出目录可写；不要给 Web
挂载 Docker socket。Docker 限制降低误操作影响，不能替代对代码和镜像的审查。

## 5. 核对、展示与复用

运行目录默认是 `data/runs/RUN_ID`，保留原始代码快照、审阅内容、日志、指标和 run.json。
成功输出后：

```bash
paperpilot compare data/runs/RUN_ID/comparison-input.json --output data/comparison.md
paperpilot record data/runs/RUN_ID/comparison-input.json --study LOCAL_STUDY_ID
paperpilot attach data/runs/RUN_ID/comparison-input.json --study WEB_STUDY_ID --api http://localhost:8000
```

也可以在 Web 的“实验结果对照”上传同一 JSON。API 要求代码 commit 一致，重新
计算对照并标明外部上传来源；它无法认证外部日志或协议声明的真实性。
record 写入本地工作区，attach 写入 API 工作区；两者不可混用 ID。之后 evidence
或 MCP study_results 会提供最近三条导入对照，供已有 Agent 联合讲解结果。

应分开报告三件事：环境和脚本是否跑通、所声明的协议是否一致、指标是否在事先
确定的容差内。小规模训练即使指标碰巧接近，也不能声称完整复现；多随机种子、
统计评估和更大训练预算需要另行验证。完整示例见
[TCN 案例](../examples/tcn-adding/README.md)。
