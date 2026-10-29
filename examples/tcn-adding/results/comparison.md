# 实验结果对照

| 指标 | 论文 | 实测 | 单位 | 差值（实测−论文） | 状态 |
|---|---:|---:|---|---:|---|
| mse | 5.8e-05 | 0.2443082481622696 | MSE | 0.2442502481622696 | 不可直接比较 |

## 协议与边界

- split：论文 `unknown`；实测 `512 train / 128 held-out generated sequentially; torch and numpy seed 1111`
- training_budget：论文 `unknown`；实测 `20 Adam updates, batch 32, learning rate 0.004, CPU`
- mse 来源：PDF physical page 13, Table 4: Adding Prob. 600 (loss), TCN 5.8e-5; architecture Table 2, page 12；实验协议不一致或存在未确认项；本次仅为小规模流程验证

按提交的协议与容差比较；不能单独证明论文已经完整复现。
