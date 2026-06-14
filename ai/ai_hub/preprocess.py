"""
preprocess.py
=============
정규화 및 데이터 증강 유틸리티.
기존 ai/new_word/ai/preprocess.py와 동일한 augment 함수 포함.
"""

import random
import numpy as np
from typing import List, Tuple

# 201-dim feature layout: (x, y, confidence) × 67 landmarks
# x columns: 0, 3, 6, ..., 198  /  y columns: 1, 4, 7, ..., 199
_X_COLS = np.arange(0, 201, 3)
_Y_COLS = np.arange(1, 201, 3)


def compute_mean_std(paths: List[str], max_len: int = 64) -> Tuple[np.ndarray, np.ndarray]:
    """Compute per-feature mean/std using only actual frames (no zero-padding)."""
    sum_ = None
    sumsq = None
    count = 0
    for p in paths:
        arr = np.load(p).astype(np.float32)
        T, F = arr.shape
        if T > max_len:
            start = max(0, (T - max_len) // 2)
            arr = arr[start:start + max_len]

        if sum_ is None:
            sum_ = np.sum(arr, axis=0)
            sumsq = np.sum(arr * arr, axis=0)
        else:
            sum_ += np.sum(arr, axis=0)
            sumsq += np.sum(arr * arr, axis=0)
        count += arr.shape[0]

    mean = sum_ / count
    var = (sumsq / count) - (mean * mean)
    std = np.sqrt(np.maximum(var, 1e-8))
    return mean.astype(np.float32), std.astype(np.float32)


def augment_time_warp(arr: np.ndarray, scale_range: float = 0.1) -> np.ndarray:
    """프레임 축을 ±scale_range 비율로 늘리거나 압축 (속도 변화 시뮬레이션)."""
    scale = 1.0 + random.uniform(-scale_range, scale_range)
    T, F = arr.shape
    new_T = max(1, int(T * scale))
    idx = np.linspace(0, T - 1, new_T).astype(np.float32)
    left = np.floor(idx).astype(int)
    right = np.clip(np.ceil(idx).astype(int), 0, T - 1)
    alpha = (idx - left).astype(np.float32)
    return (arr[left] * (1 - alpha)[:, None] + arr[right] * alpha[:, None]).astype(np.float32)


def augment_spatial(arr: np.ndarray,
                    max_shift: float = 0.03,
                    scale_range: float = 0.05,
                    noise_std: float = 0.003) -> np.ndarray:
    """x·y 정규화 좌표에 이동·스케일·노이즈 적용. confidence 열은 건드리지 않음.

    max_shift  : 상하좌우 최대 이동량 (정규화 좌표, 0.03 = 3%)
    scale_range: 스케일 변화 비율 (±5%, 신체 중심 기준 줌인·아웃)
    noise_std  : 랜드마크 검출 오차 시뮬레이션 (0.003 ≈ 2px/640px)
    """
    arr = arr.copy()

    # 1) 이동 (전체 랜드마크 동일 오프셋 → 촬영 위치 다양화)
    dx = random.uniform(-max_shift, max_shift)
    dy = random.uniform(-max_shift, max_shift)
    arr[:, _X_COLS] += dx
    arr[:, _Y_COLS] += dy

    # 2) 스케일 (신체 중심 기준 → 거리 다양화)
    cx = arr[:, _X_COLS].mean()
    cy = arr[:, _Y_COLS].mean()
    scale = 1.0 + random.uniform(-scale_range, scale_range)
    arr[:, _X_COLS] = (arr[:, _X_COLS] - cx) * scale + cx
    arr[:, _Y_COLS] = (arr[:, _Y_COLS] - cy) * scale + cy

    # 3) 노이즈 (검출 떨림 시뮬레이션)
    arr[:, _X_COLS] += np.random.normal(0, noise_std, arr[:, _X_COLS].shape)
    arr[:, _Y_COLS] += np.random.normal(0, noise_std, arr[:, _Y_COLS].shape)

    return arr
