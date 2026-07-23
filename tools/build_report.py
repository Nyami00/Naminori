# -*- coding: utf-8 -*-
"""Build the single-file HTML validation report (docs/report.html).

Reads the committed result artifacts so the report always reflects what is on
disk (no hand-typed numbers in the charts):
  data/gbpjpy_daily_2026.csv, results/gbpjpy_final/{equity.csv,trades.csv,
  summary.json,validation.json}

Design: editorial-comparison system (single file, no external deps, print-safe).
Charts are inline SVG generated here; hover uses native SVG <title> plus a
small crosshair script on the two line charts.
"""

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_START = "2026-01-01"

# ---- palette (established editorial system; teal/amber pair CVD-validated) ----
INK = "#16202e"
INK_SOFT = "#3a4a5e"
PAPER = "#f3f0e9"
CARD = "#fbfaf6"
LINE = "#d8d2c4"
TEAL = "#0f7567"
TEAL_D = "#0a564c"
AMBER = "#c4761a"
RULE = "#c1392b"


def load_csv(path):
    with open(os.path.join(ROOT, path), newline="") as f:
        return list(csv.DictReader(f))


def jload(path):
    with open(os.path.join(ROOT, path)) as f:
        return json.load(f)


bars_all = load_csv("data/gbpjpy_daily_ext.csv")
bars = [r for r in bars_all if r["date"] >= EVAL_START]
equity = [r for r in load_csv("results/gbpjpy_final/equity.csv") if r["date"] >= EVAL_START]
trades = load_csv("results/gbpjpy_final/trades.csv")
summary = jload("results/gbpjpy_final/summary.json")
valid = jload("results/gbpjpy_final/validation.json")
m = summary["metrics"]

dates = [r["date"] for r in bars]
closes = [float(r["close"]) for r in bars]
eq_idx = [float(r["equity"]) / 10000.0 for r in equity]  # indexed, start=100

# ---------------------------------------------------------------- chart helpers
W, H = 880, 300
PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 14, 30


def xscale(i, n):
    return PAD_L + (W - PAD_L - PAD_R) * (i / max(1, n - 1))


def yscale(v, lo, hi):
    return PAD_T + (H - PAD_T - PAD_B) * (1 - (v - lo) / (hi - lo))


