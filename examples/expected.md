# 可重复运行的示例

`retrieval-study.pdf` 是本项目原创的两页教育测试材料（MIT），不是已发表论文。
其生成器为 `scripts/make_example.py`，需要安装开发依赖。

提问 `What optimizer and learning rate are used?` 时，应检索到第 2 页，
原文包含 Adam、0.001 和 batch size 16。报告必须标明 MOCK 模式（默认配置），
引用真实页码；不得把示例内容当作完成过的科研实验。

公开仓库示例为 `https://github.com/pallets/click`。每次读取默认分支的当前
commit，因此 commit 和内容可能变化。应返回固定 commit 的文件行号链接、
读取文件清单和采样范围；不得声称已运行 Click 或复现其测试。

运行 API 后执行 `python scripts/smoke.py`，保存实际任务和工具记录至被忽略的
`data/smoke.json`。默认不调用付费 API；完整模型分析需要显式切换 live 模式并确认。
