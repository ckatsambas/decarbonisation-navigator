# 0003 · Charts and bilingual interface

- **Date:** 2026-10-24
- **Status:** accepted

## Charts
- **pyqtgraph** for interactive on-screen charts (fast enough to redraw while sliders move,
  and for SMAA distributions with tens of thousands of points).
- **matplotlib** for print-quality figures in the PDF report and in the thesis, so the thesis
  figures and the app's exported figures come from the same code.
- Rejected: an embedded web view with a JavaScript chart library (adds roughly 100 MB to the
  installer) and hand-drawn Qt charts only (slow to extend).

## Language
- All interface text lives in two JSON catalogues, `navigator/i18n/el.json` and `en.json`,
  read through `tr("key")`. Greek is the default.
- Switching language takes effect immediately: every page implements `retranslate()`.
- Rejected: Qt Linguist (`.ts`/`.qm`) files, which need a compile step and are harder for the
  author to edit by hand.
- A test fails if a key exists in one catalogue but not the other.
