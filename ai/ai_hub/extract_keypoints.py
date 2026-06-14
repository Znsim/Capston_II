"""
extract_keypoints.py
====================
AIHub 수어 단어 데이터에서 타겟 단어 키포인트를 추출하여 .npy로 저장.

동작 순서:
  1. REAL01 morpheme JSON 스캔 → WORD_ID → (단어, start, end) 매핑 생성
  2. 16개 keypoint ZIP에서 F카메라 데이터 추출 (REAL01 타이밍 공유 사용)
  3. 어깨 중점 기준 상대 좌표 정규화
  4. 45프레임 균등 샘플링
  5. word_data/<단어>/aihub_<WORD_ID>_<REAL_ID>.npy 저장 (shape: (45, 201))

사용법:
  cd ai/ai_hub
  python extract_keypoints.py
  python extract_keypoints.py --out-dir word_data
"""

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ─────────────────────────── 상수 ───────────────────────────

TARGET_WORDS = [
    "가다", "갈아타다", "감사", "건너다", "고장", "공항", "기차",
    "내리다", "도움", "맞다", "매표소", "버스", "시간", "어디",
    "엘리베이터", "여기", "역", "오른쪽", "왼쪽", "잃어버리다",
    "정류장", "지하철", "찾다", "카드", "타다", "택시", "화장실",
]

TARGET_FRAMES = 45
FPS = 30
NUM_REALS = 16

# OpenPose body_25 → MediaPipe pose(0-24) 인덱스 매핑
# OpenPose: 0=Nose,2=RShoulder,3=RElbow,4=RWrist,5=LShoulder,6=LElbow,7=LWrist,9=RHip,12=LHip,15=REye,16=LEye,17=REar,18=LEar
# MediaPipe: 0=Nose,2=LEye,5=REye,7=LEar,8=REar,11=LShoulder,12=RShoulder,13=LElbow,14=RElbow,15=LWrist,16=RWrist,23=LHip,24=RHip
_OP_TO_MP: Dict[int, int] = {
    0: 0,   # Nose
    2: 12,  # RShoulder → MP right shoulder
    3: 14,  # RElbow    → MP right elbow
    4: 16,  # RWrist    → MP right wrist
    5: 11,  # LShoulder → MP left shoulder
    6: 13,  # LElbow    → MP left elbow
    7: 15,  # LWrist    → MP left wrist
    9: 24,  # RHip      → MP right hip
    12: 23, # LHip      → MP left hip
    15: 5,  # REye      → MP right eye
    16: 2,  # LEye      → MP left eye
    17: 8,  # REar      → MP right ear
    18: 7,  # LEar      → MP left ear
}

DEFAULT_MORPHEME_DIR = r"E:\수어\수어 영상\1.Training\[라벨]01_real_word_morpheme\morpheme\01"
DEFAULT_ZIP_DIR      = r"E:\수어\수어 영상\1.Training"
DEFAULT_OUT_DIR      = "word_data"


# ─────────────────────────── 파싱 ───────────────────────────

def parse_word_id(filename: str) -> Optional[int]:
    m = re.search(r"WORD(\d+)", filename)
    return int(m.group(1)) if m else None


# ─────────────────────────── 키포인트 변환 ──────────────────

def _remap_pose_op_to_mp(pose_op: np.ndarray) -> np.ndarray:
    """
    OpenPose body_25(75dim) → MediaPipe pose 0-24(75dim) 순서로 재배열.
    손 부분(75~200)은 두 포맷이 동일하므로 그대로 사용.
    """
    mp = np.zeros(75, dtype=np.float32)
    for op_idx, mp_idx in _OP_TO_MP.items():
        mp[mp_idx * 3: mp_idx * 3 + 3] = pose_op[op_idx * 3: op_idx * 3 + 3]
    return mp


def keypoints_to_vector(kp_data: Dict) -> Optional[np.ndarray]:
    """OpenPose keypoint dict → 201차원 ndarray (MediaPipe 좌표 순서로 변환)."""
    people = kp_data.get("people")
    if people is None:
        return None
    person = people if isinstance(people, dict) else (people[0] if people else None)
    if person is None:
        return None

    def _pad(lst, expected):
        arr = np.array(lst, dtype=np.float32)
        if len(arr) < expected:
            arr = np.concatenate([arr, np.zeros(expected - len(arr), dtype=np.float32)])
        return arr[:expected]

    pose_op   = _pad(person.get("pose_keypoints_2d",       []), 75)
    left_arr  = _pad(person.get("hand_left_keypoints_2d",  []), 63)
    right_arr = _pad(person.get("hand_right_keypoints_2d", []), 63)
    pose_mp   = _remap_pose_op_to_mp(pose_op)
    return np.concatenate([pose_mp, left_arr, right_arr])  # (201,) MediaPipe 순서


# ─────────────────────────── 정규화 ─────────────────────────

