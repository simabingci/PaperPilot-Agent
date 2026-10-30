# TCN 论文与代码联合解读：Adding Problem T=600 的 Table 4 指标、实现映射与导入实测对比

> 运行模式：LIVE / 模型分析
> 引用经过存在性校验；结论是否被原文支持仍需人工核对。

任务：联合讲解论文和代码，说明方法对应的类、函数和配置，并列出不能确认的对应关系。
聚焦 Adding Problem T=600：先用独立查询 Table 4 Adding Prob. 600 loss 获取论文精确指标，再读取 TCN/tcn.py、TCN/adding_problem/model.py 和 add_test.py 的相关实现。结合 study_results 已导入的实测指标，讲清方法与代码对应关系，比较训练预算、划分和 MSE。不得把仓库默认参数写成论文完整设置，未检索到的信息标为未知，保留不可直接比较结论。

Skill：`paper-reproduction`

## 研究范围与证据边界

本报告基于论文 tcn-paper.pdf（14 页，sha256 f7e5df08…）与 locuslab/TCN 仓库 commit 2f8c2b817050206397458dfd1f5a25ce8a32fe65；仓库检查范围最多 24 个主要文本文件、每文件前 100 KB、总计 2 MB，且不执行仓库代码。 [S1]

论文是 Bai、Kolter、Koltun 的《An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence Modeling》，作者在文中给出代码地址 http://github.com/locuslab/TCN。 [S2] [S3]

仓库 README 说明实验用 PyTorch 完成，并建议 PyTorch v1.0.0 以上（强烈推荐 v>1.3.0），旧版本不再支持。 [S5]

README 列出 Adding Problem 在 T=200、400、600 上评估，并说明每个任务目录含 data/、[TASK_NAME]_test.py、models.py、utils.py，运行 [TASK_NAME]_test.py 即可，超参数通过命令行参数指定。 [S6] [S7]

## Table 4 的 Adding Problem T=600 精确指标

Table 4（PDF 第 13 页）给出 Adding Prob. 600 (loss) 的 TCN 结果为 5.8e-5，模型规模 70K；同表 SoTA 为 Regularized GRU 的 5.3e-5，规模同为 70K。 [S8]

Table 2（PDF 第 12 页）给出 Adding Problem T=600 的 TCN 设置：k=8、n=8、Hidden=24、Dropout 0.0、Grad Clip N/A；T=200 为 k=6、n=7、Hidden=27，T=400 为 k=7、n=7、Hidden=27。 [S10]

Figure 2(b)（PDF 第 7 页）标注 T=600 的 TCN 为 8x24, k=8 (70K)，与 Table 2 的 k=8、n=8、Hidden=24 一致；正文说明所有模型规模约 70K。 [S9]

Table 3（PDF 第 13 页）给出 Adding Problem T=600 的 LSTM 设置（1 层、Hidden 130、Grad Clip 5、Bias 1.0），与 TCN 设置分表列出。 [S8]

论文对 adding problem 的定义：输入为长度 n、深度 2 的序列，第一维为 [0,1] 随机值，第二维除两个标记为 1 的元素外全为 0，目标是求和这两个被标记的随机值；全部预测为 1 的 MSE 约为 0.1767。 [S26]

## 方法与代码的对应（含不确定项）

论文的 TCN 由因果卷积（1D FCN + 零填充 kernel size−1）与膨胀卷积构成，膨胀使感受野指数增长；残差块含两层膨胀因果卷积、ReLU、权重归一化和空间 dropout，维度不匹配时加 1x1 卷积。 [S17] [S18] [S20] [S32]

adding_problem/model.py 中的 TCN 类调用 TCN.tcn.TemporalConvNet(input_size, num_channels, kernel_size, dropout)，再接 nn.Linear(num_channels[-1], output_size)，forward 只取最后时间步 y1[:, :, -1] 做线性映射。 [S30]

