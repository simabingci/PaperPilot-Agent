# 接入已有 Agent

PaperPilot 不绑定模型供应商。已有 Agent 负责解释与反馈，本地 Python 工具负责
索引、原页、学习记录与结果比较。下面是本地桌面/命令行客户端接入，不是远程云服务。
先按 README 安装 Python 包，在自己的科研项目目录、已激活的虚拟环境中执行命令。

## 选择入口

| 客户端 | Skill 安装方式 | 可选 MCP 配置 | 验证范围 |
|---|---|---|---|
| Codex | `.agents/skills/paperpilot-study` | CLI 内部调用 MCP；无需另配 | 已有本地学习记录与阅读页验收 |
| Claude Code | `.claude/skills/paperpilot-study` | `mcpServers` JSON 片段 | 安装路径、运行命令、真实 stdio 工具调用；未做原生客户端对话验收 |
| DeepSeek Harness | `.dsh/skills/paperpilot-study` | `dsh-mcp-client` YAML 插件项 | 同上；需宿主启用 filesystem skills/MCP 插件 |
| WorkBuddy | 本机生成 Skill ZIP，在客户端上传 | `mcpServers` JSON 片段 | ZIP 布局与元信息、运行命令、真实 stdio 工具调用；未做原生客户端导入验收 |
| 其他 Agent | 指定目录或显式读取 SKILL.md | 通用 stdio JSON 片段 | 取决于宿主能否读取本地文件、执行 Python 和接入 stdio MCP |

各配置导出的启动参数已由 Python MCP 客户端实际调用，不等于三种原生客户端均已实机验收。
不承诺所有版本、所有 Agent 自动兼容。Skill 不支持任意纯网页聊天窗口自动访问本机。

## 安装教学 Skill（推荐）

为同一科研项目保持同一个数据目录，换客户端时即可继续读到当前问题、回答和反馈：

```bash
# 选择你实际使用的一项；不是全部都要安装
paperpilot --data-dir ./data skill-install --agent codex
paperpilot --data-dir ./data skill-install --agent claude-code
paperpilot --data-dir ./data skill-install --agent deepseek-harness
paperpilot --data-dir ./data skill-install --agent workbuddy
```

Codex 新开该项目会话；Claude Code 可输入 `/paperpilot-study`；Harness 在项目根目录
启动，filesystem skills 插件会扫描 `.dsh/skills`（也支持 `.agents/skills`）。自定义
Harness 组合需要 `@deepseek-ai/dsh-skill` 和 `@deepseek-ai/dsh-skill-filesystem`。
安装返回的路径含 `references/runtime.json`，绑定当前 Python 和绝对数据路径。
移动虚拟环境或数据目录后，使用同样的安装命令加 `--update` 更新绑定。

WorkBuddy 命令返回 `data/integrations/workbuddy/skills/paperpilot-study.zip` 的绝对路径。
在 WorkBuddy 的“技能 → 添加技能 → 上传技能”选择该 ZIP。它是当前机器的本地包，
包含机器路径，不应发布到市场或提交 Git；其他同门在各自机器生成。
运行 Python 的权限仍由客户端管理。未启用本地命令执行时，只加载指令不能保存进度。

其他客户端可用 `skill-install --agent generic --dest ./data/my-agent/skills`，
再通过宿主的 Skill 入口加载，或明确让 Agent 读取生成的 `paperpilot-study/SKILL.md`。

统一请求示例：

> 使用 paperpilot-study 带我读 paper.pdf。一次讲一个概念，用原文页码和摘录支撑；
> 问一个理解题，等我实际回答后再继续，保存学习记录。先恢复已有进度。

图表解释还依赖宿主模型的图片阅读能力；纯文本模型可以检索文字，不能据此声称已读懂图像。
CLI 不发起模型请求，但宿主 Agent 会读取检索内容并交给其模型，遵守该客户端的数据规则。

## 直接挂载 MCP（可选）

Skill + CLI 已经通过 MCP 检索，无需重复配置。想让工具直接出现在客户端列表时，再导出：

```bash
paperpilot --data-dir ./data mcp-config --agent claude-code --output ./data/claude-mcp.json
paperpilot --data-dir ./data mcp-config --agent deepseek-harness --output ./data/harness-mcp.yaml
paperpilot --data-dir ./data mcp-config --agent workbuddy --output ./data/workbuddy-mcp.json
paperpilot --data-dir ./data mcp-config --agent generic --output ./data/generic-mcp.json
```

导出只创建新文件，已有文件会报错，不覆盖客户端配置或读取其中的凭据。
配置含绝对 Python、UTF-8 参数和数据目录，不含 API Key。更换机器需重新生成。

- **Claude Code**：把 JSON 中 `mcpServers.paperpilot` 合并进项目 `.mcp.json` 的
  `mcpServers`，保留其他服务器；按客户端提示确认项目配置，用 `/mcp` 查看状态。
- **Harness**：导出的是 YAML 插件列表项，追加到当前 agent/profile 的插件列表，
  不要覆盖整个 profile。宿主需安装 `@deepseek-ai/dsh-mcp-client`，工具名为
  `mcp__paperpilot__paper_search` 等。不同 Harness 发行版的配置入口可能不同。
- **WorkBuddy**：在自定义 MCP 的 JSON 配置入口合并 `paperpilot` 条目；使用本地
  stdio，不需要额外模型 Key。不提供或发布连接器市场包，也不自动安装 Python。

连接后让 Agent 调用 `list_sources`，再以返回的真实 source ID 调用 `paper_search`
或 `paper_page`；空列表说明所选数据目录尚未导入材料，不能编造分析结果。
使用 `paperpilot --data-dir ./data learn start --pdf paper.pdf --goal "理解方法"` 导入。

MCP 有 8 个只读工具：source_overview、paper_search、code_search、study_search、
list_sources、study_results、paper_page、learning_context。**仅挂 MCP 不会自动导入论文、
写入学习记录或运行实验。** 完整教学需要 Skill + CLI，实验继续使用已审阅配方和具体批准。
不要在两个客户端同时推进同一个学习会话；这里支持顺序切换，不提供多写者协作协调。

本地 stdio 的 Python、PDF 和数据库必须位于客户端实际运行命令的机器。服务器上的
项目不会因为生成了本地配置而自动被另一台电脑访问；本版不暴露公网 MCP 端点。

## 官方接口依据

适配时核对的接口：

- [Claude Code Skills](https://code.claude.com/docs/en/skills) 和 [MCP](https://code.claude.com/docs/en/mcp)。
- [Harness 文件系统 Skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.zh.md)
  和 [MCP 客户端插件](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.zh.md)。
- [WorkBuddy 技能上传](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、
  [Skill 结构](https://open.workbuddy.cn/docs/skill) 和 [MCP 配置](https://open.workbuddy.cn/docs/connector)。