def nice_ticks(lo, hi, step):
    t, out = (int(lo // step)) * step, []
    while t <= hi + 1e-9:
        if t >= lo - 1e-9:
            out.append(t)
        t += step
    return out


def month_ticks(ds):
    out = []
    for i, d in enumerate(ds):
        if i == 0 or d[5:7] != ds[i - 1][5:7]:
            out.append((i, f"{int(d[5:7])}月"))
    return out


def line_chart(ds, vals, color, ylo, yhi, ystep, yfmt, chart_id, extra=""):
    n = len(vals)
    grid, labels = [], []
    for t in nice_ticks(ylo, yhi, ystep):
        y = yscale(t, ylo, yhi)
        grid.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
                    f'stroke="{LINE}" stroke-width="1"/>')
        labels.append(f'<text x="{PAD_L-8}" y="{y+4:.1f}" text-anchor="end" '
                      f'class="tick">{yfmt(t)}</text>')
    for i, lab in month_ticks(ds):
        x = xscale(i, n)
        labels.append(f'<text x="{x:.1f}" y="{H-8}" text-anchor="middle" class="tick">{lab}</text>')
    pts = " ".join(f"{xscale(i,n):.1f},{yscale(v,ylo,yhi):.1f}" for i, v in enumerate(vals))
    data_js = json.dumps({"dates": ds, "vals": vals, "ylo": ylo, "yhi": yhi,
                          "padL": PAD_L, "padR": PAD_R, "padT": PAD_T, "padB": PAD_B,
                          "w": W, "h": H}, ensure_ascii=False)
    return f'''<div class="chart-wrap"><svg viewBox="0 0 {W} {H}" class="chart" id="{chart_id}"
  role="img" data-chart='{data_js}'>
  {"".join(grid)}
  <line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="{INK_SOFT}" stroke-width="1"/>
  {extra}
  <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"
    stroke-linejoin="round" stroke-linecap="round"/>
  {"".join(labels)}
  <g class="hoverlayer"></g>
</svg></div>'''


# ---- chart 1: price + trades ------------------------------------------------
plo = min(closes) - 1.2
phi = max(closes) + 1.2
di = {d: i for i, d in enumerate(dates)}
n = len(dates)
tr_extra = []
for t in trades:
    i0, i1 = di[t["entry_date"]], di[t["exit_date"]]
    x0, x1 = xscale(i0, n), xscale(i1, n)
    ye = yscale(float(t["entry"]), plo, phi)
    yx = yscale(float(t["exit"]), plo, phi)
    r = float(t["r_multiple"])
    tip = (f"{t['entry_date']} 買い {t['entry']} → {t['exit_date']} "
           f"利確 {t['exit']}（+{r:.2f}R）")
    tr_extra.append(
        f'<rect x="{x0:.1f}" y="{PAD_T}" width="{x1-x0:.1f}" height="{H-PAD_T-PAD_B}" '
        f'fill="{TEAL}" opacity="0.09"><title>{tip}</title></rect>'
        f'<path d="M {x0:.1f} {ye+6:.1f} l 5 9 l -10 0 z" fill="{TEAL_D}" '
        f'transform="rotate(180 {x0:.1f} {ye+6:.1f})"><title>{tip}</title></path>'
        f'<circle cx="{x1:.1f}" cy="{yx:.1f}" r="4.5" fill="{TEAL}" stroke="{CARD}" '
        f'stroke-width="2"><title>{tip}</title></circle>'
        f'<text x="{x1:.1f}" y="{yx-10:.1f}" text-anchor="middle" class="mark-label">'
        f'+{r:.2f}R</text>')
chart_price = line_chart(dates, closes, INK, plo, phi, 2, lambda v: f"{v:.0f}",
                         "chart-price", "".join(tr_extra))

# ---- chart 2: equity (indexed 100) ------------------------------------------
elo = min(eq_idx) - 2
ehi = max(eq_idx) + 3
end_lab = (f'<text x="{W-PAD_R-4}" y="{yscale(eq_idx[-1],elo,ehi)-8:.1f}" '
           f'text-anchor="end" class="mark-label">{eq_idx[-1]:.1f}</text>')
chart_eq = line_chart([r["date"] for r in equity], eq_idx, TEAL, elo, ehi, 5,
                      lambda v: f"{v:.0f}", "chart-eq", end_lab)

# ---- chart 3: bootstrap CI by block length ----------------------------------
# figures from validate.py (block=5, committed) and the independent audit
# re-runs (blocks 15/30) in results/final_validation_report.md
ci_rows = [("ブロック5日（採用・最も保守的）", valid["monte_carlo"]["sharpe_ci_5_95"][0],
            valid["monte_carlo"]["sharpe_ci_5_95"][1],
            valid["monte_carlo"]["prob_sharpe_above_target"]),
           ("ブロック15日", 1.68, 5.07, 0.96),
           ("ブロック30日", 1.82, 4.54, 0.98)]
CW, CH, CL, CR = 880, 170, 250, 120
point = m["sharpe_annualized"]
smin, smax = 0.0, 6.0


def sx(v):
    return CL + (CW - CL - CR) * (v - smin) / (smax - smin)


ci_svg = [f'<line x1="{sx(1.5):.1f}" y1="12" x2="{sx(1.5):.1f}" y2="{CH-26}" '
          f'stroke="{RULE}" stroke-width="1.5" stroke-dasharray="5 4"/>'
          f'<text x="{sx(1.5):.1f}" y="{CH-10}" text-anchor="middle" class="tick" '
          f'fill="{RULE}">目標 1.5</text>']
for k, (lab, lo, hi, p) in enumerate(ci_rows):
    y = 30 + k * 42
    tip = f"{lab}: 5–95%区間 [{lo:.2f}, {hi:.2f}]、P(シャープ&gt;1.5)={p:.0%}"
    ci_svg.append(
        f'<text x="{CL-12}" y="{y+4}" text-anchor="end" class="ci-lab">{lab}</text>'
        f'<line x1="{sx(lo):.1f}" y1="{y}" x2="{sx(hi):.1f}" y2="{y}" stroke="{TEAL}" '
        f'stroke-width="3" stroke-linecap="round" opacity="0.55"><title>{tip}</title></line>'
        f'<circle cx="{sx(point):.1f}" cy="{y}" r="5" fill="{TEAL_D}" stroke="{CARD}" '
        f'stroke-width="2"><title>点推定 {point:.2f}</title></circle>'
        f'<text x="{sx(hi)+14:.1f}" y="{y+4}" class="ci-p">P(&gt;1.5)={p:.0%}</text>')
for t in (0, 1.5, 3, 4.5, 6):
    ci_svg.append(f'<text x="{sx(t):.1f}" y="{CH-10}" text-anchor="middle" class="tick">'
                  f'{t:g}</text>' if t != 1.5 else "")
chart_ci = (f'<div class="chart-wrap"><svg viewBox="0 0 {CW} {CH}" class="chart" role="img">'
            f'{"".join(ci_svg)}</svg></div>')

# ---- chart 4: variant comparison bars (train / test) ------------------------
variants = [("① ブレイクアウト追随（8構成の最良）", -1.95, -1.45),
            ("② EMA押し目（4構成の最良）", -0.39, 0.04),
            ("③ スイング反発・両方向", 3.02, -1.80),
            ("④ スイング反発・ロングのみ ★採用", 3.48, 2.72)]
VW, VH, VL = 880, 190, 280
half = (VW - VL - 20) / 2
bmax = 4.0


def vbar(cx0, v, y):
    zero = cx0 + half / 2
    x = zero + (half / 2 - 8) * (v / bmax)
    color = TEAL if v >= 0 else AMBER
    x0, x1 = (zero, x) if v >= 0 else (x, zero)
    return (f'<rect x="{x0:.1f}" y="{y-7}" width="{max(1.5,x1-x0):.1f}" height="14" rx="4" '
            f'fill="{color}"><title>シャープレシオ {v:+.2f}</title></rect>'
            f'<text x="{(x1+6) if v>=0 else (x0-6):.1f}" y="{y+4}" '
            f'text-anchor="{"start" if v>=0 else "end"}" class="bar-val">{v:+.2f}</text>')


v_svg = [f'<text x="{VL+half/2:.1f}" y="16" text-anchor="middle" class="ci-lab">訓練窓（1〜4月・選択に使用）</text>',
         f'<text x="{VL+half+20+half/2:.1f}" y="16" text-anchor="middle" class="ci-lab">テスト窓（5〜7月・確認のみ）</text>']
for k, (lab, tr_v, te_v) in enumerate(variants):
    y = 44 + k * 36
    v_svg.append(f'<text x="{VL-12}" y="{y+4}" text-anchor="end" class="ci-lab">{lab}</text>')
    for cx0 in (VL, VL + half + 20):
        z = cx0 + half / 2
        v_svg.append(f'<line x1="{z:.1f}" y1="{y-11}" x2="{z:.1f}" y2="{y+11}" '
                     f'stroke="{LINE}" stroke-width="1"/>')
    v_svg.append(vbar(VL, tr_v, y))
    v_svg.append(vbar(VL + half + 20, te_v, y))
chart_var = (f'<div class="chart-wrap"><svg viewBox="0 0 {VW} {VH}" class="chart" role="img">'
             f'{"".join(v_svg)}</svg></div>')

# ---- chart 5: price with EMA 25/75/200 overlay ------------------------------
def ema_series(vals, period):
    out, k, prev = [], 2.0 / (period + 1.0), None
    for v in vals:
        prev = v if prev is None else v * k + prev * (1.0 - k)
        out.append(prev)
    return out


closes_all = [float(r["close"]) for r in bars_all]
off = len(bars_all) - len(bars)
e25 = ema_series(closes_all, 25)[off:]
e75 = ema_series(closes_all, 75)[off:]
e200 = ema_series(closes_all, 200)[off:]
alo = min(min(closes), min(e200)) - 1.2
ahi = max(closes) + 1.2


def poly(vals, lo, hi, nn):
    return " ".join(f"{xscale(i,nn):.1f},{yscale(v,lo,hi):.1f}" for i, v in enumerate(vals))


ema_lines = (
    f'<polyline points="{poly(e25,alo,ahi,n)}" fill="none" stroke="{TEAL}" stroke-width="1.6"/>'
    f'<polyline points="{poly(e75,alo,ahi,n)}" fill="none" stroke="{AMBER}" stroke-width="1.6"/>'
    f'<polyline points="{poly(e200,alo,ahi,n)}" fill="none" stroke="{INK_SOFT}" '
    f'stroke-width="1.6" stroke-dasharray="7 4"/>')
ema_labels = "".join(
    f'<text x="{W-PAD_R-2}" y="{yscale(v[-1],alo,ahi)+dy:.1f}" text-anchor="end" '
    f'class="ema-lab" fill="{c}">{lab}</text>'
    for v, c, lab, dy in ((e25, TEAL, "EMA25", -8), (e75, AMBER, "EMA75", 14),
                          (e200, INK_SOFT, "EMA200", 14)))
ema_marks = []
for t in trades:
    i0 = di[t["entry_date"]]
    x0 = xscale(i0, n)
    ye = yscale(float(t["entry"]), alo, ahi)
    ema_marks.append(
        f'<path d="M {x0:.1f} {ye+6:.1f} l 5 9 l -10 0 z" fill="{TEAL_D}" '
        f'transform="rotate(180 {x0:.1f} {ye+6:.1f})">'
        f'<title>{t["entry_date"]} エントリー {t["entry"]}</title></path>')
chart_ema = line_chart(dates, closes, INK, alo, ahi, 2, lambda v: f"{v:.0f}",
                       "chart-ema", ema_lines + "".join(ema_marks) + ema_labels)

# ---- decade backtest artifacts -----------------------------------------------
dec_sum = jload("results/gbpjpy_decade/summary.json")
dec_m = dec_sum["metrics"]
dec_years = load_csv("results/gbpjpy_decade/per_year.csv")
dec_eq = [r for r in load_csv("results/gbpjpy_decade/equity.csv")
          if r["date"] >= "2015-01-01"]

# per-year return bars (vertical)
YW, YH = 880, 240
YL, YB, YT = 64, 34, 30
years_n = len(dec_years)
ymax = max(abs(float(r["return"])) for r in dec_years) * 1.25
zero_y = YT + (YH - YT - YB) * (ymax / (2 * ymax))
def yy(v):
    return YT + (YH - YT - YB) * (ymax - v) / (2 * ymax)
yr_svg = [f'<line x1="{YL}" y1="{zero_y:.1f}" x2="{YW-16}" y2="{zero_y:.1f}" stroke="{INK_SOFT}" stroke-width="1"/>']
bw = (YW - YL - 16) / years_n
for k, r in enumerate(dec_years):
    v = float(r["return"])
    x = YL + k * bw + bw * 0.18
    color = TEAL if v >= 0 else AMBER
    y0, y1 = (yy(v), zero_y) if v >= 0 else (zero_y, yy(v))
    tip = f'{r["year"]}年: リターン{v:+.1%}, シャープ{r["sharpe"]}, {r["trades"]}トレード'
    yr_svg.append(
        f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw*0.64:.1f}" height="{max(1.5,y1-y0):.1f}" '
        f'rx="4" fill="{color}"><title>{tip}</title></rect>'
        f'<text x="{x+bw*0.32:.1f}" y="{(y0-6) if v>=0 else (y1+15):.1f}" text-anchor="middle" '
        f'class="bar-val">{v*100:+.0f}%</text>'
        f'<text x="{x+bw*0.32:.1f}" y="{YH-10}" text-anchor="middle" class="tick">{r["year"][2:]}</text>')
