"""Step 6 · Report: the decision for management as a PDF, and every table as an Excel workbook (0014-5).

`collect()` reads the other steps and words everything in the chosen language (without switching
the interface); `navigator.report` draws the PDF and writes the workbook."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QPushButton

from ... import __version__
from ...engine import params as PR
from ...engine.mcda import criteria as C
from ...engine.mcda import ranking as RK
from ...engine.mcda import weights as W
from ...i18n import eur_short, language, num, pct, pick, tr, using
from ...report import ReportData, build_pdf, build_xlsx
from ...report.data import Table
from ..maps import option_colors
from ..plans import GROUP_COLOR, letter
from ..widgets import Panel, ReadMore, TrLabel, amp, label
from .base import Page
from .position import Choice

CONFIG_FILES = [("regulation", n) for n in ("eu_ets_maritime", "fueleu", "imo_nzf", "fuels", "markets", "cii",
                                            "activity", "eedi")] + [("market", "prices"), ("model", "imo4_power")]


def _choice(c, default: str) -> str:
    return next((v for v, b in c.buttons.items() if b.isChecked()), default)


def collect(pv, lang: str) -> ReportData:
    """Everything the report needs, worded in `lang`."""
    with using(lang):
        return _collect(pv, lang)


def _collect(pv, lang: str) -> ReportData:
    pos, opt, pri, dec = pv.position_step, pv.options_step, pv.priorities_step, pv.decision_step
    ship = opt.position_ship_name() if hasattr(opt, "position_ship_name") else ""
    model = getattr(opt, "model", None)
    kind = model.cls.label if model is not None and hasattr(model.cls, "label") else ""
    labels = {k: tr(f"rep.{k}") for k in ("summary", "settings", "position", "position_chart", "measures", "plans",
                                          "adaptive", "weights", "ranking", "smaa", "assumptions", "sources", "page",
                                          "axis_cut", "axis_npv", "company", "entropy", "critic", "rank_short",
                                          "legend_ets", "legend_fueleu", "legend_nzf")}
    st = opt.settings()
    settings = [
        (tr("rep.set.view"), tr(f"rep.view.{pv.state.view}")),
        (tr("pos.price"), tr(f"pos.price.{_choice(pos.price, 'central')}")),
        (tr("pos.nzf"), tr(f"nzf.short.{_choice(pos.nzf, 'as_drafted')}")),
        (tr("pos.baseline"), tr(f"base.short.{_choice(pos.base, 'least_cost')}")),
        (tr("opt.start"), str(st["start"])), (tr("opt.life"), tr(f"opt.life.{st['life']}")),
        (tr("opt.prices"), tr(f"pos.price.{st['prices']}")), (tr("opt.rate"), pct(st["rate"])),
        (tr("pri.method"), tr(f"pri.method.{pri.levels['families'].method}")),
    ]
    summary: list[str] = []
    # ---- today's position
    position: dict = {}
    if pos.results:
        res = pos.results
        r = {x.year: x for x in res}
        total = sum(x.total_eur for x in res)
        years = [x.year for x in res]
        position = {"years": years, "ets": [x.ets.cost for x in res], "fueleu": [x.fueleu_cost for x in res],
                    "nzf": [max(x.nzf.cost_eur, 0) for x in res], "sentence": pos.sentence.text()}
        pick_years = [y for y in (2026, 2030, 2035, 2040, 2045, 2050) if y in r]
        head = [tr("rep.col.year"), tr("legend.ets_cost"), tr("legend.fueleu"), tr("legend.nzf"), tr("rep.col.total")]
        fm = ["int", "eur", "eur", "eur", "eur"]
        position["table"] = Table(tr("rep.position"), head, [[y, r[y].ets.cost, r[y].fueleu_cost,
                                                              max(r[y].nzf.cost_eur, 0), r[y].total_eur]
                                                             for y in pick_years], fm)
        position["table_full"] = Table(tr("rep.position"), head, [[x.year, x.ets.cost, x.fueleu_cost,
                                                                   max(x.nzf.cost_eur, 0), x.total_eur] for x in res], fm)
        summary.append(tr("rep.sum.position", ship=ship, total=eur_short(total), y0=years[0], y1=years[-1],
                          c2030=eur_short(r[2030].total_eur) if 2030 in r else "–"))
    # ---- measures
    measures = None
    rows = [x for x in opt.rows if x.ok and x.app]
    if rows:
        measures = Table(tr("rep.measures"), [tr("col.measure"), tr("col.cut"), tr("col.invest"), tr("col.npv"),
                                             tr("col.mac")],
                         [[pick(x.m.name), x.cut[1], x.app.capex_eur, x.app.npv,
                           x.app.cost_per_t if x.app.cost_per_t is not None else "–"] for x in rows],
                         ["text", "pct", "eur", "eur", "num"], tr("rep.measures.note", n=len(rows)))
    # ---- plans
    plans: dict = {}
    pp = opt.plans
    if pp.front is not None and pp.front.plans:
        fr = pp.front.plans
        sel = pp.sel if 0 <= pp.sel < len(fr) else 0
        front = [{"label": letter(i), "npv": f.npv, "avoided": f.avoided} for i, f in enumerate(fr)]
        s = pp.settings()
        tl = [(pick(opt.lib[k].name), y, GROUP_COLOR.get(opt.lib[k].group, "#888888")) for k, y in fr[sel].plan.installs]
        plans = {"front": front, "selected": sel, "sentence": pp.sentence.text(), "timeline": tl,
                 "timeline_title": tr("plan.name", l=letter(sel)), "years": (s.start, s.end or s.start + 19),
                 "table": Table(tr("rep.plans"), [tr("rep.col.plan"), tr("col.npv"), tr("rep.col.avoided"),
                                                  tr("col.invest"), tr("rep.col.payback"), tr("rep.col.steps")],
                                [[letter(i), f.npv, f.avoided, f.appraisal.capex_eur, f.appraisal.payback_year or "–",
                                  "; ".join(f"{y} {pick(opt.lib[k].name)}" for k, y in f.plan.installs)]
                                 for i, f in enumerate(fr)], ["text", "eur", "num", "eur", "text", "text"])}
        best = max(range(len(fr)), key=lambda i: fr[i].npv)
        summary.append(tr("rep.sum.plan", l=letter(best), npv=eur_short(fr[best].npv), k=len(fr[best].plan.keys),
                          cut=num(fr[best].avoided / 1e3)))
        ad = pp.adaptive_result
        if ad is not None:
            now = ", ".join(pick(opt.lib[k].name) for k in ad.now.keys) or tr("plan.nothing_now")
            rows_ad = []
            for b in ad.branches:
                later = "; ".join(f"{y} {pick(opt.lib[k].name)}" for k, y in b.plan.installs if y > ad.decide_after)
                rows_ad.append([tr(f"plan.market.{b.market}"), tr(f"nzf.short.{b.nzf}"), b.prob, b.npv,
                                later or tr("plan.nothing_more")])
            plans["adaptive"] = {
                "sentence": pp.ad_sentence.text(), "now": f"{tr('plan.now', y=ad.decide_after)} {now}",
                "table": Table(tr("rep.adaptive"), [tr("rep.col.market"), "IMO NZF", tr("rep.col.prob"), tr("col.npv"),
                                                    tr("rep.col.later")], rows_ad, ["text", "text", "pct", "eur", "text"])}
            summary.append(tr("rep.sum.adaptive", y=ad.decide_after, now=now, flex=eur_short(ad.value_of_flexibility)))
    # ---- weights
    weights: dict = {}
    w = pri.global_weights()
    names = [tr(f"crit.{c.key}") for c in C.CRITERIA]
    alts = opt.alternatives()
    ent = cri = None
    if len(alts) >= 2:
        x = C.matrix(alts)
        ent, cri = W.entropy(x, C.MAXIMISE).weights, W.critic(x, C.MAXIMISE).weights
    fam_r = pri.results.get("families")
    weights = {"names": names, "company": list(w), "entropy": list(ent) if ent is not None else None,
               "critic": list(cri) if cri is not None else None,
               "sentence": tr("rep.weights.sentence", method=tr(f"pri.method.{pri.levels['families'].method}")),
               "status": pri.levels["families"].status.text() if fam_r else "",
               "table": Table(tr("rep.weights"), [tr("col.criterion"), tr("pri.yours"), tr("pri.entropy"),
                                                  tr("pri.critic")],
                              [[names[i], float(w[i]), float(ent[i]) if ent is not None else "–",
                                float(cri[i]) if cri is not None else "–"] for i in range(len(names))],
                              ["text", "pct", "pct", "pct"])}
    # ---- ranking and SMAA
    ranking = None
    smaa: dict = {}
    if len(dec.alts) >= 2 and hasattr(dec, "rankings"):
        mean, cons, _corr = RK.consensus(dec.rankings)
        order = np.argsort(cons, kind="stable")
        head = [tr("col.option"), *[tr(f"method.{m}") for m in RK.METHODS], tr("dec.consensus"), tr("crit.npv")]
        ranking = Table(tr("rep.ranking"), head,
                        [[dec.name(dec.alts[i].key), *[int(dec.rankings[m].rank[i]) for m in RK.METHODS], int(cons[i]),
                          dec.alts[i].values["npv"]] for i in order],
                        ["text", "int", "int", "int", "int", "int", "eur"],
                        "\n".join(t for t in (dec.sentence.text(), dec.agree.text()) if t))
        summary.append(dec.sentence.text())
        res = dec.smaa
        if res is not None:
            o2 = np.argsort(res.expected_rank(), kind="stable")
            keys = [res.keys[i] for i in o2]
            cols = option_colors(keys, getattr(dec, "best_key", None), C.DO_NOTHING)
            smaa = {"names": [dec.name(k) for k in keys], "acceptability": res.acceptability[o2].tolist(),
                    "expected": [float(res.expected_rank()[i]) for i in o2], "colors": cols,
                    "sentence": dec.smaa_sentence.text(),
                    "table": Table(tr("rep.smaa"), [tr("col.option"), tr("dec.first"), tr("dec.exp_rank"), tr("dec.conf")],
                                   [[dec.name(res.keys[i]), float(res.acceptability[i, 0]), float(res.expected_rank()[i]),
                                     float(res.confidence[i])] for i in o2], ["text", "pct", "num1", "pct"])}
            summary.append(dec.smaa_sentence.text())
            fan_key = dec.fan_pick.currentData()
            if fan_key and "paths" in res.details and fan_key in res.details["paths"]:
                j = res.keys.index(fan_key)
                finals = res.values["npv"][:, j]
                gain = float((finals >= 0).mean())
                smaa["fan"] = {"title": f"{tr('dec.fan')} · {dec.name(fan_key)}",
                               "years": [int(y) for y in res.details["years"]],
                               "paths": res.details["paths"][fan_key][:300].tolist(),
                               "shares": f"{pct(gain)} {tr('dec.fan.gain')}\n{pct(1 - gain)} {tr('dec.fan.loss')}"}
    # ---- assumptions and sources
    rows_as, sources, seen = [], [], set()
    for folder, name in CONFIG_FILES:
        try:
            ps = PR.load(name, base_dir=PR.CONFIG_DIR / folder)
        except (FileNotFoundError, KeyError, ValueError):
            continue
        for prm in ps.unverified():
            v = prm.value
            vs = (str(v) if not isinstance(v, dict) else ", ".join(f"{k}: {x}" for k, x in list(v.items())[:4]))[:40]
            rows_as.append([f"{name}.{prm.key}", vs, prm.note or ps.sources.get(prm.source, PR.Source("", prm.source)).title])
        for s in ps.sources.values():
            if s.title not in seen:
                seen.add(s.title)
                sources.append((s.title, s.url, s.checked))
    for s in opt.lib.sources.values():
        if s.title not in seen:
            seen.add(s.title)
            sources.append((s.title, s.url, s.checked))
    assumptions = Table(tr("rep.assumptions"), [tr("rep.col.param"), tr("rep.col.value"), tr("rep.col.note")], rows_as,
                        ["text", "text", "text"], tr("rep.assumptions.note", n=len(rows_as)))
    summary.append(tr("rep.sum.caveats", n=len(rows_as)))
    return ReportData(lang, tr("rep.title"), f"{ship}{' · ' + kind if kind else ''}", dt.date.today().isoformat(),
                      __version__, labels, [s for s in summary if s], settings, position, measures, plans, weights,
                      ranking, smaa, assumptions, sources)


class StepReport(Page):
    title_key = "step.6.q"
    lede_key = "step.6.lede"
    title_style = ("Question", "QuestionLede")

    def __init__(self, state, project_view):
        super().__init__(state)
        self.pv = project_view
        p = Panel("rep.panel")
        h = QHBoxLayout()
        h.addWidget(TrLabel("rep.lang", "SectionTitle"))
        self.lang = Choice([("el", "rep.lang.el"), ("en", "rep.lang.en")])
        self.lang.set_value(language())
        self.lang.picked.connect(lambda v: (self.lang.set_value(v), self.refresh()))
        h.addWidget(self.lang)
        h.addStretch(1)
        p.body.addLayout(h)
        self.preview = label("", "Sentence", wrap=True)
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        p.body.addWidget(self.preview)
        b = QHBoxLayout()
        self.pdf_btn = QPushButton()
        self.pdf_btn.setObjectName("Primary")
        self.pdf_btn.clicked.connect(lambda: self.export("pdf"))
        self.xlsx_btn = QPushButton()
        self.xlsx_btn.setObjectName("Choice")
        self.xlsx_btn.clicked.connect(lambda: self.export("xlsx"))
        b.addWidget(self.pdf_btn)
        b.addWidget(self.xlsx_btn)
        self.status = label("", "Muted", wrap=True)
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        b.addWidget(self.status, 1)
        p.body.addLayout(b)
        p.body.addWidget(ReadMore("rep.more"))
        self.lay.addWidget(p)
        self.lay.addStretch(1)
        self.retranslate_buttons()

    def lang_value(self) -> str:
        return _choice(self.lang, language())

    def refresh(self) -> None:
        try:
            data = collect(self.pv, self.lang_value())
        except Exception as e:  # noqa: BLE001 - a preview must never break the page
            self.preview.setText(str(e))
            return
        self.preview.setText("<br>".join(f"• {s}" for s in data.summary))

    def showEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().showEvent(e)
        self.refresh()

    def default_path(self, ext: str) -> Path:
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or str(Path.home())
        ship = (self.pv.project.name if self.pv.project else "navigator").strip() or "navigator"
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in ship).strip()
        return Path(docs) / f"{safe} - {tr('rep.file')} {dt.date.today().isoformat()}.{ext}"

    def export(self, kind: str, path: str | None = None) -> Path | None:
        if path is None:
            filt = "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)"
            path, _ = QFileDialog.getSaveFileName(self, tr("rep.save"), str(self.default_path(kind)), filt)
            if not path:
                return None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data = collect(self.pv, self.lang_value())
            out = build_pdf(data, path) if kind == "pdf" else build_xlsx(data, path)
        except Exception as e:  # noqa: BLE001 - reported to the user
            self.status.setText(tr("rep.failed", msg=str(e)))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        url = QUrl.fromLocalFile(str(out.parent)).toString()
        self.status.setText(tr("rep.saved", name=out.name) + f' · <a href="{url}">{tr("rep.open_folder")}</a>')
        return out

    def retranslate_buttons(self) -> None:
        self.pdf_btn.setText(amp(tr("rep.pdf")))
        self.xlsx_btn.setText(amp(tr("rep.xlsx")))

    def on_language(self) -> None:
        self.lang.retranslate()
        self.retranslate_buttons()
        self.refresh()

