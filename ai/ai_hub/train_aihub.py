"""
train_aihub.py
==============
팀 수집 데이터(ai/new_word/word_data) + AIHub 데이터(ai/ai_hub/word_data) 병합 학습.

- 팀 데이터: 27개 단어, ~2661개 (MediaPipe Holistic)
- AIHub 데이터: 8개 단어, ~205개 (OpenPose → MediaPipe 변환 완료)
- 동일 좌표 포맷(어깨 중점 기준 상대 좌표, 201차원)으로 병합 학습

사용법:
  cd ai/ai_hub
  python train_aihub.py
  python train_aihub.py --team-data ../new_word/word_data --aihub-data word_data
"""

import argparse
import sys
import random
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

_SCRIPT_DIR  = Path(__file__).resolve().parent
_NEW_WORD_AI = _SCRIPT_DIR.parent / "new_word" / "ai"
sys.path.insert(0, str(_NEW_WORD_AI))

from model_bilstm    import BiLSTMClassifier
from dataset_dynamic import DynamicSignDataset, gather_samples as gather_team_samples
from preprocess      import compute_mean_std

try:
    from torch.utils.tensorboard import SummaryWriter
    _HAS_TB = True
except ImportError:
    _HAS_TB = False
    class SummaryWriter:
        def __init__(self, **kwargs): pass
        def add_scalar(self, *a, **kw): pass
        def close(self): pass


# ─────────────────────────── 데이터 수집 ───────────────────────────

def gather_aihub_samples(aihub_root: str) -> Tuple[List[str], List[str]]:
    """AIHub word_data/<단어>/aihub_*.npy 수집."""
    rootp = Path(aihub_root)
    paths, labels = [], []
    if not rootp.exists():
        return paths, labels
    for d in sorted(rootp.iterdir()):
        if not d.is_dir():
            continue
        for fn in sorted(d.glob("aihub_*.npy")):
            paths.append(str(fn))
            labels.append(d.name)
    return paths, labels


def merge_datasets(
    team_root: str,
    aihub_root: str,
) -> Tuple[List[str], List[str]]:
    """팀 데이터 + AIHub 데이터 병합."""
    team_paths,  team_labels  = gather_team_samples(team_root)
    aihub_paths, aihub_labels = gather_aihub_samples(aihub_root)

    print(f"팀 데이터:  {len(team_paths)}개  ({len(set(team_labels))}개 클래스)")
    print(f"AIHub 데이터: {len(aihub_paths)}개  ({len(set(aihub_labels))}개 클래스)")

    all_paths  = team_paths  + aihub_paths
    all_labels = team_labels + aihub_labels

    print(f"병합 후:    {len(all_paths)}개  ({len(set(all_labels))}개 클래스)")
    for lbl in sorted(set(all_labels)):
        t_cnt = team_labels.count(lbl)
        a_cnt = aihub_labels.count(lbl)
        total = t_cnt + a_cnt
        note = f" (팀 {t_cnt} + AIHub {a_cnt})" if a_cnt > 0 else ""
        print(f"  {lbl}: {total}개{note}")

    return all_paths, all_labels


# ─────────────────────────── 학습 ───────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="팀 + AIHub 병합 BiLSTM 학습")
    p.add_argument("--team-data",    default=str(_SCRIPT_DIR.parent / "new_word" / "word_data"))
    p.add_argument("--aihub-data",   default=str(_SCRIPT_DIR / "word_data"))
    p.add_argument("--max-len",      type=int,   default=45)
    p.add_argument("--batch-size",   type=int,   default=32)
    p.add_argument("--epochs",       type=int,   default=150)
    p.add_argument("--lr",           type=float, default=1e-3)
    p.add_argument("--hidden",       type=int,   default=256)
    p.add_argument("--layers",       type=int,   default=2)
    p.add_argument("--dropout",      type=float, default=0.5)
    p.add_argument("--val-split",    type=float, default=0.2)
    p.add_argument("--seed",         type=int,   default=42)
    p.add_argument("--out-dir",      default=str(_SCRIPT_DIR.parent / "new_word" / "models"))
    p.add_argument("--aihub-only",   action="store_true",
                   help="AIHub 데이터만 사용 (8개 클래스 단독 학습)")
    return p.parse_args()