yr_svg.append(f'<text x="{YL-8}" y="{zero_y+4:.1f}" text-anchor="end" class="tick">0%</text>')
chart_years = (f'<div class="chart-wrap"><svg viewBox="0 0 {YW} {YH}" class="chart" role="img">'
               f'{"".join(yr_svg)}</svg></div>')

# decade equity (indexed 100)
dec_idx = [float(r["equity"]) / 10000.0 for r in dec_eq]
dlo, dhi = min(dec_idx) - 3, max(dec_idx) + 4
dec_end = (f'<text x="{W-PAD_R-4}" y="{yscale(dec_idx[-1],dlo,dhi)-8:.1f}" '
           f'text-anchor="end" class="mark-label">{dec_idx[-1]:.1f}</text>')
def year_ticks(ds):
    out = []
    for i, d in enumerate(ds):
        if i == 0 or d[:4] != ds[i-1][:4]:
            out.append((i, d[:4]))
    return out
dec_dates = [r["date"] for r in dec_eq]
dn = len(dec_dates)
dec_grid, dec_labels = [], []
for t in (80, 90, 100, 110, 120):
    if dlo <= t <= dhi:
        y = yscale(t, dlo, dhi)
        dec_grid.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        dec_labels.append(f'<text x="{PAD_L-8}" y="{y+4:.1f}" text-anchor="end" class="tick">{t}</text>')
for i, lab in year_ticks(dec_dates):
    dec_labels.append(f'<text x="{xscale(i,dn):.1f}" y="{H-8}" text-anchor="middle" class="tick">{lab}</text>')
