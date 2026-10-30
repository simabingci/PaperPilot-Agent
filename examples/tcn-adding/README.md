# TCN Adding Problem：作者代码的 CPU 小规模验证

论文：[Bai, Kolter & Koltun, 2018](https://arxiv.org/abs/1803.01271)。
作者代码：[locuslab/TCN](https://github.com/locuslab/TCN)，固定 commit
`2f8c2b817050206397458dfd1f5a25ce8a32fe65`（上游 MIT）。本目录仅包含配方、
适配器和运行说明，不重新打包论文 PDF 或上游代码。

## 目标与范围

PDF 物理第 13 页 Table 4 报告 Adding Problem T=600 的 TCN loss 为 **5.8e-5**。
第 12 页 Table 2 给出对应的 8 层、kernel 8、hidden 24 配置。适配器直接导入
作者的 `TCN.adding_problem.model.TCN` 和 `data_generator`，不改写其模型实现。

这个案例只运行 20 次 Adam 更新，训练集 512、测试集 128，batch 32、lr 0.004，
Torch 与 NumPy seed 均为 1111。完整论文的划分与训练预算未在本配方中确认，
因此 `scope=smoke`，比较必须显示 **不可直接比较**。这是代码运行与指标记录案例，
不是 Table 4 指标复现成功声明。

## 执行

在项目根目录、已安装 PaperPilot 和 Docker 的主机运行：

```bash
docker build -t paperpilot-tcn:cpu examples/tcn-adding
paperpilot inspect examples/tcn-adding/recipe.json
# 审阅批准后，复制 inspect 输出的完整 approval_digest：
paperpilot run examples/tcn-adding/recipe.json --approve APPROVAL_DIGEST
paperpilot compare data/runs/RUN_ID/comparison-input.json --output data/tcn-comparison.md
```

镜像使用 Python 3.12、NumPy 2.5.0、PyTorch 2.6.0 CPU wheel，不安装 CUDA。
构建需要互联网。Docker Hub 不可达时可指定
`--build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim`；PyPI 索引
可用 `--build-arg PIP_INDEX_URL=...` 配置，PyTorch CPU wheel 来自官方源。

运行批准预算：180 秒墙钟、1 CPU、2 GB 内存；容器无网络、无 GPU。
时间不含镜像构建和快照下载。适配器会保存 metrics.json、training.json，Runner
保存 stdout/stderr、镜像 ID、代码归档哈希及比较输入。种子固定不保证跨硬件逐位一致。

## 已记录的运行

本目录保留一次真实 CPU 运行的 [原始指标](results/metrics.json)、
[训练历史](results/training.json)、[运行记录](results/run.json) 和
[结果对照](results/comparison.md)。20 次更新后的测试 MSE 为
**0.2443082481622696**，论文 Table 4 为 **0.000058**。
由于训练预算和划分未对齐，对照状态为不可直接比较。该数值不作为性能或复现成功声明。

[真实联合模型报告](../../docs/examples/tcn-study-report.md)引用了论文表格、代码及
本次导入结果，实际调用 6 次 MCP 工具、收集 39 条证据。报告保留原始模型输出，
其中命令仍是未执行草案，存在整条命令放在一个数组元素中的格式问题，不能直接
交给 Runner。运行本案例请使用上面已测试的 recipe.json 和 adapter.py。

## 联合讲解

下载论文到本地运行目录后，可以用 CLI 或 Web 关联同一仓库版本：

```bash
paperpilot init --pdf paper.pdf --repo https://github.com/locuslab/TCN \
  --commit 2f8c2b817050206397458dfd1f5a25ce8a32fe65 --title "TCN Adding Problem"
paperpilot evidence --study STUDY_ID --query "Adding Prob. 600 loss Table 4 TemporalConvNet"
```

重点核对 `TCN/tcn.py` 的因果裁剪、指数膨胀卷积和残差，`model.py` 的序列末端回归，
以及 `utils.py` 中两处掩码位置对应的求和目标。读取默认训练脚本时注意：参数默认值
不等于论文 Table 2 的全部实验配置；小规模适配器也不等于原始完整训练脚本。