def normalize_sequence(seq: np.ndarray) -> np.ndarray:
    """
    어깨 중점 기준 상대 좌표 정규화 (MediaPipe 좌표 순서 기준).
    MediaPipe: LShoulder=index 11 (cols 33,34), RShoulder=index 12 (cols 36,37)
    collect_word_data.py 와 동일 방식.
    """
    seq = seq.copy()
    # LShoulder cols 33,34 / RShoulder cols 36,37 (MediaPipe 순서)
    cx = (seq[:, 33] + seq[:, 36]) / 2.0
    cy = (seq[:, 34] + seq[:, 37]) / 2.0

    x_cols = np.arange(0, 201, 3)
    y_cols = np.arange(1, 201, 3)
    seq[:, x_cols] -= cx[:, None]
    seq[:, y_cols] -= cy[:, None]
    return seq


# ─────────────────────────── 샘플링 ─────────────────────────

def uniform_sample(seq: np.ndarray, n_frames: int) -> np.ndarray:
    T = seq.shape[0]
    if T == 0:
        return np.zeros((n_frames, seq.shape[1]), dtype=np.float32)
    if T == n_frames:
        return seq.astype(np.float32)
    idx = np.round(np.linspace(0, T - 1, n_frames)).astype(int)
    return seq[idx].astype(np.float32)


# ─────────────────────────── Step 1: morpheme 스캔 ──────────

def scan_morpheme_real01(morpheme_dir: Path) -> Dict[int, Dict]:
    """
    REAL01 F카메라 morpheme 스캔.
    반환: {word_id: {"word": str, "start": float, "end": float}}
    """
    target_set = set(TARGET_WORDS)
    result: Dict[int, Dict] = {}

    json_files = list(morpheme_dir.glob("*_REAL01_F_morpheme.json"))
    print(f"[Step 1] REAL01 F카메라 morpheme 파일: {len(json_files)}개")

    for fp in json_files:
        wid = parse_word_id(fp.name)
        if wid is None:
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        for item in data.get("data", []):
            attrs = item.get("attributes", [])
            if not attrs:
                continue
            word_name = attrs[0].get("name", "")
            if word_name not in target_set:
                continue
            result[wid] = {
                "word":  word_name,
                "start": float(item.get("start", 0.0)),
                "end":   float(item.get("end",   999.0)),
            }
            break  # 단어당 첫 번째 어노테이션만 사용

    found_words = set(v["word"] for v in result.values())
    print(f"        → 발견 단어: {len(found_words)}/{len(TARGET_WORDS)}개")
    for w in sorted(found_words):
        ids = [wid for wid, v in result.items() if v["word"] == w]
        print(f"          {w}: WORD ID {sorted(ids)}")
    missing = sorted(set(TARGET_WORDS) - found_words)
    if missing:
        print(f"        → 미발견: {missing}")
    return result


# ─────────────────────────── Step 2: 키포인트 추출 ──────────

def get_zip_path(zip_dir: Path, real_id: int) -> Optional[Path]:
    """실제 ZIP 파일명을 glob으로 찾음 (브라켓 등 특수문자 대응)."""
    matches = sorted(zip_dir.glob(f"*{real_id:02d}_real_word_keypoint.zip"))
    return matches[0] if matches else None


def extract_frames_from_zip(
    zip_path: Path,
    real_id: int,
    word_id: int,
    start_sec: float,
    end_sec: float,
) -> Optional[np.ndarray]:
    """
    ZIP에서 WORD{word_id}_REAL{real_id}_F 폴더의 start~end 프레임 읽기.
    ZIP 내부 구조: {real_id:02d}/NIA_SL_WORD{word_id:04d}_REAL{real_id:02d}_F/...json
    """
    # ZIP 내부 섹션 번호 = real_id (01/ 02/ ... 16/)
    section   = f"{real_id:02d}"
    folder_id = f"NIA_SL_WORD{word_id:04d}_REAL{real_id:02d}_F"
    prefix    = f"{section}/{folder_id}/"

    start_frame = int(start_sec * FPS)
    end_frame   = int(end_sec   * FPS)

    frames: List[np.ndarray] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            candidates = [
                n for n in zf.namelist()
                if n.startswith(prefix) and n.endswith("_keypoints.json")
            ]
            if not candidates:
                return None

            def frame_num(name: str) -> int:
                m = re.search(r"_(\d{12})_keypoints\.json$", name)
                return int(m.group(1)) if m else -1

            candidates.sort(key=frame_num)

            for name in candidates:
                fn = frame_num(name)
                if fn < 0:
                    continue
                # start/end 필터 — 합리적인 범위 내에서만 (±5프레임 여유)
                if fn < max(0, start_frame - 5) or fn > end_frame + 5:
                    continue
                try:
                    with zf.open(name) as f:
                        kp_data = json.loads(f.read().decode("utf-8"))
                except Exception:
                    continue
                vec = keypoints_to_vector(kp_data)
                if vec is not None:
                    frames.append(vec)
    except Exception as e:
        print(f"    [ERROR] {zip_path.name}: {e}")
        return None

    if not frames:
        return None

    seq = np.stack(frames, axis=0)
    seq = normalize_sequence(seq)
    seq = uniform_sample(seq, TARGET_FRAMES)
    return seq


