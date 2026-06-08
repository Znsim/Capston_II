from pathlib import Path
from typing import List, Tuple
import numpy as np
import torch
from torch.utils.data import Dataset

from .preprocess import normalize_landmarks, augment as _augment


class FingerspellingDataset(Dataset):
    """지문자 .npy 데이터셋 (PyTorch 학습용).

    폴더 구조: dataset/<자모>/landmarks_npy/*.npy
    각 .npy 파일: (21, 3) raw MediaPipe 랜드마크 → 로드 시 정규화.

    collect_data.py 로 수집된 데이터와 train_classifier.py 가 읽는
    동일한 데이터를 공유한다.
    """

    def __init__(self, root: str, augment: bool = False):
        self.augment = augment
        rootp = Path(root)

        samples: List[Tuple[str, str]] = []
        label_set = set()

        if not rootp.exists():
            self.samples = []
            self.label2idx = {}
            self.idx2label = {}
            return

        for label_dir in sorted(rootp.iterdir()):
            if not label_dir.is_dir():
                continue
            npy_dir = label_dir / "landmarks_npy"
            if not npy_dir.exists():
                continue
            label = label_dir.name
            label_set.add(label)
            for npy in sorted(npy_dir.glob("*.npy")):
                samples.append((str(npy), label))

        self.label2idx = {l: i for i, l in enumerate(sorted(label_set))}
        self.idx2label = {i: l for l, i in self.label2idx.items()}
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        raw = np.load(path).astype(np.float32)  # (21, 3)
        arr = normalize_landmarks(raw)           # (63,)
        if self.augment:
            arr = _augment(arr)
        return torch.from_numpy(arr), self.label2idx[label]
