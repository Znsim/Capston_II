"""
Dwell(유지) 입력 기반 실시간 단어 조합기
"""
import time
from .korean_composer import KoreanComposer

DWELL_SECS = 1.0
SPACE_SECS = 2.0
COOLDOWN   = 0.5


class WordBuilder:
    """
    매 프레임 update(label) 를 호출하면 Dwell 타이머로 자모를 확정하고
    KoreanComposer 로 단어를 조합한다.
    """

    def __init__(self, dwell: float = DWELL_SECS,
                 space_dwell: float = SPACE_SECS,
                 cooldown: float = COOLDOWN):
        self.dwell       = dwell
        self.space_dwell = space_dwell
        self.cooldown    = cooldown
        self.composer    = KoreanComposer()

        self._cur_label      = None
        self._label_start    = 0.0
        self._last_committed = None
        self._committed_at   = 0.0

    def update(self, label: str | None) -> dict:
        now   = time.time()
        label = label if (label and label != 'none') else None

        if label != self._cur_label:
            self._cur_label      = label
            self._label_start    = now
            self._last_committed = None

        elapsed    = now - self._label_start
        can_commit = (now - self._committed_at) > self.cooldown
        committed  = None

        if label is None:
            progress = min(elapsed / self.space_dwell, 1.0)
            if elapsed >= self.space_dwell and can_commit and self.composer.composing:
                self.composer.space()
                self._committed_at   = now
                self._last_committed = None
                committed = ' '
        else:
            progress = min(elapsed / self.dwell, 1.0)
            if elapsed >= self.dwell and can_commit and label != self._last_committed:
                self.composer.add(label)
                self._last_committed = label
                self._committed_at   = now
                committed = label

        return {
            'text':      self.composer.text,
            'composing': self.composer.composing,
            'progress':  progress,
            'committed': committed,
        }

    def backspace(self):
        self.composer.backspace()
        self._last_committed = None

    def clear(self):
        self.composer.clear()
        self._last_committed = None
        self._cur_label      = None
