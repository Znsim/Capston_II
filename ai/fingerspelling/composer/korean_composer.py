"""
한글 자모 → 음절 조합 엔진 (표준 두벌식 오토마타)
"""

CHOSUNG  = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
JUNGSUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
JONGSUNG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']

CONSONANTS = set(CHOSUNG)
VOWELS     = set(JUNGSUNG)

COMPOUND_VOWEL = {
    ('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
    ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ',
    ('ㅡ', 'ㅣ'): 'ㅢ',
}

COMPOUND_JONG = {
    ('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
    ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ',
    ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ',
}

DOUBLE_CONSONANT = {'ㄱ': 'ㄲ', 'ㄷ': 'ㄸ', 'ㅂ': 'ㅃ', 'ㅅ': 'ㅆ', 'ㅈ': 'ㅉ'}
SPLIT_JONG  = {v: k for k, v in COMPOUND_JONG.items()}
VOWEL_FIRST = {v: k[0] for k, v in COMPOUND_VOWEL.items()}


def _compose(cho: str, jung: str, jong: str = '') -> str:
    return chr(0xAC00 + (CHOSUNG.index(cho) * 21 + JUNGSUNG.index(jung)) * 28 + JONGSUNG.index(jong))


def _decompose(syllable: str):
    code   = ord(syllable) - 0xAC00
    jong_i = code % 28
    jung_i = (code // 28) % 21
    cho_i  = code // 28 // 21
    return CHOSUNG[cho_i], JUNGSUNG[jung_i], JONGSUNG[jong_i]


class KoreanComposer:
    """두벌식 오토마타로 지문자 자모를 조합해 완성형 한글을 생성한다."""

    def __init__(self):
        self._done: list[str] = []
        self._cho:  str | None = None
        self._jung: str | None = None
        self._jong: str | None = None

    def add(self, jamo: str):
        if jamo in CONSONANTS:
            self._input_consonant(jamo)
        elif jamo in VOWELS:
            self._input_vowel(jamo)

    def space(self):
        self._commit()
        self._done.append(' ')

    def backspace(self):
        if self._jong is not None:
            self._jong = SPLIT_JONG[self._jong][0] if self._jong in SPLIT_JONG else None
        elif self._jung is not None:
            self._jung = VOWEL_FIRST[self._jung] if self._jung in VOWEL_FIRST else None
        elif self._cho is not None:
            self._cho = None
        elif self._done:
            last = self._done.pop()
            if last == ' ':
                return
            if 0 <= ord(last) - 0xAC00 < 11172:
                cho, jung, jong = _decompose(last)
                self._cho  = cho
                self._jung = jung
                self._jong = jong if jong else None

    def clear(self):
        self._done.clear()
        self._cho = self._jung = self._jong = None

    @property
    def text(self) -> str:
        return ''.join(self._done) + self._current()

    @property
    def composing(self) -> str:
        return self._current()

    def _current(self) -> str:
        if self._cho is None:
            return ''
        if self._jung is None:
            return self._cho
        return _compose(self._cho, self._jung, self._jong or '')

    def _commit(self):
        cur = self._current()
        if cur:
            self._done.append(cur)
        self._cho = self._jung = self._jong = None

    def _input_consonant(self, c: str):
        if self._jung is None:
            if self._cho is not None and self._cho == c and c in DOUBLE_CONSONANT:
                self._cho = DOUBLE_CONSONANT[c]
            elif self._cho is not None:
                self._done.append(self._cho)
                self._cho = c
            else:
                self._cho = c
            self._jong = None
        else:
            if self._jong is None:
                self._jong = c
            elif self._jong == c and c in DOUBLE_CONSONANT:
                self._jong = DOUBLE_CONSONANT[c]
            else:
                comp = COMPOUND_JONG.get((self._jong, c))
                if comp:
                    self._jong = comp
                else:
                    self._done.append(_compose(self._cho, self._jung, self._jong))
                    self._cho  = c
                    self._jung = self._jong = None

    def _input_vowel(self, v: str):
        if self._cho is None:
            self._cho  = 'ㅇ'
            self._jung = v
        elif self._jung is None:
            self._jung = v
        elif self._jong is None:
            comp = COMPOUND_VOWEL.get((self._jung, v))
            if comp:
                self._jung = comp
            else:
                self._done.append(_compose(self._cho, self._jung))
                self._cho  = 'ㅇ'
                self._jung = v
                self._jong = None
        else:
            if self._jong in SPLIT_JONG:
                first, second = SPLIT_JONG[self._jong]
                self._done.append(_compose(self._cho, self._jung, first))
                self._cho = second
            else:
                self._done.append(_compose(self._cho, self._jung))
                self._cho = self._jong
            self._jung = v
            self._jong = None
