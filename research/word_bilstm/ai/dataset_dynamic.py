import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import numpy as np
import torch
from torch.utils.data import Dataset

from preprocess import augment_time_warp, augment_spatial


class DynamicSignDataset(Dataset):
    """Dataset for dynamic sign sequences stored as .npy files.

    Expects structure: root/<speaker>/<label>/<label_0000.npy>
    """

    def __init__(self, root: str, paths: Optional[List[str]] = None, labels: Optional[List[str]] = None,
                 max_len: int = 64, mean: Optional[np.ndarray] = None, std: Optional[np.ndarray] = None,
                 augment: bool = False):
        self.root = Path(root)
        self.max_len = max_len
        self.augment = augment

        if paths is None or labels is None:
            # scan folders
            samples = []  # tuples (path, label)
            for speaker in sorted(os.listdir(self.root)):
                sp = self.root / speaker
                if not sp.is_dir():
                    continue
                for label in sorted([d for d in os.listdir(sp) if (sp / d).is_dir()]):
                    lbl_dir = sp / label
                    for fn in sorted(os.listdir(lbl_dir)):
                        if fn.endswith('.npy'):
                            samples.append((str(lbl_dir / fn), label))
            self.paths, self.labels = zip(*samples) if samples else ([], [])
        else:
            self.paths = paths
            self.labels = labels

        # label -> idx mapping
        unique = sorted(list(set(self.labels)))
        self.label2idx = {l: i for i, l in enumerate(unique)}
        self.idx2label = {i: l for l, i in self.label2idx.items()}

        # normalization stats
        self.mean = mean
        self.std = std

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, idx):
        p = self.paths[idx]
        arr = np.load(p).astype(np.float32)  # shape (T, F)
        arr, actual_len = self._preprocess(arr)
        label = self.label2idx[self.labels[idx]]
        return torch.from_numpy(arr), int(label), int(actual_len)

    def _preprocess(self, arr: np.ndarray):
        # 1) 시간 축 증강 (T가 바뀌므로 actual_len 계산 전에 적용)
        if self.augment:
            arr = augment_time_warp(arr)

        # 2) time_warp 후 실제 프레임 수 확정 (LSTM에 전달할 실제 길이)
        actual_len = min(arr.shape[0], self.max_len)

        # 3) max_len에 맞게 trim / pad
        T, F = arr.shape
        if T > self.max_len:
            start = max(0, (T - self.max_len) // 2)
            arr = arr[start:start + self.max_len]
        elif T < self.max_len:
            pad = np.zeros((self.max_len - T, F), dtype=arr.dtype)
            arr = np.vstack([arr, pad])

        # 4) 공간 증강 (정규화 전 정규화 좌표 상태에서 적용)
        if self.augment:
            arr = augment_spatial(arr)

        # 5) 정규화
        if self.mean is not None and self.std is not None:
            arr = (arr - self.mean) / (self.std + 1e-8)

        return arr, actual_len


def gather_samples(root: str) -> Tuple[List[str], List[str]]:
    samples = []
    rootp = Path(root)
    for speaker in sorted(os.listdir(rootp)):
        sp = rootp / speaker
        if not sp.is_dir():
            continue
        for label in sorted([d for d in os.listdir(sp) if (sp / d).is_dir()]):
            lbl_dir = sp / label
            for fn in sorted(os.listdir(lbl_dir)):
                if fn.endswith('.npy'):
                    samples.append((str(lbl_dir / fn), label))
    if not samples:
        return [], []
    paths, labels = zip(*samples)
    return list(paths), list(labels)