add_test.py 以 input_channels=2、n_classes=1 构造模型，channel_sizes = [args.nhid]*args.levels，kernel_size=args.ksize，dropout=args.dropout，优化器由 getattr(optim, args.optim) 按名称创建。 [S34]

训练循环对每个 batch 计算 F.mse_loss(output, y)，反向传播后若 args.clip > 0 则做梯度裁剪，再 optimizer.step()；评估函数在 model.eval() 与 torch.no_grad() 下对 X_test 计算 F.mse_loss 并打印平均 loss。 [S36] [S38]

数据由 data_generator(50000, seq_length) 生成训练集、data_generator(1000, seq_length) 生成测试集，torch.manual_seed(args.seed) 固定随机种子。 [S34]

## 仓库默认参数与论文设置的差异

add_test.py 的 argparse 默认值为：batch_size=32、dropout=0.0、clip=-1（不裁剪）、epochs=10、ksize=7、levels=8、seq_len=400、lr=4e-3、optim=Adam、nhid=30、seed=1111；这些是代码默认值，不等于论文 T=600 的完整实验协议。 [S35] [S37]

论文 Table 2 的 T=600 设置为 k=8、n=8、Hidden=24、Dropout 0.0、Grad Clip N/A；代码默认 ksize=7、levels=8、nhid=30、seq_len=400，与论文 T=600 的 k=8、Hidden=24、T=600 不一致，需显式传参才能对齐。 [S10] [S35] [S37]

论文未在已检索证据中给出 T=600 的 batch size、学习率、优化器、训练迭代/epoch 预算与数据划分；这些在代码中由默认值或命令行参数决定，不能据代码默认值反推论文完整设置。 [S10] [S35] [S37]

## 导入实测结果与不可直接比较结论

导入结果（外部提交，API 未认证执行）记录 scope=smoke：Adding Problem 序列长度 600，模型为 TCN、kernel 8、8 levels、24 hidden channels、dropout 0，20 次 Adam 更新、batch 32、lr 0.004、CPU。 [S39]

该提交的划分是 512 训练 / 128 留出、顺序生成、torch 与 numpy 种子 1111；预处理为两个均匀随机值由二值掩码选出、求和为目标；评估为留出合成序列上的 MSE。 [S39]

对比行显示 MSE：论文 5.8e-5，实测 0.2443082481622696，delta 0.2442502481622696，容差 1e-5，方向 lower，状态 not_comparable，原因包括实验协议不一致或存在未确认项、本次仅为小规模流程验证。 [S39]

提交记录的协议差异为：split 论文 unknown、实际 512/128；training_budget 论文 unknown、实际 20 次 Adam 更新；comparable=false，结论为按提交协议与容差比较、不能单独证明论文已完整复现。 [S39]

该实测是小规模 smoke 流程验证，不能标注为复现论文结果；上传的运行元数据是提交者的声明，保留其 provenance 与 not_comparable 状态。 [S39]

## 实验目标与命令（未执行建议）

论文 Table 4 的 Adding Prob. 600 (loss) 指标为 MSE 5.8e-5，位于 PDF 第 13 页；架构设置见 Table 2（PDF 第 12 页）。 [S8] [S10]

仓库说明运行 add_test.py 即可跑 Adding Problem，超参数通过命令行参数指定，可用 -h 查看。 [S7]

代码默认 seq_len=400、ksize=7、nhid=30，与论文 T=600 的 k=8、Hidden=24 不同；对齐论文设置需显式传 --seq_len 600 --ksize 8 --nhid 24 --levels 8 --dropout 0.0，但论文的 batch size、学习率、优化器与训练预算在已检索证据中未知。 [S10] [S35] [S37]

## 论文方法 → 代码实现

### TCN 主干：膨胀因果卷积 + 残差块

