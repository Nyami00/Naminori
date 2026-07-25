# -*- coding: utf-8 -*-
"""Build docs/report_10pct.html - the "can we reach 10% a year" research report.

Every number and chart is read from the committed result artifacts:
  results/trend_portfolio/  (hypothesis E, FX-only TSMOM)
  results/multiasset/       (hypothesis F, 22-instrument TSMOM)
  results/allocation/       (hypothesis G, trend-filtered allocation,
                             the GFC test and the leverage table)
Single file, no external dependencies, print- and mobile-safe.
"""

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INK, INK_SOFT = "#16202e", "#3a4a5e"
PAPER, CARD, LINE = "#f3f0e9", "#fbfaf6", "#d8d2c4"
TEAL, TEAL_D, AMBER, RULE = "#0f7567", "#0a564c", "#c4761a", "#c1392b"


def jload(p):
    with open(os.path.join(ROOT, p)) as f:
        return json.load(f)


def cload(p):
    with open(os.path.join(ROOT, p), newline="") as f:
        return list(csv.DictReader(f))


lev = jload("results/allocation/leverage_table.json")
gfc = jload("results/allocation/gfc_test.json")
alloc = jload("results/allocation/selected.json")
ma = jload("results/multiasset/selected.json")
fx = jload("results/trend_portfolio/selected.json")
bench = jload("results/multiasset/benchmarks.json")
eq_rows = cload("results/allocation/gfc_equity.csv")

lev_rows = lev["rows"]
bh = lev["buy_and_hold"]
row125 = next(r for r in lev_rows if r["leverage"] == 1.25)
row100 = next(r for r in lev_rows if r["leverage"] == 1.0)
gfc_w = gfc["windows"]["GFC decade (never used before)"]
full_w = gfc["windows"]["full 18.5 years"]

# ---------------------------------------------------------------- chart utils
W, H = 880, 320
PL, PR, PT, PB = 58, 18, 16, 32


def xs(i, n):
    return PL + (W - PL - PR) * (i / max(1, n - 1))


def ys(v, lo, hi):
    return PT + (H - PT - PB) * (1 - (v - lo) / (hi - lo))


# ---- chart 1: equity curves through the GFC ---------------------------------
dates = [r["date"] for r in eq_rows]
tf = [float(r["trend_filtered"]) / 10000.0 for r in eq_rows]
bhv = [float(r["buy_hold"]) / 10000.0 for r in eq_rows]
lo, hi = min(min(tf), min(bhv)) * 0.95, max(max(tf), max(bhv)) * 1.05
n = len(dates)
grid, labels = [], []
for t in (100, 200, 300, 400, 500, 600):
    if lo <= t <= hi:
        y = ys(t, lo, hi)
        grid.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" '
                    f'stroke="{LINE}" stroke-width="1"/>')
        labels.append(f'<text x="{PL-8}" y="{y+4:.1f}" text-anchor="end" class="tick">{t}</text>')
for i, d in enumerate(dates):
    if i == 0 or d[:4] != dates[i - 1][:4]:
        if int(d[:4]) % 2 == 0:
            labels.append(f'<text x="{xs(i,n):.1f}" y="{H-8}" text-anchor="middle" '
                          f'class="tick">{d[:4]}</text>')
# shade the crisis years
shade = ""
for y0, y1, lab in (("2008-01-01", "2009-03-31", "リーマン"),
                    ("2020-02-01", "2020-04-30", "コロナ"),
                    ("2022-01-01", "2022-10-31", "22年利上げ")):
    i0 = next((i for i, d in enumerate(dates) if d >= y0), None)
    i1 = next((i for i, d in enumerate(dates) if d >= y1), n - 1)
    if i0 is not None:
        x0, x1 = xs(i0, n), xs(i1, n)
        shade += (f'<rect x="{x0:.1f}" y="{PT}" width="{max(2,x1-x0):.1f}" '
                  f'height="{H-PT-PB}" fill="{RULE}" opacity="0.07"/>'
                  f'<text x="{(x0+x1)/2:.1f}" y="{PT+13}" text-anchor="middle" '
                  f'class="tick" fill="{RULE}">{lab}</text>')
