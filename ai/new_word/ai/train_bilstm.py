import argparse
import os
from pathlib import Path
import random
import time
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from dataset_dynamic import DynamicSignDataset, gather_samples
from preprocess import compute_mean_std, augment_time_warp
from model_bilstm import BiLSTMClassifier

# 스크립트 위치 기준 절대 경로
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=str, default=str(_ROOT / 'word_data'))
    p.add_argument('--max-len', type=int, default=45)
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--epochs', type=int, default=50)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--hidden', type=int, default=128)
    p.add_argument('--layers', type=int, default=2)
    p.add_argument('--dropout', type=float, default=0.5)
    p.add_argument('--val-split', type=float, default=0.2)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--out-dir', type=str, default=str(_ROOT / 'models'))
    return p.parse_args()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def collate_fn(batch):
    xs, ys, lens = zip(*batch)
    xs = torch.stack(xs, dim=0)  # (B, T, F)
    ys = torch.tensor(ys, dtype=torch.long)
    lens = torch.tensor(lens, dtype=torch.long)
    return xs, ys, lens


def train():
    args = parse_args()
    set_seed(args.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('Device:', device)

    # gather samples
    paths, labels = gather_samples(args.data_root)
    if not paths:
        raise RuntimeError('No samples found under ' + args.data_root)

    # label encoder
    le = LabelEncoder()
    y_enc = le.fit_transform(labels)

    # train/val split (random)
    train_p, val_p, train_y, val_y = train_test_split(paths, labels, test_size=args.val_split,
                                                      stratify=labels, random_state=args.seed)

    # compute mean/std on training set
    print('Computing normalization stats...')
    mean, std = compute_mean_std(train_p, max_len=args.max_len)

    # create datasets
    train_ds = DynamicSignDataset(args.data_root, paths=train_p, labels=train_y,
                                  max_len=args.max_len, mean=mean, std=std, augment=True)
    val_ds = DynamicSignDataset(args.data_root, paths=val_p, labels=val_y,
                                max_len=args.max_len, mean=mean, std=std, augment=False)

    num_classes = len(train_ds.label2idx)
    input_size = 0
    # probe one sample for feature size
    sample = np.load(train_p[0]).astype(np.float32)
    input_size = sample.shape[1]

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)

    model = BiLSTMClassifier(input_size=input_size, hidden_size=args.hidden, num_layers=args.layers,
                             num_classes=num_classes, bidirectional=True, dropout=args.dropout)
    model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    writer = SummaryWriter(log_dir=str(_ROOT / 'runs' / time.strftime('%Y%m%d-%H%M%S')))

    best_val = 0.0
    patience = 6
    wait = 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        total = 0
        correct = 0
        for xb, yb, lb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            logits = model(xb, lengths=lb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * xb.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == yb).sum().item()
            total += xb.size(0)

        train_loss = total_loss / total
        train_acc = correct / total

        # validation
        model.eval()
        v_total = 0
        v_correct = 0
        v_loss = 0.0
        with torch.no_grad():
            for xb, yb, lb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                logits = model(xb, lengths=lb)
                loss = criterion(logits, yb)
                v_loss += loss.item() * xb.size(0)
                preds = logits.argmax(dim=1)
                v_correct += (preds == yb).sum().item()
                v_total += xb.size(0)

        val_loss = v_loss / v_total
        val_acc = v_correct / v_total

        writer.add_scalar('loss/train', train_loss, epoch)
        writer.add_scalar('loss/val', val_loss, epoch)
        writer.add_scalar('acc/train', train_acc, epoch)
        writer.add_scalar('acc/val', val_acc, epoch)

        print(f'Epoch {epoch}/{args.epochs}  train_loss={train_loss:.4f} acc={train_acc:.4f}  val_loss={val_loss:.4f} val_acc={val_acc:.4f}')

        if val_acc > best_val:
            best_val = val_acc
            wait = 0
            torch.save(model.state_dict(), str(out_dir / 'dynamic_gesture_model.pt'))
            joblib.dump(le, str(out_dir / 'label_encoder_dynamic.pkl'))
            joblib.dump({'mean': mean, 'std': std}, str(out_dir / 'norm_stats.pkl'))
            # 추론 스크립트가 아키텍처를 재구성할 수 있도록 설정 저장
            joblib.dump({
                'input_size': input_size,
                'hidden_size': args.hidden,
                'num_layers': args.layers,
                'num_classes': num_classes,
                'bidirectional': True,
                'dropout': args.dropout,
                'max_len': args.max_len,
            }, str(out_dir / 'model_config.pkl'))
        else:
            wait += 1
            if wait >= patience:
                print('Early stopping')
                break

    writer.close()


if __name__ == '__main__':
    train()