论文描述 TCN 为 1D FCN + 因果卷积，用膨胀卷积扩大感受野，残差块含两层膨胀因果卷积、ReLU、权重归一化与空间 dropout，维度不匹配时用 1x1 卷积。代码中 TCN/adding_problem/model.py 的 TCN 类调用 TCN.tcn.TemporalConvNet 实现主干，再接线性层输出。论文未在已检索证据中逐行给出 TemporalConvNet 内部实现，故类内细节（如权重归一化、1x1 卷积的具体写法）属于未完全核对的对应。 [S17] [S20] [S32] [S30]

### 输出头：只取最后时间步

论文的 adding problem 目标是标量求和，代码 TCN.forward 返回 self.linear(y1[:, :, -1])，即只对最后时间步的通道做线性映射得到单值输出；这与论文任务定义（输出一个和）方向一致，但论文未明确说明输出头只取最后时间步，属于合理但未逐字确认的对应。 [S26] [S30]

### 损失函数：MSE

论文以 MSE 报告 Adding Prob. 600 (loss) 5.8e-5；代码训练循环用 F.mse_loss(output, y)，评估函数同样用 F.mse_loss 对 X_test 计算平均 loss。两者在损失形式上对应，但论文未说明其评估是在测试集还是验证集上计算，代码用 X_test。 [S8] [S26] [S36] [S38]

### 超参数：k、levels、hidden、dropout

论文 Table 2 给出 T=600 的 k=8、n=8、Hidden=24、Dropout 0.0；代码通过 --ksize、--levels、--nhid、--dropout 传入，channel_sizes=[args.nhid]*args.levels。代码默认值为 ksize=7、levels=8、nhid=30、dropout=0.0，与论文 T=600 不一致，需显式传参；论文的 batch size、学习率、优化器在已检索证据中未知，不能与代码默认值 Adam、lr=4e-3 直接等同。 [S10] [S34] [S35] [S37]

### 数据生成与划分

论文定义 adding problem 为长度 n、深度 2 的序列，第二维两个 1 标记待求和元素，全猜 1 的 MSE 约 0.1767；代码 data_generator(50000, seq_length) 生成训练、data_generator(1000, seq_length) 生成测试，并用 torch.manual_seed(args.seed) 固定种子。论文未在已检索证据中给出训练/测试样本数与划分比例，故样本量对应关系未确认。 [S26] [S34]

## 实验目标与运行草案

> 以下命令尚未执行；需核对环境与数据后单独批准。

### Adding Problem T=600，论文 Table 4 报告值

数据与划分：Adding Problem，序列长度 T=600；论文未在已检索证据中给出训练/测试划分细节

论文指标：MSE (loss) = 5.8e-05 MSE；PDF 第 13 页 Table 4：Adding Prob. 600 (loss)，TCN 5.8e-5，70K；架构见 PDF 第 12 页 Table 2

```json
["python TCN/adding_problem/add_test.py --seq_len 600 --ksize 8 --levels 8 --nhid 24 --dropout 0.0"]
```

缺失条件：论文 T=600 的 batch size、学习率、优化器、训练迭代/epoch 预算未在已检索证据中给出；论文训练/测试划分与样本数未在已检索证据中给出；论文是否使用梯度裁剪在 Table 2 中记为 N/A，但代码默认 clip=-1（不裁剪），需确认；该命令为未执行建议，需在 PyTorch v1.0.0+ 环境运行

[S8] [S10] [S35] [S37]

### Adding Problem T=600，导入的 smoke 实测

数据与划分：512 训练 / 128 留出，顺序生成，torch 与 numpy 种子 1111

论文指标：MSE = 5.8e-05 MSE；PDF 第 13 页 Table 4（对比基准）；实测见导入结果 6b1c86f46e7343048bc557bfb2165007

```json
["python TCN/adding_problem/add_test.py --seq_len 600 --ksize 8 --levels 8 --nhid 24 --dropout 0.0 --batch_size 32 --lr 0.004 --optim Adam --epochs 1"]
```

缺失条件：该实测为外部提交、API 未认证执行，不能作为论文复现证据；20 次 Adam 更新远小于论文训练预算（论文预算未知）；512/128 划分与论文划分（未知）不同；实测 MSE 0.2443 与论文 5.8e-5 状态为 not_comparable，不可直接比较