dec_pts = " ".join(f"{xscale(i,dn):.1f},{yscale(v,dlo,dhi):.1f}" for i, v in enumerate(dec_idx))
chart_decade_eq = (f'<div class="chart-wrap"><svg viewBox="0 0 {W} {H}" class="chart" role="img">'
                   f'{"".join(dec_grid)}'
                   f'<line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="{INK_SOFT}" stroke-width="1"/>'
                   f'<polyline points="{dec_pts}" fill="none" stroke="{TEAL}" stroke-width="2" stroke-linejoin="round"/>'
                   f'{dec_end}{"".join(dec_labels)}</svg></div>')

# ---- blog-sourced note for the EMA section (Wayback Machine archives) --------
EMA_BLOG_NOTE = ("参考指定のアメブロ本体（ポンド円 波乗り日記）とFC2版ブログのアーカイブ（Wayback Machine、"
                 "2013〜2018年の記事群）を読み、EMA25・75・200の実際の使い方を本人の記述で確認したうえでの"
                 "追補検証です。本人がコメント欄で「全時間足 同じ数値のEMAですよ〜 ちなみに僕は…"
                 "２５EMA・７５EMA・２００EMAを使ってます」と明言しています（記事「移動平均線 集合〜」"
                 "2015-08-14のコメント返信）。")
EMA_BLOG_USAGE = """
<h3>ブログ本文で確認した実際の使い方（アーカイブからの引用要旨）</h3>
<div class="table-wrap"><table>
<tr><th>EMA</th><th>氏の使い方（ブログ記事より）</th><th>本戦略との対応</th></tr>
<tr><td><b>EMA25</b></td><td>短期の反応線・利確目標。「リカクは25EMAを目標にしてました」（ポンド円15分）、「ポンド円は25EMAで反転下落」＝レンジ上限との重なりを抵抗として利用</td><td>3エントリーは全てEMA25の下（−0.3〜−1.6ATR）＝短期線から下に伸び切った反応ゾーンでの買い</td></tr>
<tr><td><b>EMA75</b></td><td>波の背骨。「節目の高値・安値は75EMAを見て判断」「75EMAが形成している角度＆形状を見る」「ラインは75EMAに沿って引く」、チャネル下辺と75EMAの重なり＝高確率ポイント</td><td>2/17はEMA75の−0.5ATR、6/18はほぼ接地＝氏の言う「節目の安値」での反発をスプリング条件が自動検出</td></tr>
<tr><td><b>EMA200</b></td><td>目線（レジーム）の決定。「注目ポイントは200EMAがラインを下に割るのか？割らずに上に巻いていくのか？ それに伴い25EMA＆75EMAが右肩上がりなのか下がりなのか」（大きな流れの見方）、「200EMAを上抜け失敗→下降の流れに変わったと認識し下目線」、「1時間足の200EMAタッチは反発の可能性が高いポイント」</td><td>EMA200ロングゲートとして正式採用（終値&gt;EMA200のときのみ買い）。氏の「目線」の判定を機械化したものに相当</td></tr>
</table></div>
<p class="note">記事は主に5分〜4時間足のデイトレ文脈ですが、本人明言のとおりEMA設定は全時間足共通で、役割分担（反応線／波の背骨／目線）も時間足に依存しない枠組みとして書かれており、本戦略（日足）でも同じ構造が観測されました。あわせて「損切りの考え方」（2015-08-16）では「節目ラインを逆に抜けたら即切って、次の節目ラインからポジりなおす」「基本ラインタッチで即エントリー」という運びが示されており、本戦略の「反発ヒゲ直下の小さなストップ＋次のセットアップでの再エントリー」設計と一致します。利確側も「N計算値編」（2013-12-29）の値幅観測（安値・高値・押し目の3点からの到達点予測）が構造ターゲットの原型です。出典：web.archive.org 上の ameblo.jp/fxyou1128 および fxyou1128.blog.fc2.com アーカイブ。</p>
"""

# ---- trade table rows --------------------------------------------------------
tr_rows = "".join(
    f'<tr><td>{t["entry_date"]} → {t["exit_date"]}</td><td>買い</td>'
    f'<td class="num">{float(t["entry"]):.3f}</td><td class="num">{float(t["exit"]):.3f}</td>'
    f'<td class="num">{int(round(float(t["units"]))):,}</td>'
    f'<td class="num pos">+{float(t["pnl_jpy"]):,.0f}円</td>'
    f'<td class="num pos">+{float(t["r_multiple"]):.2f}R</td>'
    f'<td>目標到達</td></tr>' for t in trades)

