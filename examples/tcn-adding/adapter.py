"""Run the authors' unchanged TCN/model/data generator with a documented tiny CPU budget."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

sys.path.insert(0, "/workspace")
from TCN.adding_problem.model import TCN  # noqa: E402
from TCN.adding_problem.utils import data_generator  # noqa: E402

torch.set_num_threads(1)
torch.manual_seed(1111)
np.random.seed(1111)
model = TCN(2, 1, [24] * 8, kernel_size=8, dropout=0.0)
optimizer = torch.optim.Adam(model.parameters(), lr=0.004)
train_x, train_y = data_generator(512, 600)
test_x, test_y = data_generator(128, 600)
history = []
model.train()
for step in range(20):
    start = (step * 32) % 512
    optimizer.zero_grad()
    loss = F.mse_loss(model(train_x[start:start + 32]), train_y[start:start + 32])
    loss.backward()
    optimizer.step()
    history.append(float(loss.detach()))
    print(json.dumps({"step": step + 1, "training_mse": history[-1]}), flush=True)
model.eval()
with torch.no_grad():
    predictions = torch.cat([model(test_x[i:i + 16]) for i in range(0, 128, 16)])
    mse = float(F.mse_loss(predictions, test_y))
output = Path(os.environ["PAPERPILOT_OUTPUT_DIR"])
protocol = dict(dataset="Adding Problem, sequence length 600",
    split="512 train / 128 held-out generated sequentially; torch and numpy seed 1111",
    preprocessing="Two uniform values selected by a binary mask; sum as target",
    model="TCN, kernel 8, 8 levels, 24 hidden channels, dropout 0",
    training_budget="20 Adam updates, batch 32, learning rate 0.004, CPU",
    evaluation="Mean squared error on held-out synthetic sequences")
(output / "metrics.json").write_text(json.dumps(dict(protocol=protocol, metrics={"mse": mse}, units={"mse": "MSE"}),
                                               indent=2), encoding="utf-8")
(output / "training.json").write_text(json.dumps(dict(training_mse=history, torch=torch.__version__,
    numpy=np.__version__, parameters=sum(p.numel() for p in model.parameters()), seed=1111), indent=2), encoding="utf-8")
print(json.dumps({"test_mse": mse, "scope": "smoke", "not_full_reproduction": True}), flush=True)