[S39] [S8]

## 缺失信息与边界


## 来源与分析范围

```json
{
  "paper_id": "230463be2790449a8d7b82f3611f620f",
  "repository_id": "a7912f7bd7f84b82aa608be4f7eb6d0c",
  "objective": "Table 4 Adding Problem T=600；讲解论文与代码，核对完整实验与 20 步 CPU 小规模运行的差异。",
  "paper": {
    "filename": "tcn-paper.pdf",
    "pages": 14,
    "sha256": "f7e5df08b234f1c395ff4f7b3597b28f170fc9d70af388be5b645bfc4456f42b",
    "ocr": false
  },
  "repository": {
    "repository_url": "https://github.com/locuslab/TCN",
    "commit": "2f8c2b817050206397458dfd1f5a25ce8a32fe65",
    "description": "Sequence modeling benchmarks and temporal convolutional networks",
    "license": "MIT",
    "files": [
      "README.md",
      "TCN/__init__.py",
      "TCN/tcn.py",
      "TCN/adding_problem/add_test.py",
      "TCN/adding_problem/model.py",
      "TCN/adding_problem/utils.py",
      "TCN/char_cnn/char_cnn_test.py",
      "TCN/char_cnn/model.py",
      "TCN/char_cnn/utils.py",
      "TCN/copy_memory/copymem_test.py",
      "TCN/copy_memory/model.py",
      "TCN/copy_memory/utils.py",
      "TCN/lambada_language/lambada_test.py",
      "TCN/lambada_language/model.py",
      "TCN/lambada_language/utils.py",
      "TCN/mnist_pixel/model.py",
      "TCN/mnist_pixel/pmnist_test.py",
      "TCN/mnist_pixel/utils.py",
      "TCN/poly_music/model.py",
      "TCN/poly_music/music_test.py",
      "TCN/poly_music/utils.py",
      "TCN/word_cnn/model.py",
      "TCN/word_cnn/utils.py",
      "TCN/word_cnn/word_cnn_test.py"
    ],
    "skipped": [],
    "truncated_files": [],
    "tree_truncated": false,
    "tree": [
      ".gitignore",
      "LICENSE",
      "README.md",
      "TCN/__init__.py",
      "TCN/adding_problem/README.md",
      "TCN/adding_problem/add_test.py",
      "TCN/adding_problem/model.py",
      "TCN/adding_problem/utils.py",
      "TCN/char_cnn/README.md",
      "TCN/char_cnn/char_cnn_test.py",
      "TCN/char_cnn/model.py",
      "TCN/char_cnn/utils.py",
      "TCN/copy_memory/README.md",
      "TCN/copy_memory/copymem_test.py",
      "TCN/copy_memory/model.py",
      "TCN/copy_memory/utils.py",
      "TCN/lambada_language/README.md",
      "TCN/lambada_language/data/lambada_vocabulary_sorted.txt",
      "TCN/lambada_language/lambada_test.py",
      "TCN/lambada_language/model.py",
      "TCN/lambada_language/utils.py",
      "TCN/mnist_pixel/README.md",
      "TCN/mnist_pixel/data/mnist/processed/README.md",
      "TCN/mnist_pixel/data/mnist/raw/t10k-images-idx3-ubyte",
      "TCN/mnist_pixel/data/mnist/raw/t10k-labels-idx1-ubyte",
      "TCN/mnist_pixel/data/mnist/raw/train-images-idx3-ubyte",
      "TCN/mnist_pixel/data/mnist/raw/train-labels-idx1-ubyte",
      "TCN/mnist_pixel/model.py",
      "TCN/mnist_pixel/pmnist_test.py",
      "TCN/mnist_pixel/utils.py",
      "TCN/poly_music/README.md",
      "TCN/poly_music/mdata/JSB_Chorales.mat",
      "TCN/poly_music/mdata/MuseData.mat",
      "TCN/poly_music/mdata/Nottingham.mat",
      "TCN/poly_music/mdata/Piano_midi.mat",
      "TCN/poly_music/model.py",
      "TCN/poly_music/music_test.py",
      "TCN/poly_music/utils.py",
      "TCN/tcn.py",
      "TCN/word_cnn/README.md",
      "TCN/word_cnn/data/penn/corpus",
      "TCN/word_cnn/data/penn/test.txt",
      "TCN/word_cnn/data/penn/train.txt",
      "TCN/word_cnn/data/penn/valid.txt",
      "TCN/word_cnn/model.py",
      "TCN/word_cnn/utils.py",
      "TCN/word_cnn/word_cnn_test.py"
    ],
    "total_files": 47,
    "archive_bytes": 16960767,
    "transport": "GitHub API + commit-pinned codeload ZIP, in-memory reads",
    "scope": "最多 24 个主要文本文件、每文件前 100 KB、总计 2 MB；大文件截取明确记录；不执行仓库代码"
  }
}
```

