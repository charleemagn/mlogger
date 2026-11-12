"""PyTorch: обычный цикл обучения с MLogger. Данные синтетические, скачивать ничего не нужно.

    pip install torch
    pip install ./sdk
    python demo/pytorch_example.py

Работает на любой видеокарте, которую видит PyTorch (CUDA, Apple MPS), и на процессоре.
"""

import torch
from torch import nn

import mlogger

device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
config = {"lr": 1e-3, "batch_size": 256, "epochs": 20, "hidden": 128, "device": device}

torch.manual_seed(0)
x = torch.randn(20_000, 20)
y = (x[:, :5].sum(dim=1) + 0.5 * torch.randn(20_000) > 0).long()
x_train, y_train, x_val, y_val = x[:16_000], y[:16_000], x[16_000:].to(device), y[16_000:].to(device)

model = nn.Sequential(nn.Linear(20, config["hidden"]), nn.ReLU(), nn.Linear(config["hidden"], 2)).to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=config["lr"])
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config["epochs"])
loss_fn = nn.CrossEntropyLoss()

with mlogger.init(project="pytorch-example", config=config, tags=["mlp"], total_steps=config["epochs"],
                  main_metric="val/accuracy") as run:
    for epoch in range(1, config["epochs"] + 1):
        model.train()
        order = torch.randperm(len(x_train))
        total = 0.0
        for i in range(0, len(order), config["batch_size"]):
            idx = order[i:i + config["batch_size"]]
            loss = loss_fn(model(x_train[idx].to(device)), y_train[idx].to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(idx)
        scheduler.step()

        model.eval()
        with torch.no_grad():
            logits = model(x_val)
            val_loss = loss_fn(logits, y_val)
            accuracy = (logits.argmax(dim=1) == y_val).float().mean()

        run.log({"train/loss": total / len(order), "val/loss": val_loss, "val/accuracy": accuracy,
                 "lr": scheduler.get_last_lr()[0]}, step=epoch)
        print(f"epoch {epoch:2d}  val_loss={val_loss.item():.4f}  val_acc={accuracy.item():.4f}")