# ─────────────────────────── 메인 ───────────────────────────

def extract_all(morpheme_dir: Path, zip_dir: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: REAL01 morpheme 스캔
    word_map = scan_morpheme_real01(morpheme_dir)
    if not word_map:
        print("[ERROR] 타겟 단어를 찾지 못했습니다. morpheme_dir를 확인하세요.")
        return

    words_to_ids: Dict[str, List[int]] = {}
    for wid, info in word_map.items():
        words_to_ids.setdefault(info["word"], []).append(wid)

    # Step 2: ZIP 한 번씩 열어서 전체 WORD_ID 추출 (효율 최적화)
    print(f"\n[Step 2] 키포인트 추출 (REAL01~{NUM_REALS:02d} × {len(word_map)}개 WORD_ID)")
    total_saved = 0

    for real_id in range(1, NUM_REALS + 1):
        zip_path = get_zip_path(zip_dir, real_id)
        if zip_path is None:
            print(f"  REAL{real_id:02d}: ZIP 없음 → 스킵")
            continue

        # 이미 완료된 항목 확인
        pending = {
            wid: info for wid, info in word_map.items()
            if not (out_dir / info["word"] / f"aihub_{wid:04d}_{real_id:02d}.npy").exists()
        }
        if not pending:
            print(f"  REAL{real_id:02d}: 이미 완료 → 스킵")
            total_saved += len(word_map)
            continue

        print(f"\n  REAL{real_id:02d}: {zip_path.name}  ({len(pending)}개 추출 예정)")
        section = f"{real_id:02d}"
        real_saved = len(word_map) - len(pending)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # namelist를 한 번만 스캔
                all_names = zf.namelist()

                for wid, info in sorted(pending.items()):
                    word    = info["word"]
                    start_s = info["start"]
                    end_s   = info["end"]
                    prefix  = f"{section}/NIA_SL_WORD{wid:04d}_REAL{real_id:02d}_F/"

                    candidates = [
                        n for n in all_names
                        if n.startswith(prefix) and n.endswith("_keypoints.json")
                    ]
                    if not candidates:
                        print(f"    WORD{wid:04d} ({word}): 폴더 없음")
                        continue

                    def frame_num(name: str) -> int:
                        m = re.search(r"_(\d{12})_keypoints\.json$", name)
                        return int(m.group(1)) if m else -1

                    candidates.sort(key=frame_num)
                    sf = max(0, int(start_s * FPS) - 5)
                    ef = int(end_s * FPS) + 5

                    frames: List[np.ndarray] = []
                    for name in candidates:
                        fn = frame_num(name)
                        if fn < sf or fn > ef:
                            continue
                        try:
                            with zf.open(name) as f:
                                kp_data = json.loads(f.read().decode("utf-8"))
                        except Exception:
                            continue
                        vec = keypoints_to_vector(kp_data)
                        if vec is not None:
                            frames.append(vec)

                    if not frames:
                        print(f"    WORD{wid:04d} ({word}): 유효 프레임 없음")
                        continue

                    seq = np.stack(frames, axis=0)
                    seq = normalize_sequence(seq)
                    arr = uniform_sample(seq, TARGET_FRAMES)

                    out_file = out_dir / word / f"aihub_{wid:04d}_{real_id:02d}.npy"
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    np.save(str(out_file), arr)
                    real_saved += 1

        except Exception as e:
            print(f"  [ERROR] {zip_path.name}: {e}")
            continue

        print(f"    저장: {real_saved}/{len(word_map)}개")
        total_saved += real_saved

    print(f"\n[완료] 총 {total_saved}개 .npy 파일")
    print(f"       저장 위치: {out_dir.resolve()}")

    print("\n[단어별 추출 결과]")
    for word in sorted(words_to_ids.keys()):
        saved = len(list((out_dir / word).glob("aihub_*.npy"))) if (out_dir / word).exists() else 0
        expected = len(words_to_ids[word]) * NUM_REALS
        print(f"  {word}: {saved}/{expected}개")


# ─────────────────────────── CLI ────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AIHub 수어 키포인트 추출기")
    p.add_argument("--morpheme-dir", default=DEFAULT_MORPHEME_DIR)
    p.add_argument("--zip-dir",      default=DEFAULT_ZIP_DIR)
    p.add_argument("--out-dir",      default=DEFAULT_OUT_DIR)
    args = p.parse_args()

    extract_all(
        morpheme_dir=Path(args.morpheme_dir),
        zip_dir=Path(args.zip_dir),
        out_dir=Path(args.out_dir),
    )