- [S1] 来源元数据（页数、版本和采样范围；不是正文页码）
- [S2] PDF 第 1 页
- [S3] PDF 第 1 页
- [S4] PDF 第 1 页
- [S5] [README.md:L1-L21](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/README.md#L1-L21)
- [S6] [README.md:L21-L41](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/README.md#L21-L41)
- [S7] [README.md:L39-L51](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/README.md#L39-L51)
- [S8] PDF 第 13 页
- [S9] PDF 第 7 页
- [S10] PDF 第 12 页
- [S11] PDF 第 7 页
- [S12] PDF 第 4 页
- [S13] [TCN/lambada_language/lambada_test.py:L160-L184](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/lambada_language/lambada_test.py#L160-L184)
- [S14] [TCN/char_cnn/char_cnn_test.py:L156-L188](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/char_cnn/char_cnn_test.py#L156-L188)
- [S15] [TCN/char_cnn/char_cnn_test.py:L128-L154](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/char_cnn/char_cnn_test.py#L128-L154)
- [S16] [TCN/word_cnn/word_cnn_test.py:L166-L187](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/word_cnn/word_cnn_test.py#L166-L187)
- [S17] PDF 第 4 页
- [S18] PDF 第 3 页
- [S19] PDF 第 8 页
- [S20] PDF 第 4 页
- [S21] PDF 第 3 页
- [S22] [TCN/word_cnn/utils.py:L68-L88](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/word_cnn/utils.py#L68-L88)
- [S23] [TCN/lambada_language/utils.py:L129-L147](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/lambada_language/utils.py#L129-L147)
- [S24] [TCN/lambada_language/utils.py:L1-L34](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/lambada_language/utils.py#L1-L34)
- [S25] PDF 第 3 页
- [S26] PDF 第 5 页
- [S27] PDF 第 8 页
- [S28] PDF 第 5 页
- [S29] PDF 第 5 页
- [S30] [TCN/adding_problem/model.py:L1-L17](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/model.py#L1-L17)
- [S31] PDF 第 11 页
- [S32] PDF 第 3 页
- [S33] PDF 第 8 页
- [S34] [TCN/adding_problem/add_test.py:L39-L70](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/add_test.py#L39-L70)
- [S35] [TCN/adding_problem/add_test.py:L10-L29](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/add_test.py#L10-L29)
- [S36] [TCN/adding_problem/add_test.py:L69-L98](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/add_test.py#L69-L98)
- [S37] [TCN/adding_problem/add_test.py:L28-L37](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/add_test.py#L28-L37)
- [S38] [TCN/adding_problem/add_test.py:L101-L112](https://github.com/locuslab/TCN/blob/2f8c2b817050206397458dfd1f5a25ce8a32fe65/TCN/adding_problem/add_test.py#L101-L112)
- [S39] 导入结果 6b1c86f46e7343048bc557bfb2165007（外部提交，未认证执行；最多展示最近 3 条）