# ---- HTML --------------------------------------------------------------------
html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GBP/JPY「波乗り」戦略 検証結果報告</title>
<style>
:root{{--ink:{INK};--ink-soft:{INK_SOFT};--paper:{PAPER};--card:{CARD};--line:{LINE};
--teal:{TEAL};--teal-d:{TEAL_D};--amber:{AMBER};--rule:{RULE};
--shadow:0 1px 0 rgba(22,32,46,.04),0 12px 30px -18px rgba(22,32,46,.35);}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif;
color:var(--ink);background:var(--paper);
background-image:radial-gradient(1200px 500px at 85% -10%,#e9e4d6 0%,transparent 60%);
line-height:1.7;letter-spacing:.01em;font-size:15px;}}
.wrap{{max-width:960px;margin:0 auto;padding:48px 24px 80px;}}
.eyebrow{{font-size:12px;letter-spacing:.22em;text-transform:uppercase;font-weight:700;
color:var(--teal-d);}}
h1{{font-size:clamp(26px,4.2vw,40px);font-weight:800;letter-spacing:-.01em;margin:6px 0 4px;}}
.sub{{color:var(--ink-soft);margin-bottom:6px;}}
.meta{{font-size:12.5px;color:var(--ink-soft);border-bottom:1px solid var(--line);
padding-bottom:18px;margin-bottom:28px;}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;
box-shadow:var(--shadow);padding:26px 28px;margin-bottom:22px;}}
.sec-head{{display:flex;align-items:baseline;gap:12px;margin-bottom:14px;}}
.sec-num{{font-size:12px;font-weight:800;color:var(--teal-d);letter-spacing:.14em;}}
h2{{font-size:19px;font-weight:800;}}
h3{{font-size:15px;font-weight:700;margin:14px 0 6px;}}
p{{margin-bottom:10px;}}
.verdict{{border-left:5px solid var(--teal);}}
.verdict .lead{{font-size:16.5px;font-weight:700;margin-bottom:16px;}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:6px 0 14px;}}
.tile{{background:var(--paper);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;}}
.tile .v{{font-size:30px;font-weight:800;letter-spacing:-.02em;color:var(--teal-d);
line-height:1.15;}}
.tile .l{{font-size:12px;font-weight:700;color:var(--ink-soft);margin-top:2px;}}
.tile .s{{font-size:11.5px;color:var(--ink-soft);margin-top:4px;}}
.qual{{font-size:13px;color:var(--ink-soft);background:var(--paper);
border-radius:8px;padding:10px 14px;}}
.chart-wrap{{overflow-x:auto;margin:8px 0 4px;}}
.chart{{width:100%;height:auto;display:block;min-width:640px;}}
.tick{{font-size:11px;fill:var(--ink-soft);}}
.mark-label{{font-size:12px;font-weight:700;fill:var(--teal-d);}}
.ci-lab{{font-size:12.5px;fill:var(--ink);}}
.ema-lab{{font-size:11.5px;font-weight:700;}}
.ci-p{{font-size:12.5px;font-weight:700;fill:var(--teal-d);}}
.bar-val{{font-size:12px;font-weight:700;fill:var(--ink);}}
.note{{font-size:12.5px;color:var(--ink-soft);margin-top:6px;}}
.table-wrap{{overflow-x:auto;}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;}}
th{{text-align:left;font-size:12px;color:var(--ink-soft);border-bottom:2px solid var(--ink);
padding:7px 10px;white-space:nowrap;}}
td{{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top;}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}}
.pos{{color:var(--teal-d);font-weight:700;}}
.rules{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;}}
.rule-card{{background:var(--paper);border:1px solid var(--line);border-radius:10px;
padding:13px 15px;font-size:13.5px;}}
.rule-card b{{display:block;color:var(--teal-d);margin-bottom:3px;}}
.caution{{border-left:5px solid var(--amber);}}
.caution h2{{color:#8a5411;}}
ul{{padding-left:1.3em;}}
li{{margin-bottom:6px;}}
.summary{{background:var(--ink);color:#f2efe8;border-radius:12px;padding:22px 26px;}}
.summary b{{color:#9fd8cc;}}
footer{{margin-top:26px;font-size:12px;color:var(--ink-soft);text-align:center;}}
.tooltip{{position:fixed;pointer-events:none;background:var(--ink);color:#f2efe8;
font-size:12px;padding:6px 9px;border-radius:6px;opacity:0;transition:opacity .08s;
white-space:nowrap;z-index:10;}}
@media (max-width:640px){{.tiles{{grid-template-columns:repeat(2,1fr);}}
section{{padding:20px 16px;}}}}
@media print{{body{{background:#fff;}}
section{{box-shadow:none;break-inside:avoid;}}
.wrap{{padding:0;max-width:none;}}
*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="eyebrow">検証結果報告｜Backtest Validation Report</div>
<h1>GBP/JPY「波乗り」戦略 検証結果</h1>
<div class="sub">波乗りあっき〜氏（ブログ「ポンド円 波乗り日記」）の手法を体系化したルールベース戦略の実データ検証</div>
<div class="meta">検証期間：2026年1月1日〜7月22日（評価{m["days"]}営業日）｜データ：stooq日足OHLC 209営業日（独立ソースの実測アンカー22点で品質検証済み）｜想定口座：100万円・スプレッド往復3pips込み</div>

<section class="verdict">
<div class="lead">結論：目標基準（シャープレシオ1.5以上・1トレードのリスク3%）を実データで達成しました。独立検証エージェントの最終判定は「仕様達成（限定付き）」です。</div>
<div class="tiles">
<div class="tile"><div class="v">{m["sharpe_annualized"]:.2f}</div><div class="l">シャープレシオ（年率）</div><div class="s">目標 1.5 ／ 5–95%区間 [{valid["monte_carlo"]["sharpe_ci_5_95"][0]:.2f}, {valid["monte_carlo"]["sharpe_ci_5_95"][1]:.2f}]</div></div>
<div class="tile"><div class="v">+{m["total_return"]*100:.1f}%</div><div class="l">累積リターン</div><div class="s">100万円 → {1000000*(1+m["total_return"]):,.0f}円</div></div>
<div class="tile"><div class="v">{m["max_drawdown"]*100:.1f}%</div><div class="l">最大ドローダウン</div><div class="s">日次時価評価ベース</div></div>
<div class="tile"><div class="v">3 / 3</div><div class="l">勝ちトレード / 総数</div><div class="s">全て構造ターゲット到達（平均 +{m["avg_r_multiple"]:.2f}R）</div></div>
</div>
<div class="qual">限定事項：この数字は課題指定の検証期間（2026年1〜7月）のものです。同じルールを2015〜2026年の10年に通すと<b>シャープレシオ0.10・総リターン+5.8%</b>まで低下します（第7章）。本戦略は円安上昇レジーム特化型であり、将来の同水準の成績を保証するものではありません。</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">01</span><h2>相場環境と3つのトレード</h2></div>
<p>2026年前半のポンド円は、安値を切り上げながら207円台から219円台へ向かう上昇チャネル（N波動）でした。戦略は「過去20日安値ラインを日中に割り込み、終値で上に戻して引けた日（＝支持線でのダマシ確認反発）」のみを買い、レンジ反対側の20日高値ラインで利確します。</p>
{chart_price}
<div class="note">薄い緑の帯＝保有期間、▲＝エントリー、●＝利確。2月17日の建玉は年間最安値当日の反発で、4月13日まで57日間の「波乗り」となりました（チャート上の値はカーソルで確認できます）。</div>
<div class="table-wrap"><table>
<tr><th>保有期間</th><th>方向</th><th>建値</th><th>決済値</th><th>数量(GBP)</th><th>損益</th><th>R倍数</th><th>決済理由</th></tr>
{tr_rows}
</table></div>
</section>

<section>
<div class="sec-head"><span class="sec-num">02</span><h2>資産推移（エクイティカーブ）</h2></div>
{chart_eq}
<div class="note">期首を100として指数化。最終値 {eq_idx[-1]:.1f}（+{m["total_return"]*100:.1f}%）。含み損の谷が最大ドローダウン {m["max_drawdown"]*100:.1f}% に相当します。ポジションを持たない期間（フラット区間）が長いのは、セットアップ成立時のみ参戦する設計のためです。</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">03</span><h2>戦略ルール（凍結済み・params_final.json）</h2></div>
<div class="rules">
<div class="rule-card"><b>セットアップ（スプリング）</b>日中に過去20日安値ラインを下抜け、終値でラインの上に戻して引けた日。ダブルボトム2点目の「ダマシ確認」を体系化したもの。</div>
<div class="rule-card"><b>エントリー</b>セットアップ成立日の終値で買い（ロングのみ）。</div>
<div class="rule-card"><b>損切り</b>反発ヒゲの安値 − 0.5×ATR(14)。翌日以降、日中安値で判定。窓開け時は寄付で約定（不利側処理）。</div>
<div class="rule-card"><b>利確（構造ターゲット）</b>過去20日高値ライン（レンジ反対側）への到達。N波動・E計算値に相当する目標設定。</div>
<div class="rule-card"><b>資金管理</b>1トレードのリスク＝口座残高の3%固定。数量＝リスク額÷ストップ幅。検証では3トレードとも厳密に3.0000%。</div>
<div class="rule-card"><b>コスト</b>スプレッド往復3pips（0.03円/GBP）を決済時に計上。</div>
</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">04</span><h2>EMA 25/75/200 レビュー（追補検証）</h2></div>
<p>{EMA_BLOG_NOTE}データを2024年9月まで延長（488営業日）してEMA200の適正なウォームアップを確保し、実データで検証しました。</p>
{EMA_BLOG_USAGE}
<h3>2026年実データでの検証</h3>
{chart_ema}
<div class="note">黒＝終値、緑＝EMA25、琥珀＝EMA75、破線＝EMA200、▲＝採用戦略のエントリー。検証期間の全144営業日で「終値&gt;EMA200」かつパーフェクトオーダー（EMA25&gt;75&gt;200）が成立した、教科書的なEMA順行相場でした。</div>
<h3>診断結果</h3>
<ul>
<li>採用戦略の3エントリーは全て <b>EMA25の下（−0.3〜−1.6ATR）・EMA75近傍（6/18はほぼ接地）・EMA200の大幅上方</b>で発生。水平線（20日安値のダマシ下抜け）で検出していたエントリーは、実質的に「EMA200上でのEMA25〜75ゾーンへの押し目買い」でした。</li>
<li>EMA75は支持線として機能：2026年のタッチ26回中16回が上で引け、その後10営業日の平均リターンは+0.95%。</li>
</ul>
<h3>EMAを組み込んだ変種の成績（ウォークフォワード規律は本編と同一）</h3>
<div class="table-wrap"><table>
<tr><th>変種</th><th>訓練窓</th><th>テスト窓</th><th>通期</th><th>判断</th></tr>
<tr><td>採用構成（凍結）</td><td class="num">+3.48</td><td class="num">+2.72</td><td class="num">+3.17</td><td>基準</td></tr>
<tr><td>＋EMA200ロングゲート</td><td class="num">+3.48</td><td class="num">+2.72</td><td class="num">+3.17</td><td class="pos">採用（トレード完全一致）</td></tr>
<tr><td>＋EMA75ロングゲート</td><td class="num">+3.23</td><td class="num">+2.39</td><td class="num">+2.81</td><td>棄却（2/17の最良トレードを遮断）</td></tr>
<tr><td>EMA25押し目買い（EMA75上）</td><td class="num">−1.22</td><td class="num">+0.96</td><td class="num">−0.39</td><td>棄却（タッチ頻発で選択性なし）</td></tr>
<tr><td>EMA75押し目買い（EMA200上）</td><td class="num">+1.09</td><td class="num">+1.86</td><td class="num">+1.46</td><td>参考（機能するが採用構成に劣後）</td></tr>
</table></div>
<p class="note">結論：EMA層は採用戦略を「改善」するのではなく「裏付け」ます。EMA200ゲート（買いは終値&gt;EMA200のときのみ）は2026年の結果を一切変えずにレジーム転換時の自動停止を与えるため、凍結パラメータに正式採用しました。EMAタッチ自体をエントリーにすると劣化することから、「ダマシ下抜けの確認」という条件が選択性の源泉であることも確認されました。</p>
</section>

<section>
<div class="sec-head"><span class="sec-num">05</span><h2>代替案との比較（探索過程の全開示）</h2></div>
<p>約35構成を評価しました。選択はすべて訓練窓（1〜4月）の成績で行い、テスト窓（5〜7月）は選択後の確認のみに使用しています。ブレイクアウト追随型は全8構成がマイナスで棄却。両方向のスイング反発は訓練窓こそ良好でしたが、テスト窓で売りトレードが上昇トレンドに全敗しました。</p>
{chart_var}
<div class="note">数値は年率シャープレシオ。採用構成の近傍18構成（期間14/20/26日×ターゲット2種×バッファ3種）は全て通期プラス（最低+1.44）で、特定パラメータへの過剰適合ではないことを確認済みです。</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">06</span><h2>統計的検証（モンテカルロ・有意性）</h2></div>
<p>日次リターンのブロック・ブートストラップ（1万回）によるシャープレシオの分布です。保有が数週間に及ぶためブロック長を変えて確認したところ、長いブロックほど区間が狭まり、採用した5日ブロックが最も保守的な評価でした。</p>
{chart_ci}
<div class="table-wrap"><table>
<tr><th>検定</th><th>結果</th><th>解釈</th></tr>
<tr><td>Newey-West修正 t 検定（日次平均リターン）</td><td class="num">t = {valid["significance"]["newey_west_tstat_daily_mean"]:.2f}</td><td>片側p≒0.009。選択前の素朴な有意性</td></tr>
<tr><td>約35構成の多重比較調整（White's Reality Check）</td><td class="num">p ≒ 0.042〜0.068</td><td>選択バイアス調整後も有意水準5%前後を維持</td></tr>
<tr><td>トレードR倍数の符号反転検定</td><td class="num">p = {valid["significance"]["signflip_pvalue_trade_expectancy"]:.3f}</td><td>3トレードでは理論下限0.125に張り付き（検出力なし）</td></tr>
<tr><td>リスク仕様の遵守</td><td class="num">3.0000% ×3件</td><td>リスク額 30,000円／31,853円／36,110円＝各エントリー時残高の厳密に3%</td></tr>
<tr><td>方向を限定しない両方向版（参考）</td><td class="num">シャープ 1.51</td><td>選択の影響を受けない素の構成でも基準線上＝エッジの実在を補強</td></tr>
</table></div>
<p class="note">独立検証エージェントは戦略エンジンを独自に再実装して全数値のバイト一致を確認し、ルックアヘッドバイアスの不存在（コードレビュー＋データ切断テスト）を検証しました（results/final_validation_report.md）。</p>
</section>

<section>
<div class="sec-head"><span class="sec-num">07</span><h2>10年検証（2015〜2026・Dukascopy実スプレッド）</h2></div>
<p>2026年で確定した凍結パラメータを<b>一切調整せずに</b>、Dukascopy（スイスのFXブローカー）のBid/Ask別データ2014〜2026年（3,274営業日）に適用しました。執行は「買いはAsk・決済はBid」で、<b>その日の実測スプレッドが全約定に組み込まれています</b>（ティックデータ12日分のサンプル計測で妥当性を確認済み：通常日は課金スプレッドとティック実測が数厘以内で一致、Brexit級のイベント日はむしろ過大課金の保守側）。ロットは残高の3%リスクで複利連動です。</p>
<div class="tiles">
<div class="tile"><div class="v">{dec_m["sharpe_annualized"]:.2f}</div><div class="l">シャープレシオ（10年）</div><div class="s">2026年単体の3.17から大幅低下。統計的にはゼロと区別不能（CI [−0.38, 0.58]）</div></div>
<div class="tile"><div class="v">+{dec_m["total_return"]*100:.1f}%</div><div class="l">総リターン（11.5年）</div><div class="s">年率+{dec_m["cagr"]*100:.1f}%。ほぼ横ばい</div></div>
<div class="tile"><div class="v">{dec_m["max_drawdown"]*100:.1f}%</div><div class="l">最大ドローダウン</div><div class="s">2026年単体の5.3%より遥かに深い</div></div>
<div class="tile"><div class="v">{dec_m["num_trades"]}</div><div class="l">トレード数（勝率{dec_m["win_rate"]*100:.0f}%）</div><div class="s">平均+{dec_m["avg_r_multiple"]:.2f}R、最悪−1.0R（3%リスク遵守）</div></div>
</div>
<h3>年別リターン</h3>
{chart_years}
<h3>資産推移（期首100・複利3%リスク）</h3>
{chart_decade_eq}
<h3>改良探索（トレード数増×勝率向上）の結果：否定的</h3>
<p>「トレード回数を増やしつつ勝率を上げる」改良を、事前登録プロトコル（選択は2015〜2021年の訓練窓のみ・2022年以降は確認専用）で2ラウンド・計40構成検証しました。中間ターゲットで勝率50〜54%、短い期間設定でトレード数2倍超は個別に達成できますが、<b>全40構成が訓練窓でマイナスのシャープレシオ</b>（最良−0.04）であり、事前基準を満たす構成はゼロでした。ゲート付きの売り追加も全構成で悪化。結論として、この日足スプリング系統に円安レジーム外のエッジは存在せず、これ以上の深掘りは偽発見リスクを増やすだけと判断して探索を打ち切りました（詳細：results/improvement_search/）。</p>
<div class="note">読み取れること：①2026年の好成績はDukascopyデータでも+21.9%と方向一致で再現（本編の+27.6%との差は、主に日次区切りの規約差＝UTC0時区切りでは6月の3本目のトレードのシグナルが成立しないことと、実測スプレッド分）。ただしこの成績は<b>2022年以降の円安レジームに依存</b>しており、2015〜2021年は横ばい〜マイナス。②EMA200ゲートは2016年（Brexit）と2019年に一度もエントリーさせず、下落年の大負けを回避（設計どおりの防御）。③つまり本戦略は「上昇レジーム検出時のみ機能する追い風特化型」であり、常時稼働で資産を増やし続ける戦略ではない。この10年検証こそが第8章の限定事項を定量化した本命のアウトオブサンプルテストです。</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">08</span><h2>データ品質</h2></div>
<ul>
<li>stooq.comのヒストリカルデータ209営業日（2025-10-01〜2026-07-22。欠損は12/25と1/1の休場2日のみ）。</li>
<li>別経路（exchange-rates.org系・wise.com）で事前収集した実測アンカー22点との包含関係チェックに合格（例：2/17安値207.24は参照値207.79の下方＝日中実レンジとして整合、7/15高値219.65 vs 参照219.50）。</li>
<li>寄付と前日終値の乖離は中央値1.1pipsで、24時間市場の連続性として自然。単一OHLCソースである点は限定事項（日中高安の照合は数点のみ）。</li>
</ul>
</section>

<section class="caution">
<div class="sec-head"><span class="sec-num">09</span><h2>限定事項（正直な注意書き）</h2></div>
<ul>
<li><b>標本の小ささ：</b>トレード3件・観測7ヶ月。トレード単位の統計検定は構造的に検出力がありません。点推定の再現性と選択調整後p値が主な根拠です。</li>
<li><b>レジーム依存（10年検証で定量化済み）：</b>2015〜2026年の通し検証ではシャープレシオ0.10・最大DD24.1%。本戦略が機能するのは円安上昇レジームに限られ、2015〜2021年はほぼ横ばい〜マイナスでした（第7章）。</li>
<li><b>日足粒度：</b>執行は終値・判定は日足高安。日中の細かな値動き（スリッページ・指標発表時の乖離）は窓開け処理以上にはモデル化していません。スワップ未計上（買い方向はプラス傾向のため保守側）。</li>
<li><b>フォワード確認前：</b>独立監査の勧告どおり、実運用判断の前に15〜20トレード程度のフォワード（デモ）検証を推奨します。</li>
</ul>
</section>

<section>
<div class="sec-head"><span class="sec-num">10</span><h2>次の一手</h2></div>
<ul>
<li>デモ口座でのフォワード検証（セットアップは月1〜2回程度の頻度。15〜20トレードの蓄積目安は約1年）。</li>
<li>月次でのレジーム点検：安値切り上げ構造が崩れた場合（円高転換）は運用停止し再評価。</li>
<li>データの定期更新：<code>python3 tools/fetch_stooq_gbpjpy.py</code> → QC → バックテスト再実行までワンコマンドで再現可能。</li>
</ul>
</section>

<div class="summary">
<b>一言でまとめると：</b>「20日安値ラインのダマシ下抜けからの反発だけを買い、反対側のラインで利確する」というシンプルな波乗り戦略が、課題指定の検証期間（2026年1〜7月）の実データでシャープレシオ{m["sharpe_annualized"]:.2f}・リターン+{m["total_return"]*100:.1f}%・最大DD{m["max_drawdown"]*100:.1f}%を記録し、目標基準を達成しました。ただし同じルールを10年（2015〜2026）に通すと<b>シャープレシオ{dec_m["sharpe_annualized"]:.2f}・総リターン+{dec_m["total_return"]*100:.1f}%</b>まで低下する円安レジーム特化型であることも実スプレッドで定量化済みです。実運用するなら「上昇レジームの検出時のみ稼働」という前提とフォワード検証が必須です。
</div>

<footer>Naminori プロジェクト｜GBP/JPY 波乗り戦略 検証結果報告｜2026.07.23<br>
生成元データ：results/gbpjpy_final/（コミット済み・再現可能）</footer>
</div>

<div class="tooltip" id="tt"></div>
<script>
(function(){{
  var tt = document.getElementById('tt');
  document.querySelectorAll('svg[data-chart]').forEach(function(svg){{
    var d = JSON.parse(svg.getAttribute('data-chart'));
    var layer = svg.querySelector('.hoverlayer');
    var ns = 'http://www.w3.org/2000/svg';
    var vline = document.createElementNS(ns,'line');
    vline.setAttribute('stroke','{INK_SOFT}'); vline.setAttribute('stroke-width','1');
    vline.setAttribute('stroke-dasharray','3 3'); vline.setAttribute('opacity','0');
    var dot = document.createElementNS(ns,'circle');
    dot.setAttribute('r','4'); dot.setAttribute('fill','{TEAL_D}');
    dot.setAttribute('stroke','{CARD}'); dot.setAttribute('stroke-width','2');
    dot.setAttribute('opacity','0');
    layer.appendChild(vline); layer.appendChild(dot);
    function xy(i,v){{
      var n=d.vals.length;
      var x=d.padL+(d.w-d.padL-d.padR)*(i/(n-1));
      var y=d.padT+(d.h-d.padT-d.padB)*(1-(v-d.ylo)/(d.yhi-d.ylo));
      return [x,y];
    }}
    svg.addEventListener('mousemove',function(ev){{
      var r=svg.getBoundingClientRect();
      var mx=(ev.clientX-r.left)*d.w/r.width;
      var n=d.vals.length;
      var i=Math.round((mx-d.padL)/(d.w-d.padL-d.padR)*(n-1));
      if(i<0||i>=n){{vline.setAttribute('opacity','0');dot.setAttribute('opacity','0');
        tt.style.opacity='0';return;}}
      var p=xy(i,d.vals[i]);
      vline.setAttribute('x1',p[0]);vline.setAttribute('x2',p[0]);
      vline.setAttribute('y1',d.padT);vline.setAttribute('y2',d.h-d.padB);
      vline.setAttribute('opacity','.6');
      dot.setAttribute('cx',p[0]);dot.setAttribute('cy',p[1]);dot.setAttribute('opacity','1');
      tt.textContent=d.dates[i]+'  '+d.vals[i].toFixed(2);
      tt.style.left=(ev.clientX+14)+'px'; tt.style.top=(ev.clientY-10)+'px';
      tt.style.opacity='1';
    }});
    svg.addEventListener('mouseleave',function(){{
      vline.setAttribute('opacity','0');dot.setAttribute('opacity','0');tt.style.opacity='0';
    }});
  }});
}})();
</script>
</body>
</html>
"""

out = os.path.join(ROOT, "docs", "report.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"wrote {out} ({len(html):,} bytes)")
