"""
지문자 PyTorch 모델 학습 (대안)
================================
실행: python train.py
옵션: python train.py --epochs 150 --lr 5e-4

train_classifier.py (sklearn) 의 PyTorch 대안.
동일한 dataset/ 폴더 데이터를 사용하며
정규화 + 증강을 적용한 MLP 모델을 학습합니다.

저장 결과 (models/):
  fingerspelling_model.pt  : PyTorch 가중치
  label2idx.pkl            : 레이블 → 인덱스
  model_config.pkl         : 모델 구조 정보
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import joblib
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Subset
from torch.utils.tensorboard import SummaryWriter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ai.dataset import FingerspellingDataset
from ai.model import MLPClassifier

INPUT_SIZE = 63  # 21 × 3


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root",  default=str(ROOT / "dataset"))
    p.add_argument("--out-dir",    default=str(ROOT / "models"))
    p.add_argument("--epochs",     type=int,   default=120)
    p.add_argument("--lr",         type=float, default=1e-3)
    p.add_argument("--batch-size", type=int,   default=32)
    p.add_argument("--val-split",  type=float, default=0.2)
    p.add_argument("--seed",       type=int,   default=42)
    return p.parse_args()


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ── 데이터 ───────────────────────────────────────────────────────────
    full_ds = FingerspellingDataset(args.data_root, augment=False)
    if len(full_ds) == 0:
        print("데이터가 없습니다. collect_data.py 를 먼저 실행하세요.")
        sys.exit(1)

    classes = list(full_ds.label2idx.keys())
    print(f"총 샘플: {len(full_ds)}  |  클래스({len(classes)}): {classes}")

    all_indices = list(range(len(full_ds)))
    all_labels  = [full_ds.samples[i][1] for i in all_indices]

    try:
        train_idx, val_idx = train_test_split(
            all_indices, test_size=args.val_split,
            stratify=all_labels, random_state=args.seed,
        )
    except ValueError:
        train_idx, val_idx = train_test_split(
            all_indices, test_size=args.val_split, random_state=args.seed,
        )

    aug_ds    = FingerspellingDataset(args.data_root, augment=True)
    train_ds  = Subset(aug_ds,  train_idx)
    val_ds    = Subset(full_ds, val_idx)
    print(f"Train: {len(train_ds)}  |  Val: {len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False, num_workers=0)

    # ── 모델 ─────────────────────────────────────────────────────────────
    num_classes = len(full_ds.label2idx)
    model       = MLPClassifier(INPUT_SIZE, num_classes).to(device)
    optimizer   = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    criterion   = nn.CrossEntropyLoss()
    scheduler   = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_dir = ROOT / "runs" / time.strftime("%Y%m%d-%H%M%S")
    writer  = SummaryWriter(log_dir=str(log_dir))

    best_val_acc = 0.0
    patience, wait = 15, 0

    # ── 학습 루프 ────────────────────────────────────────────────────────
    for epoch in range(1, args.epochs + 1):
        model.train()
        t_loss, t_correct, t_total = 0.0, 0, 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb)
            loss   = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            t_loss    += loss.item() * len(xb)
            t_correct += (logits.argmax(1) == yb).sum().item()
            t_total   += len(xb)
        scheduler.step()

        model.eval()
        v_loss, v_correct, v_total = 0.0, 0, 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                logits  = model(xb)
                v_loss    += criterion(logits, yb).item() * len(xb)
                v_correct += (logits.argmax(1) == yb).sum().item()
                v_total   += len(xb)

        train_acc = t_correct / t_total
        val_acc   = v_correct / v_total

        writer.add_scalar("loss/train", t_loss / t_total, epoch)
        writer.add_scalar("loss/val",   v_loss / v_total, epoch)
        writer.add_scalar("acc/train",  train_acc,        epoch)
        writer.add_scalar("acc/val",    val_acc,          epoch)

        print(f"Epoch {epoch:3d}/{args.epochs} | "
              f"train_acc={train_acc:.4f} | val_acc={val_acc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            wait = 0
            torch.save(model.state_dict(), str(out_dir / "fingerspelling_model.pt"))
            joblib.dump(full_ds.label2idx, str(out_dir / "label2idx.pkl"))
            joblib.dump({"input_size": INPUT_SIZE, "num_classes": num_classes},
                        str(out_dir / "model_config.pkl"))
            print(f"  -> 모델 저장 (val_acc={val_acc:.4f})")
        else:
            wait += 1
            if wait >= patience:
                print("Early stopping")
                break

    writer.close()
    print(f"\n학습 완료. 최고 val_acc: {best_val_acc:.4f}")
    print(f"TensorBoard: tensorboard --logdir {log_dir}")


if __name__ == "__main__":
    main()
