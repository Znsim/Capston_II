import KoreanComposer from "./korean_composer";

const compose = (...jamo) => {
  const composer = new KoreanComposer();
  jamo.forEach((value) => composer.add(value));
  return composer;
};

describe("KoreanComposer", () => {
  test.each([
    [["ㅇ", "ㅗ", "ㅏ"], "와"],
    [["ㅇ", "ㅜ", "ㅓ"], "워"],
    [["ㅇ", "ㅡ", "ㅣ"], "의"],
  ])("복합 모음을 조합한다: %j", (input, expected) => {
    expect(compose(...input).text).toBe(expected);
  });

  test.each([
    [["ㄱ", "ㄱ", "ㅏ"], "까"],
    [["ㄷ", "ㄷ", "ㅏ"], "따"],
    [["ㅂ", "ㅂ", "ㅏ"], "빠"],
    [["ㅅ", "ㅅ", "ㅏ"], "싸"],
    [["ㅈ", "ㅈ", "ㅏ"], "짜"],
  ])("쌍자음을 조합한다: %j", (input, expected) => {
    expect(compose(...input).text).toBe(expected);
  });

  test("받침을 다음 음절의 초성으로 이동한다", () => {
    expect(compose("ㄱ", "ㅏ", "ㄴ", "ㅏ").text).toBe("가나");
  });

  test("복합 받침의 뒤 자음을 다음 음절로 이동한다", () => {
    expect(compose("ㄷ", "ㅏ", "ㄹ", "ㄱ", "ㅏ").text).toBe("달가");
  });

  test("복합 모음을 한 단계씩 삭제한다", () => {
    const composer = compose("ㅇ", "ㅗ", "ㅏ");
    composer.backspace();
    expect(composer.text).toBe("오");
    composer.backspace();
    expect(composer.text).toBe("ㅇ");
    composer.backspace();
    expect(composer.text).toBe("");
  });

  test("공백과 초기화를 처리한다", () => {
    const composer = compose("ㄱ", "ㅏ");
    composer.space();
    expect(composer.text).toBe("가 ");
    composer.backspace();
    expect(composer.text).toBe("가");
    composer.clear();
    expect(composer.text).toBe("");
  });
});
