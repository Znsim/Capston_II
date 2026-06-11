/*
한글 자모 → 음절 조합 엔진 (표준 두벌식 오토마타)
*/

const CHOSUNG  = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
const JUNGSUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
const JONGSUNG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']

const CONSONANTS = new Set(CHOSUNG)
const VOWELS     = new Set(JUNGSUNG)

// 두 단순 모음 → 복합 모음
const COMPOUND_VOWEL = {
    'ㅗ,ㅏ': 'ㅘ',
    'ㅗ,ㅐ': 'ㅙ',
    'ㅗ,ㅣ': 'ㅚ',
    'ㅜ,ㅓ': 'ㅝ',
    'ㅜ,ㅔ': 'ㅞ',
    'ㅜ,ㅣ': 'ㅟ',
    'ㅡ,ㅣ': 'ㅢ',
}

// 두 단순 자음 → 복합 종성
const COMPOUND_JONG = {
    'ㄱ,ㅅ': 'ㄳ',
    'ㄴ,ㅈ': 'ㄵ',
    'ㄴ,ㅎ': 'ㄶ',
    'ㄹ,ㄱ': 'ㄺ',
    'ㄹ,ㅁ': 'ㄻ',
    'ㄹ,ㅂ': 'ㄼ',
    'ㄹ,ㅅ': 'ㄽ',
    'ㄹ,ㅌ': 'ㄾ',
    'ㄹ,ㅍ': 'ㄿ',
    'ㄹ,ㅎ': 'ㅀ',
    'ㅂ,ㅅ': 'ㅄ',
}

// 같은 자음 두 번 → 쌍자음
const DOUBLE_CONSONANT = {
    'ㄱ': 'ㄲ',
    'ㄷ': 'ㄸ',
    'ㅂ': 'ㅃ',
    'ㅅ': 'ㅆ',
    'ㅈ': 'ㅉ',
}

const SPLIT_JONG = {}
for (const key in COMPOUND_JONG) {
    SPLIT_JONG[COMPOUND_JONG[key]] = key.split(',')
}

// 복합 모음 → 첫 번째 단순 모음 (backspace용)
const VOWEL_FIRST = {}
for (const key in COMPOUND_VOWEL) {
    VOWEL_FIRST[COMPOUND_VOWEL[key]] = key.split(',')[0]
}

function _compose(cho, jung, jong = '') {
    return String.fromCharCode(
        0xAC00 + (CHOSUNG.indexOf(cho) * 21 + JUNGSUNG.indexOf(jung)) * 28 + JONGSUNG.indexOf(jong)
    )
}

function _decompose(syllable) {
    // 완성형 음절 → (초성, 중성, 종성) 튜플
    const code = syllable.charCodeAt(0) - 0xAC00
    const jong_i = code % 28
    const jung_i = Math.floor(code / 28) % 21
    const cho_i  = Math.floor(Math.floor(code / 28) / 21)

    return [CHOSUNG[cho_i], JUNGSUNG[jung_i], JONGSUNG[jong_i]]
}

class KoreanComposer {
    /*
    지문자 자모를 두벌식 오토마타로 조합해 완성형 한글을 생성한다.

    사용법:
        const c = new KoreanComposer()

        for (const jamo of ['ㅅ', 'ㅏ', 'ㄱ', 'ㅗ', 'ㅏ']) {
            c.add(jamo)
        }

        console.log(c.text)   // → '사과'
    */

    constructor() {
        this._done = []
        this._cho  = null
        this._jung = null
        this._jong = null   // 단순 or 복합 종성
    }

    // ── public ────────────────────────────────────────────────────────

    add(jamo) {
        // 자모 하나 추가
        if (CONSONANTS.has(jamo)) {
            this.inputConsonant(jamo)
        } else if (VOWELS.has(jamo)) {
            this._inputVowel(jamo)
        }
    }

    space() {
        // 현재 조합 중인 음절을 확정하고 공백 추가
        this._commit()
        this._done.push(' ')
    }

    backspace() {
        // 마지막으로 입력된 자모 하나 취소

        if (this._jong !== null) {

            if (this._jong in SPLIT_JONG) {
                // 복합 종성 → 첫째 자음만 남김
                this._jong = SPLIT_JONG[this._jong][0]
            } else {
                this._jong = null
            }

        } else if (this._jung !== null) {

            if (this._jung in VOWEL_FIRST) {
                // 복합 모음 → 첫째 모음으로
                this._jung = VOWEL_FIRST[this._jung]
            } else {
                this._jung = null
            }

        } else if (this._cho !== null) {

            this._cho = null

        } else if (this._done.length > 0) {

            const last = this._done.pop()

            if (last === ' ') {
                return
            }

            const code = last.charCodeAt(0) - 0xAC00

            // 완성형 음절 분해
            if (0 <= code && code < 11172) {
                const [cho, jung, jong] = _decompose(last)

                this._cho  = cho
                this._jung = jung
                this._jong = jong ? jong : null
            }
        }
    }