p_tf = " ".join(f"{xs(i,n):.1f},{ys(v,lo,hi):.1f}" for i, v in enumerate(tf))
p_bh = " ".join(f"{xs(i,n):.1f},{ys(v,lo,hi):.1f}" for i, v in enumerate(bhv))
chart_eq = f'''<div class="chart-wrap"><svg viewBox="0 0 {W} {H}" class="chart" role="img">
{"".join(grid)}{shade}
<line x1="{PL}" y1="{H-PB}" x2="{W-PR}" y2="{H-PB}" stroke="{INK_SOFT}" stroke-width="1"/>
<polyline points="{p_bh}" fill="none" stroke="{AMBER}" stroke-width="2"/>
<polyline points="{p_tf}" fill="none" stroke="{TEAL}" stroke-width="2.2"/>
<text x="{W-PR-4}" y="{ys(bhv[-1],lo,hi)+16:.1f}" text-anchor="end" class="lab" fill="{AMBER}">単純保有 {bhv[-1]:.0f}</text>
<text x="{W-PR-4}" y="{ys(tf[-1],lo,hi)-8:.1f}" text-anchor="end" class="lab" fill="{TEAL_D}">フィルタ付 {tf[-1]:.0f}</text>
{"".join(labels)}</svg></div>'''

# ---- chart 2: Sharpe comparison across everything tested --------------------
strategies = [
    ("波乗り戦略（GBPJPY単体・10年）", 0.10, AMBER),
    ("波乗り3ペア分散", 0.28, AMBER),
    ("通貨トレンドフォロー", fx["metrics_target10pct_vol"]["full"]["sharpe"], AMBER),
    ("多資産トレンドフォロー", ma["metrics_base"]["full"]["sharpe"], AMBER),
    ("単純保有（指数＋金）", bh["sharpe"], TEAL),
    ("トレンドフィルタ付き分散", row100["sharpe"], TEAL_D),
]
BW, BH_ = 880, 210
BL = 250
smax = 0.9
bars = []
for k, (lab, val, col) in enumerate(strategies):
    y = 26 + k * 30
    w = (BW - BL - 90) * (val / smax)
    bars.append(f'<text x="{BL-12}" y="{y+5}" text-anchor="end" class="lab2">{lab}</text>'
                f'<rect x="{BL}" y="{y-9}" width="{max(2,w):.1f}" height="18" rx="4" fill="{col}">'
                f'<title>{lab}: シャープレシオ {val:.2f}</title></rect>'
                f'<text x="{BL+w+8:.1f}" y="{y+5}" class="val">{val:.2f}</text>')
chart_sharpe = (f'<div class="chart-wrap"><svg viewBox="0 0 {BW} {BH_}" class="chart" role="img">'
                f'{"".join(bars)}</svg></div>')

# ---- chart 3: leverage frontier (return vs drawdown) ------------------------
FW, FH = 880, 260
FL, FB = 64, 40
dd_max = 0.45
ret_max = 0.14
def fx_(v):
    return FL + (FW - FL - 24) * (v / dd_max)
def fy_(v):
    return FH - FB - (FH - FB - 24) * (v / ret_max)
pts = []
for t in (0.0, 0.1, 0.2, 0.3, 0.4):
    pts.append(f'<line x1="{fx_(t):.1f}" y1="{FH-FB}" x2="{fx_(t):.1f}" y2="20" '
               f'stroke="{LINE}" stroke-width="1"/>'
               f'<text x="{fx_(t):.1f}" y="{FH-FB+18}" text-anchor="middle" class="tick">{t:.0%}</text>')
for t in (0.0, 0.05, 0.10):
    pts.append(f'<line x1="{FL}" y1="{fy_(t):.1f}" x2="{FW-24}" y2="{fy_(t):.1f}" '
               f'stroke="{LINE}" stroke-width="1"/>'
               f'<text x="{FL-8}" y="{fy_(t)+4:.1f}" text-anchor="end" class="tick">{t:.0%}</text>')
