"""학습된 모델의 클래스별 정확도 및 confusion matrix 출력 (학습과 동일한 전처리 사용)"""
import sys
from pathlib import Path
import numpy as np
import joblib
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / 'ai'))
sys.stdout.reconfigure(encoding='utf-8')

from model_bilstm import BiLSTMClassifier
from dataset_dynamic import DynamicSignDataset, gather_samples

MODEL_DIR = BASE_DIR / "models"
DATA_ROOT = BASE_DIR / "word_data"

def collate_fn(batch):
    xs, ys, lens = zip(*batch)
    return torch.stack(xs), torch.tensor(ys, dtype=torch.long), torch.tensor(lens, dtype=torch.long)

def main():
    config  = joblib.load(MODEL_DIR / "model_config.pkl")
    le      = joblib.load(MODEL_DIR / "label_encoder_dynamic.pkl")
    stats   = joblib.load(MODEL_DIR / "norm_stats.pkl")

    model = BiLSTMClassifier(
        input_size=config['input_size'], hidden_size=config['hidden_size'],
        num_layers=config['num_layers'], num_classes=config['num_classes'],
        bidirectional=config.get('bidirectional', True), dropout=config.get('dropout', 0.5),
    )
    model.load_state_dict(torch.load(MODEL_DIR / "dynamic_gesture_model.pt", map_location='cpu'))
    model.eval()

    paths, labels = gather_samples(str(DATA_ROOT))
    print(f"전체 샘플: {len(paths)}개 / 클래스: {len(set(labels))}개")

    # 학습과 동일한 train/val 분할 (seed=42)
    train_p, val_p, train_y, val_y = train_test_split(
        paths, labels, test_size=0.2, stratify=labels, random_state=42
    )

    # 전체 데이터셋 (학습과 동일한 전처리, augment=False)
    full_ds = DynamicSignDataset(
        str(DATA_ROOT), paths=paths, labels=labels,
        max_len=config['max_len'], mean=stats['mean'], std=stats['std'], augment=False
    )
    full_loader = DataLoader(full_ds, batch_size=64, shuffle=False, collate_fn=collate_fn)

    y_true_idx, y_pred_idx = [], []
    with torch.no_grad():
        for xb, yb, lb in full_loader:
            logits = model(xb, lengths=lb)
            preds = logits.argmax(dim=1)
            y_true_idx.extend(yb.tolist())
            y_pred_idx.extend(preds.tolist())

    # 인덱스 → 단어 변환
    idx2label = full_ds.idx2label
    y_true = [idx2label[i] for i in y_true_idx]
    y_pred = [idx2label[i] for i in y_pred_idx]

    correct = sum(t == p for t, p in zip(y_true, y_pred))
    print(f"\n전체 정확도: {correct/len(y_true)*100:.2f}%  ({correct}/{len(y_true)})\n")
    print("=" * 60)
    print(classification_report(y_true, y_pred, digits=3, zero_division=0))

    # 오답 분석
    wrong_by_class = Counter(t for t, p in zip(y_true, y_pred) if t != p)
    print("=" * 60)
    print("오답 많은 단어 Top 10:")
    for word, cnt in wrong_by_class.most_common(10):
        total = labels.count(word)
        print(f"  {word}: {cnt}/{total} 오답 ({cnt/total*100:.1f}%)")

if __name__ == "__main__":
    main()
