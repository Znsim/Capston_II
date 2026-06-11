import KoreanComposer from "./korean_composer";  //

class WordBuilder {
  constructor(dwellSecs = 1.0, spaceSecs = 2.0, cooldown = 0.5) {
    this.dwellSecs = dwellSecs;
    this.spaceSecs = spaceSecs;
    this.cooldown = cooldown;
    this.composer = new KoreanComposer();

    this._curLabel = null;
    this._labelStart = 0;
    this._lastCommitted = null;
    this._committedAt = 0;
  }

  update(label) {
    const now = performance.now() / 1000;
    label = (label && label !== 'none') ? label : null;

    if (label !== this._curLabel) {
      this._curLabel = label;
      this._labelStart = now;
      this._lastCommitted = null;
    }

    const elapsed = now - this._labelStart;
    const canCommit = (now - this._committedAt) > this.cooldown;
    let committed = null;

    if (label === null) {
      const progress = Math.min(elapsed / this.spaceSecs, 1.0);
      if (elapsed >= this.spaceSecs && canCommit && this.composer.composing) {
        this.composer.space();
        this._committedAt = now;
        this._lastCommitted = null;
        committed = ' ';
      }
      return { text: this.composer.text, composing: this.composer.composing, progress, committed };
    } else {
      const progress = Math.min(elapsed / this.dwellSecs, 1.0);
      if (elapsed >= this.dwellSecs && canCommit && label !== this._lastCommitted) {
        this.composer.add(label);
        this._lastCommitted = label;
        this._committedAt = now;
        committed = label;
      }
      return { text: this.composer.text, composing: this.composer.composing, progress, committed };
    }
  }

  backspace() {
    this.composer.backspace();
    this._lastCommitted = null;
  }

  clear() {
    this.composer.clear();
    this._lastCommitted = null;
    this._curLabel = null;
  }
}

export default WordBuilder;