    clear() {
        // 전체 초기화
        this._done = []
        this._cho = null
        this._jung = null
        this._jong = null
    }

    get text() {
        // 확정된 텍스트 + 현재 조합 중인 음절
        return this._done.join('') + this._current()
    }

    get composing() {
        // 현재 조합 중인 미확정 음절
        return this._current()
    }

    // ── internal ──────────────────────────────────────────────────────

    _current() {
        if (this._cho === null) {
            return ''
        }

        if (this._jung === null) {
            return this._cho
        }

        return _compose(this._cho, this._jung, this._jong || '')
    }

    _commit() {
        const cur = this._current()

        if (cur) {
            this._done.push(cur)
        }

        this._cho = null
        this._jung = null
        this._jong = null
    }

    inputConsonant(c) {

        // 현재 중성(모음) 없음
        if (this._jung === null) {

            // 현재 초성과 같은 자음이고 쌍자음 가능 → 쌍자음으로 합침
            if (this._cho !== null && this._cho === c && c in DOUBLE_CONSONANT) {

                // 예: ㄱ + ㄱ → ㄲ
                this._cho = DOUBLE_CONSONANT[c]

            // 이미 초성 있으면 → 기존 초성 확정, 새 초성 시작
            } else if (this._cho !== null) {

                this._done.push(this._cho)
                this._cho = c

            // 초성 없으면 → 초성으로 설정
            } else {

                this._cho = c
            }

            this._jong = null

        // 현재 중성(모음) 있음 (종성 자리)
        } else {

            // 종성 없음 → 종성으로 설정
            if (this._jong === null) {

                this._jong = c

            // 종성과 같은 자음이고 쌍자음 가능 → 종성 쌍자음
            } else if (this._jong === c && c in DOUBLE_CONSONANT) {

                // 예: 종성 ㅅ + ㅅ → ㅆ
                this._jong = DOUBLE_CONSONANT[c]

            } else {

                // 복합 종성 가능 → 합침
                const comp = COMPOUND_JONG[`${this._jong},${c}`]

                if (comp) {

                    // 예: ㄹ + ㄱ → ㄺ
                    this._jong = comp

                } else {

                    // 그 외 → 현재 음절 확정, 새 초성 시작
                    this._done.push(
                        _compose(this._cho, this._jung, this._jong)
                    )

                    this._cho  = c
                    this._jung = null
                    this._jong = null
                }
            }
        }
    }

    _inputVowel(v) {

        // 초성 없음 → ㅇ(묵음) + 모음
        if (this._cho === null) {

            // 예: ㅏ → 아
            this._cho  = 'ㅇ'
            this._jung = v

        // 초성만 있음 → 중성 추가
        } else if (this._jung === null) {

            // 예: ㄱ + ㅏ → 가
            this._jung = v

        // 초성+중성, 종성 없음 → 복합 모음 시도
        } else if (this._jong === null) {

            const comp = COMPOUND_VOWEL[`${this._jung},${v}`]

            // 가능하면 합침
            if (comp) {

                // 예: ㅗ + ㅏ → ㅘ
                this._jung = comp

            } else {

                // 불가하면 현재 음절 확정, 새 ㅇ+모음
                this._done.push(
                    _compose(this._cho, this._jung)
                )

                this._cho  = 'ㅇ'
                this._jung = v
                this._jong = null
            }

        // 종성 있음 → 종성이 다음 초성으로 이동
        } else {

            // 복합 종성
            if (this._jong in SPLIT_JONG) {

                // 첫째는 종성 유지, 둘째가 다음 초성
                const [first, second] = SPLIT_JONG[this._jong]

                // 예: 닭 + ㅏ → 달가
                this._done.push(
                    _compose(this._cho, this._jung, first)
                )

                this._cho = second

            } else {

                // 단순 종성 → 다음 초성으로 이동
                // 예: 한 + ㅡ → 하느
                this._done.push(
                    _compose(this._cho, this._jung)
                )

                this._cho = this._jong
            }

            this._jung = v
            this._jong = null
        }
    }
}

export default KoreanComposer