def set_seed(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def collate_fn(batch):
    xs, ys, lens = zip(*batch)
    return torch.stack(xs), torch.tensor(ys, dtype=torch.long), torch.tensor(lens, dtype=torch.long)


def train():
    args = parse_args()
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")

    if args.aihub_only:
        from train_aihub import gather_aihub_samples
        all_paths, all_labels = gather_aihub_samples(args.aihub_data)
        print(f"AIHub 단독 모드: {len(all_paths)}개  ({len(set(all_labels))}개 클래스)")
    else:
        all_paths, all_labels = merge_datasets(args.team_data, args.aihub_data)

    if not all_paths:
        raise RuntimeError("학습 데이터가 없습니다. --team-data / --aihub-data 경로를 확인하세요.")

    # LabelEncoder
    le = LabelEncoder()
    le.fit(all_labels)
    y_encoded = le.transform(all_labels).tolist()

    # train/val 분할
    try:
        tr_p, val_p, tr_y, val_y = train_test_split(
            all_paths, all_labels, test_size=args.val_split,
            stratify=all_labels, random_state=args.seed,
        )
    except ValueError:
        print("[WARN] stratify 실패 → 무작위 분할")
        tr_p, val_p, tr_y, val_y = train_test_split(
            all_paths, all_labels, test_size=args.val_split, random_state=args.seed,
        )

    print(f"\ntrain: {len(tr_p)}  val: {len(val_p)}")

    # 정규화 통계 (훈련셋 기준)
    print("Normalization stats 계산 중...")
    mean, std = compute_mean_std(tr_p, max_len=args.max_len)

    # Dataset
    train_ds = DynamicSignDataset(
        args.team_data, paths=tr_p,  labels=tr_y,
        max_len=args.max_len, mean=mean, std=std, augment=True,
    )
    val_ds = DynamicSignDataset(
        args.team_data, paths=val_p, labels=val_y,
        max_len=args.max_len, mean=mean, std=std, augment=False,
    )

    num_classes = len(train_ds.label2idx)
    input_size  = np.load(tr_p[0]).shape[1]

    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                              shuffle=True,  collate_fn=collate_fn, num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size,
                              shuffle=False, collate_fn=collate_fn, num_workers=0)

    model = BiLSTMClassifier(
        input_size=input_size, hidden_size=args.hidden, num_layers=args.layers,
        num_classes=num_classes, bidirectional=True, dropout=args.dropout,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='max', factor=0.5, patience=5
    )
    criterion = nn.CrossEntropyLoss()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    writer = SummaryWriter(log_dir=str(out_dir / "runs" / time.strftime("%Y%m%d-%H%M%S"))) if _HAS_TB else SummaryWriter()

    best_val, wait, patience_cnt = 0.0, 0, 10
    print(f"\n학습 시작 (epochs={args.epochs}, classes={num_classes}, input={input_size})\n")

    for epoch in range(1, args.epochs + 1):
        model.train()
        t_loss = t_correct = t_total = 0
        for xb, yb, lb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            logits = model(xb, lengths=lb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            t_loss    += loss.item() * xb.size(0)
            t_correct += (logits.argmax(1) == yb).sum().item()
            t_total   += xb.size(0)

        train_acc = t_correct / t_total

        model.eval()
        v_loss = v_correct = v_total = 0
        with torch.no_grad():
            for xb, yb, lb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                logits = model(xb, lengths=lb)
                v_loss    += criterion(logits, yb).item() * xb.size(0)
                v_correct += (logits.argmax(1) == yb).sum().item()
                v_total   += xb.size(0)

        val_acc = v_correct / v_total
        scheduler.step(val_acc)

        writer.add_scalar("acc/train", train_acc, epoch)
        writer.add_scalar("acc/val",   val_acc,   epoch)

        print(f"Epoch {epoch:3d}/{args.epochs}  "
              f"train_acc={train_acc:.4f}  val_acc={val_acc:.4f}")

        if val_acc > best_val:
            best_val = val_acc
            wait = 0
            torch.save(model.state_dict(), str(out_dir / "dynamic_gesture_model.pt"))
            joblib.dump(le, str(out_dir / "label_encoder_dynamic.pkl"))
            joblib.dump({"mean": mean, "std": std}, str(out_dir / "norm_stats.pkl"))
            joblib.dump({
                "input_size": input_size, "hidden_size": args.hidden,
                "num_layers": args.layers, "num_classes": num_classes,
                "bidirectional": True, "dropout": args.dropout, "max_len": args.max_len,
            }, str(out_dir / "model_config.pkl"))
            print(f"  → best 모델 저장 (val_acc={best_val:.4f})")
        else:
            wait += 1
            if wait >= patience_cnt:
                print(f"Early stopping (patience={patience_cnt})")
                break

    writer.close()
    print(f"\n학습 완료.  최고 val_acc={best_val:.4f}")
    print(f"모델 위치: {out_dir.resolve()}")


if __name__ == "__main__":
    train()