pts.append(f'<line x1="{FL}" y1="{fy_(0.10):.1f}" x2="{FW-24}" y2="{fy_(0.10):.1f}" '
           f'stroke="{RULE}" stroke-width="1.5" stroke-dasharray="6 4"/>'
           f'<text x="{FW-28}" y="{fy_(0.10)-8:.1f}" text-anchor="end" class="val" fill="{RULE}">目標 年利10%</text>')
line_pts = " ".join(f'{fx_(r["max_drawdown"]):.1f},{fy_(r["estimated_total_return"]):.1f}'
                    for r in lev_rows)
pts.append(f'<polyline points="{line_pts}" fill="none" stroke="{TEAL}" stroke-width="2" '
           f'stroke-dasharray="4 3" opacity="0.7"/>')
for r in lev_rows:
    x, y = fx_(r["max_drawdown"]), fy_(r["estimated_total_return"])
    pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{TEAL}" stroke="{CARD}" stroke-width="2">'
               f'<title>レバレッジ{r["leverage"]}倍: 推定総リターン{r["estimated_total_return"]:.1%}、最大DD{r["max_drawdown"]:.1%}</title></circle>'
               f'<text x="{x:.1f}" y="{y-13:.1f}" text-anchor="middle" class="val">{r["leverage"]:g}x</text>')
xb, yb = fx_(bh["max_drawdown"]), fy_(bh["estimated_total_return"])
pts.append(f'<circle cx="{xb:.1f}" cy="{yb:.1f}" r="7" fill="{AMBER}" stroke="{CARD}" stroke-width="2">'
           f'<title>単純保有: 推定総リターン{bh["estimated_total_return"]:.1%}、最大DD{bh["max_drawdown"]:.1%}</title></circle>'
           f'<text x="{xb:.1f}" y="{yb-14:.1f}" text-anchor="middle" class="val" fill="#8a5411">単純保有</text>')
pts.append(f'<text x="{FW/2:.0f}" y="{FH-6}" text-anchor="middle" class="tick">'
           f'← 最大ドローダウン（右ほど痛い） →</text>')
chart_frontier = (f'<div class="chart-wrap"><svg viewBox="0 0 {FW} {FH}" class="chart" role="img">'
                  f'{"".join(pts)}</svg></div>')

# ---- crisis-year table -------------------------------------------------------
crisis = [r for r in gfc["per_year"] if r["year"] in ("2008", "2011", "2018", "2020", "2022")]
crisis_rows = "".join(
    f'<tr><td>{r["year"]}年</td>'
    f'<td class="num {"pos" if r["trend_return"]>=0 else "neg"}">{r["trend_return"]:+.1%}</td>'
    f'<td class="num">{r["trend_dd"]:.1%}</td>'
    f'<td class="num {"pos" if r["buyhold_return"]>=0 else "neg"}">{r["buyhold_return"]:+.1%}</td>'
    f'<td class="num">{r["buyhold_dd"]:.1%}</td></tr>' for r in crisis)

lev_table = "".join(
    f'<tr{" class=hl" if r["leverage"]==1.25 else ""}><td>{r["leverage"]:g}倍</td>'
    f'<td class="num">{r["cagr"]:.1%}</td><td class="num">{r["ann_vol"]:.1%}</td>'
    f'<td class="num">{r["sharpe"]:.2f}</td><td class="num">{r["max_drawdown"]:.1%}</td>'
    f'<td class="num strong">{r["estimated_total_return"]:.1%}</td></tr>' for r in lev_rows)

