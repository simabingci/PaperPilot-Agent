# 在已有 Agent 中读懂论文

主入口是使用者已有的 Agent，网页只用于回顾记录。项目不额外发起模型请求；
已有 Agent 自身的订阅、用量与权限仍按其账户计量。

## 安装与开始

在独立虚拟环境安装本项目，进入自己的科研项目目录，运行：

```bash
paperpilot skill-install
```

默认复制到当前目录 `.agents/skills/paperpilot-study/`，存在同名目录时直接报错，
不覆盖本地修改。显式使用 `--update` 才替换打包的 Skill 文件，并保留其他本地文件。
安装时也记录当前 Python 命令和数据目录，使 Agent 不依赖终端已激活 venv。也可指定 `--dest PATH`。这是项目技能安装，不修改全局 Codex
配置、不配置 Key。新会话中请 Agent 使用 `paperpilot-study`。
Claude Code、DeepSeek Harness、WorkBuddy 通过 `--agent` 选择安装格式，
共用同一学习存储；完整步骤及验收边界见 [Agent 接入](integrations.md)。
参见 [官方 Skills 说明](https://developers.openai.com/codex/skills/)。

为每个科研项目保留稳定的 `--data-dir`，并将数据、笔记加入该项目的 Git 忽略规则。
没有代码时，`init` 不需要 `--repo`：

```bash
paperpilot --data-dir ./data init --pdf paper.pdf --title "目标论文"
paperpilot --data-dir ./data evidence --source SOURCE_ID --query "DDIM method experiments"
paperpilot --data-dir ./data pages --source SOURCE_ID --page 3
paperpilot --data-dir ./data learn start --source SOURCE_ID --goal "理解方法与实验"
```

`evidence` 经真实 MCP 检索，并补充最多3个不同命中页的完整文字；`pages` 返回指定
原物理页的文字和索引块。旧记录缺原件时只返回有重叠的分块并提示关联原件。
`pages --source ID --page N --image-output page.png` 可渲染公式和图表；
`paper-text --source ID --output paper.md` 可导出带页码的完整论文文字。原 PDF
保存在本地 data/pdf/，不上传模型；图像由已有 Agent 的图像阅读能力解释，不声称自带 OCR。

## 一次学习回合

Agent 从原文证据写出一个概念、通俗解释和一个理解题，输出 lesson JSON：

```json
{
  "concept": "本次要理解的概念",
  "explanation": "与具体原文一致的解释，先例子后术语。",
  "question": "一个简短的理解问题？",
  "evidence": [{"chunk_id": "实际检索返回的块ID", "quote": "该块内的精确短摘录"}],
  "assumptions": []
}
```

```bash
paperpilot schema lesson
paperpilot --data-dir ./data learn lesson SESSION --input lesson.json
# 等待使用者实际回答，不自动生成“用户答案”
paperpilot --data-dir ./data learn answer SESSION --answer "使用者真实回答"
paperpilot schema review
paperpilot --data-dir ./data learn review SESSION --input review.json
```

review 包含 `assessment`（understood / needs_review / uncertain）、`feedback`
和 `evidence`。未完成回答和反馈前，不能追加下一概念；没有理解时可在下一个
回合换例子重讲。反馈来源明确为 Agent 判断，不是客观测得的掌握率。
引用块必须属于当前论文或关联代码，摘录必须存在；这些检查不证明整个讲解正确。

```bash
paperpilot --data-dir ./data learn list
paperpilot --data-dir ./data learn context SESSION
paperpilot --data-dir ./data learn show SESSION
paperpilot --data-dir ./data learn export SESSION --output ./notes.md
paperpilot --data-dir ./data notebook
```

网页默认通过 Streamlit 的 8501 本机端口启动；被占用时可用 `notebook --port 8502`。
原文与当前讲解并排，窄屏上下排列，页码默认定位到当前概念引用页；历史概念、
完整笔记、待复习反馈和实验结果均可查看。旧学习记录可在页面关联同一哈希原件。
需要刷新查看 Agent 新写入的记录。多位同门各自安装、各自保存数据，当前无
多租户、自动同步或同时编辑同一学习会话的冲突合并。

## 没有作者代码时

先讲解，再生成方法实现笔记：模块、输入输出、方程与伪代码、实验目标、缺失
设置和独立实现选择。当前 CLI 不会自动生成网络、下载模型权重或修复训练代码；
这些由使用者与 Agent 在具体研究目录完成。完成后可使用现有配方 Runner 执行。

数据划分、权重和评估设置未确认时，执行成功也不能证明完整复现。实验仍需
具体命令与预算；不为了小实验引入自动修补、通用重试或假成功兜底。


## 一步打开与续学

```bash
paperpilot --data-dir ./data learn start --pdf paper.pdf --goal "理解方法与实验"
paperpilot --data-dir ./data learn context SESSION
# 使用者明确不想回答本题时，保留跳过而不伪造掌握情况：
paperpilot --data-dir ./data learn skip SESSION --reason "先读实验设置"
paperpilot --data-dir ./data notebook --port 8502
```

`paper_page` 和 `learning_context` 也通过现有 MCP Server 对外提供，均为只读操作。
学习反馈仍来自调用方 Agent；工具验证引用与状态，不能代替真实用户教学效果评估。