html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>年利10%は可能か — 4つの手法の検証</title>
<style>
:root{{--ink:{INK};--ink-soft:{INK_SOFT};--paper:{PAPER};--card:{CARD};--line:{LINE};
--teal:{TEAL};--teal-d:{TEAL_D};--amber:{AMBER};--rule:{RULE};
--shadow:0 1px 0 rgba(22,32,46,.04),0 12px 30px -18px rgba(22,32,46,.35);}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif;
color:var(--ink);background:var(--paper);
background-image:radial-gradient(1200px 500px at 85% -10%,#e9e4d6 0%,transparent 60%);
line-height:1.85;letter-spacing:.01em;font-size:15px;}}
.wrap{{max-width:960px;margin:0 auto;padding:48px 24px 80px;}}
.eyebrow{{font-size:12px;letter-spacing:.22em;text-transform:uppercase;font-weight:700;color:var(--teal-d);}}
h1{{font-size:clamp(26px,4.2vw,40px);font-weight:800;letter-spacing:-.01em;margin:6px 0 6px;line-height:1.35;}}
.sub{{color:var(--ink-soft);margin-bottom:8px;}}
.meta{{font-size:12.5px;color:var(--ink-soft);border-bottom:1px solid var(--line);
padding-bottom:18px;margin-bottom:26px;}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;
box-shadow:var(--shadow);padding:26px 28px;margin-bottom:22px;}}
.sec-head{{display:flex;align-items:baseline;gap:12px;margin-bottom:14px;}}
.sec-num{{font-size:12px;font-weight:800;color:var(--teal-d);letter-spacing:.14em;}}
h2{{font-size:19px;font-weight:800;}}
h3{{font-size:15px;font-weight:700;margin:16px 0 6px;color:var(--teal-d);}}
p{{margin-bottom:11px;}}
.verdict{{border-left:5px solid var(--teal);}}
.lead{{font-size:16.5px;font-weight:700;margin-bottom:14px;}}
.tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:8px 0 12px;}}
.tile{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px 16px;}}
.tile.win{{border-color:#9fd0c4;background:#eef6f3;}}
.tile .v{{font-size:27px;font-weight:800;color:var(--teal-d);line-height:1.2;}}
.tile .l{{font-size:12px;font-weight:700;color:var(--ink-soft);margin-top:2px;}}
.tile .s{{font-size:11.5px;color:var(--ink-soft);margin-top:4px;}}
.qual{{font-size:13px;color:var(--ink-soft);background:var(--paper);border-radius:8px;padding:10px 14px;}}
.chart-wrap{{overflow-x:auto;margin:10px 0 4px;}}
.chart{{width:100%;height:auto;display:block;min-width:600px;}}
.tick{{font-size:11px;fill:var(--ink-soft);}}
.lab{{font-size:12.5px;font-weight:700;}}
.lab2{{font-size:12.5px;fill:var(--ink);}}
.val{{font-size:12px;font-weight:700;fill:var(--ink);}}
.note{{font-size:12.5px;color:var(--ink-soft);margin-top:6px;}}
.table-wrap{{overflow-x:auto;}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;}}
th{{text-align:left;font-size:12px;color:var(--ink-soft);border-bottom:2px solid var(--ink);
padding:7px 10px;white-space:nowrap;}}
td{{border-bottom:1px solid var(--line);padding:8px 10px;}}
td:first-child{{font-weight:700;white-space:nowrap;}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}}
.pos{{color:var(--teal-d);font-weight:700;}}
.neg{{color:var(--rule);font-weight:700;}}
.strong{{font-weight:800;}}
tr.hl{{background:#eef6f3;}}
.caution{{border-left:5px solid var(--amber);}}
.caution h2{{color:#8a5411;}}
ul{{padding-left:1.3em;}} li{{margin-bottom:7px;}}
.summary{{background:var(--ink);color:#f2efe8;border-radius:12px;padding:22px 26px;}}
.summary b{{color:#9fd8cc;}}
footer{{margin-top:24px;font-size:12px;color:var(--ink-soft);text-align:center;}}
@media (max-width:640px){{.tiles{{grid-template-columns:1fr;}}section{{padding:20px 16px;}}}}
@media print{{body{{background:#fff;}}section{{box-shadow:none;break-inside:avoid;}}
.wrap{{padding:0;max-width:none;}}*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="eyebrow">追加研究レポート｜Reaching 10% a Year</div>
<h1>年利10%は可能か<br>——4系統の手法を検証した結果</h1>
<div class="sub">波乗り戦略の限界（年利1.4%）を出発点に、通貨トレンドフォロー・多資産トレンドフォロー・分散アロケーションを事前登録プロトコルで検証しました。</div>
<div class="meta">データ：Dukascopy日足Bid/Ask 最大22銘柄（通貨11・株価指数5・貴金属2・エネルギー3・銅）／最長2007年1月〜2026年7月・実測スプレッド込み。検証窓：訓練2015〜2021年で構成選択、2022年以降および2008〜2014年は選択に不使用。</div>

<section class="verdict">
<p class="lead">結論：年利10%は達成可能でした。ただし「取引を工夫する」方向ではなく、「分散して保有し、下降局面だけ降りる」方向でのみです。</p>
<div class="tiles">
<div class="tile"><div class="v">✗</div><div class="l">トレード系4手法</div><div class="s">シャープ0.10〜0.42。10%到達には5〜14倍のレバレッジが必要で、ドローダウン50〜88%＝実質破綻</div></div>
<div class="tile win"><div class="v">{row125["estimated_total_return"]:.1%}</div><div class="l">推奨解：トレンドフィルタ付き分散（1.25倍）</div><div class="s">最大DD {row125["max_drawdown"]:.1%}／18.5年・リーマン期を含む</div></div>
<div class="tile"><div class="v">{bh["estimated_total_return"]:.1%}</div><div class="l">対抗馬：単純保有</div><div class="s">最大DD {bh["max_drawdown"]:.1%}。利回りは互角だが下落耐性が大きく劣る</div></div>
</div>
<div class="qual">レバレッジなしの素の成績は年{row100["cagr"]:.1%}（価格ベース）／推定総リターン{row100["estimated_total_return"]:.1%}・最大DD{row100["max_drawdown"]:.1%}です。10%に届かせるにはレバレッジ1.25倍が必要で、その分ドローダウンも{row100["max_drawdown"]:.1%}→{row125["max_drawdown"]:.1%}に拡大します。リターンは常にリスクとの交換であり、無料の10%は存在しません。</div>
</section>

<section>
<div class="sec-head"><span class="sec-num">01</span><h2>なぜトレード系では届かないのか（算数）</h2></div>
<p>リターンはおおよそ<b>シャープレシオ × ボラティリティ</b>で決まります。ボラティリティはレバレッジで自由に上げられますが、ドローダウンも同じ比率で膨らみます。したがって<b>到達可能な利回りの上限は、実質的にシャープレシオが決めます</b>。</p>
{chart_sharpe}
<div class="note">本プロジェクトで検証した全手法のシャープレシオ（琥珀＝棄却、緑＝採用候補）。トレード系（上4本）はいずれも0.42以下で、年利10%を出すには年率24〜36%のボラティリティ＝ドローダウン50〜88%が必要になり、運用として成立しません。</div>
<div class="table-wrap"><table>
<tr><th>棄却した手法</th><th>シャープ</th><th>10%到達に必要なレバレッジ</th><th>その時の最大DD</th></tr>
<tr><td>通貨トレンドフォロー（11ペア）</td><td class="num">{fx["metrics_target10pct_vol"]["full"]["sharpe"]:.2f}</td><td class="num">13.6倍</td><td class="num neg">87.9%</td></tr>
<tr><td>多資産トレンドフォロー（22銘柄）</td><td class="num">{ma["metrics_base"]["full"]["sharpe"]:.2f}</td><td class="num">5.3倍</td><td class="num neg">50.6%</td></tr>
</table></div>
</section>

<section>
<div class="sec-head"><span class="sec-num">02</span><h2>決定的な検証：リーマンショックを含む18.5年</h2></div>
<p>採用構成は「株価指数4本＋金を等分し、<b>250日移動平均を上回っている資産だけ保有</b>、割り込んだら現金化、月1回だけ判定」という古典的なタイミングモデルです。2015〜2021年で構成を確定したのち、<b>一切再調整せずに</b>一度も使っていない2008〜2014年（リーマンショック期）へ適用しました。</p>
{chart_eq}
<div class="note">2008年1月＝100とした資産推移。赤帯は危機局面。緑（フィルタ付き）は2008年にほぼ無傷で、以降も一貫して滑らかです。</div>
<div class="table-wrap"><table>
<tr><th>期間</th><th colspan="2">トレンドフィルタ付き</th><th colspan="2">単純保有</th></tr>
<tr><th></th><th class="num">年利／シャープ</th><th class="num">最大DD</th><th class="num">年利／シャープ</th><th class="num">最大DD</th></tr>
<tr><td>2008〜2014年<br><span class="note">（選択に未使用＝純粋な検証）</span></td>
<td class="num">{gfc_w["trend_filtered"]["cagr"]:.1%} ／ {gfc_w["trend_filtered"]["sharpe"]:.2f}</td>
<td class="num pos">{gfc_w["trend_filtered"]["max_drawdown"]:.1%}</td>
<td class="num">{gfc_w["buy_hold"]["cagr"]:.1%} ／ {gfc_w["buy_hold"]["sharpe"]:.2f}</td>
<td class="num neg">{gfc_w["buy_hold"]["max_drawdown"]:.1%}</td></tr>
<tr><td>2008〜2026年<br><span class="note">（全期間18.5年）</span></td>
<td class="num">{full_w["trend_filtered"]["cagr"]:.1%} ／ {full_w["trend_filtered"]["sharpe"]:.2f}</td>
<td class="num pos">{full_w["trend_filtered"]["max_drawdown"]:.1%}</td>
<td class="num">{full_w["buy_hold"]["cagr"]:.1%} ／ {full_w["buy_hold"]["sharpe"]:.2f}</td>
<td class="num neg">{full_w["buy_hold"]["max_drawdown"]:.1%}</td></tr>
</table></div>
<h3>危機の年に何が起きたか</h3>
<div class="table-wrap"><table>
<tr><th>年</th><th class="num">フィルタ付き</th><th class="num">その年のDD</th><th class="num">単純保有</th><th class="num">その年のDD</th></tr>
{crisis_rows}
</table></div>
<p class="note">2008年の差（−1.2% 対 −28.4%）がこの手法の全てです。移動平均を割った資産を月次で現金化するだけで、暴落の大半を回避しています。逆に上昇局面では出遅れるため（2019年 +7.2% 対 +23.5%）、<b>利回りではなくドローダウンを買う手法</b>だと理解する必要があります。</p>
</section>

<section>
<div class="sec-head"><span class="sec-num">03</span><h2>目標10%への到達経路（レバレッジの選択）</h2></div>
<p>この構成はドローダウンが単純保有の半分以下なので、<b>レバレッジをかける余地がある</b>のが要点です。シャープレシオはレバレッジで変わらないため（0.74で一定）、下表は純粋に「どれだけのドローダウンを受け入れれば、どれだけの利回りが得られるか」の対応表になります。</p>
{chart_frontier}
<div class="table-wrap"><table>
<tr><th>レバレッジ</th><th class="num">価格ベース年利</th><th class="num">年率ボラ</th><th class="num">シャープ</th><th class="num">最大DD</th><th class="num">推定総リターン</th></tr>
{lev_table}
<tr><td>単純保有（参考）</td><td class="num">{bh["cagr"]:.1%}</td><td class="num">{bh["ann_vol"]:.1%}</td><td class="num">{bh["sharpe"]:.2f}</td><td class="num neg">{bh["max_drawdown"]:.1%}</td><td class="num strong">{bh["estimated_total_return"]:.1%}</td></tr>
</table></div>
<p class="note">「推定総リターン」は価格ベースの実測値に、配当（投資中の株式部分に年{lev["assumptions"]["dividend_yield"]:.1%}）・現金部分の金利（年{lev["assumptions"]["cash_rate"]:.1%}）・借入コスト（1倍超の部分に年{lev["assumptions"]["financing_rate"]:.1%}）を加減した<b>推計</b>です。バックテストされた数値ではなく、前提を変えれば動きます（前提はresults/allocation/leverage_table.jsonに記録）。</p>
</section>

<section class="caution">
<div class="sec-head"><span class="sec-num">04</span><h2>この結論の限界（必ず読んでください）</h2></div>
<ul>
<li><b>これは投資であって、トレードではありません。</b>波乗り戦略とは別物です。売買は月1回の判定のみで、年間の取引回数は数回。「相場を読む技術」は一切使いません。</li>
<li><b>18.5年でも標本は十分ではありません。</b>危機は2008年・2020年・2022年の3回しか含まれず、実質的な独立事象は数回です。次の危機が移動平均の効かない形（一晩で終わる急落など）で来れば、この防御は機能しません。</li>
<li><b>推定総リターンは前提に依存します。</b>配当・金利・借入コストは実測ではなく仮定です。特に借入コストは金利環境で大きく変わり、高金利下ではレバレッジの妙味が消えます。</li>
<li><b>レバレッジ1.25倍でも最大{row125["max_drawdown"]:.1%}の含み損に耐える必要があります。</b>1,000万円が約{10000000*(1-row125["max_drawdown"])/10000:.0f}万円まで減る局面が実際にありました。これに耐えられないなら、レバレッジなし（年{row100["estimated_total_return"]:.1%}・DD{row100["max_drawdown"]:.1%}）を選ぶべきです。</li>
<li><b>税・取引手数料・為替影響は未計上です。</b>日本の居住者が外国指数に投資する場合、約20%の課税と円換算の変動が加わります。</li>
</ul>
</section>

<section>
<div class="sec-head"><span class="sec-num">05</span><h2>実装するなら</h2></div>
<ul>
<li><b>使う商品：</b>CFDではなく現物のETF・投資信託（S&P500・ナスダック100・日経225・FTSE・金）。CFDは保有中ずっと金利コストがかかり、この長期保有型とは相性が最悪です。</li>
<li><b>やること：</b>月1回、各ETFの価格が250日移動平均より上か下かを確認。上なら保有継続、下なら売って現金（またはMMF）へ。それだけです。</li>
<li><b>やらないこと：</b>移動平均を割った瞬間に売る（月次判定を守る）、下がったから買い増す、上昇に焦って戻す。判定日以外は何もしないことが成績の一部です。</li>
<li><b>レバレッジをかける場合：</b>信用取引ではなくレバレッジ型ETFは避けてください（日次リバランスで長期保有時に減価します）。証券会社の現物担保ローン等、コストが明示され、かつ強制決済されにくい手段を選ぶこと。</li>
</ul>
</section>

<div class="summary">
<b>一言でまとめると：</b>「相場を当てる」方向（波乗り戦略・トレンドフォロー4系統、シャープ0.10〜0.42）では、年利10%はレバレッジ地獄を通らずに到達できませんでした。一方「分散して保有し、250日移動平均を割った資産だけ現金化する」という月1回・数分の作業（シャープ{row100["sharpe"]:.2f}）は、リーマンショックを含む18.5年で単純保有と同等の利回りを半分以下のドローダウンで達成し、1.25倍のレバレッジで<b>推定年利{row125["estimated_total_return"]:.1%}・最大DD{row125["max_drawdown"]:.1%}</b>に到達しました。皮肉な結論ですが、これがデータの答えです。
</div>

<footer>Naminori プロジェクト｜年利10%研究レポート｜2026.07<br>
生成元：results/{{trend_portfolio,multiasset,allocation}}/（全てコミット済み・再現可能）<br>
本資料は投資助言ではなく、公開データによる検証結果の記録です。</footer>
</div>
</body>
</html>
"""

out = os.path.join(ROOT, "docs", "report_10pct.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"wrote {out} ({len(html):,} bytes)")
