# Naminori — GBP/JPY 波乗り型トレンドフォロー戦略

波乗りあっき〜氏（ブログ「ポンド円 波乗り日記」）の手法をベースに体系化した、GBP/JPY日足のトレンドフォロー戦略と、そのバックテスト・統計検証パイプライン。**依存ライブラリなし（Python 3 標準ライブラリのみ）。**

## 現在のステータス（2026-07-23）

| 項目 | 状態 |
|---|---|
| 戦略ルールの体系化（ブログ手法→機械判定ルール） | ✅ 完了（docs/methodology.md） |
| バックテストエンジン＋単体テスト28項目 | ✅ 完了・全テスト通過 |
| 統計検証（モンテカルロ・有意性検定）パイプライン | ✅ 完了・独立エージェント監査済み |
| 実データでのパイプライン実証（USD/JPY参照ラン） | ✅ 実行済み（結果はマイナス。対象外通貨・参考値） |
| **GBP/JPY 2026年1〜7月の本番バックテスト** | ❌ **未実施（データ入手不能ブロッカー）** |
| 目標基準（シャープレシオ≥1.5）の判定 | ⏸ **未検証** — データ供給後に自動判定可能 |

このサンドボックスのネットワーク許可リストが全ての市場データ源を遮断しており（詳細と証拠: docs/data_blocker.md）、GBP/JPYの価格系列が入手できなかった。**性能数値を捏造せず、検証可能な成果物のみを提出している。**

## 戦略概要

- **波の検出（N波動）**: 終値が過去20日終値最高値を上抜けたら新しい上昇波とみなす（下降は対称）
- **流れのフィルタ**: EMA50の方向と一致する場合のみエントリー
- **損切り**: エントリー − 2×ATR(14)（直近スイングの代理）。**1トレードのリスクは口座残高の3%固定**（数量=リスク額÷ストップ幅）
- **利伸ばし**: シャンデリア・トレイリング（最高終値 − 3×ATR、切り上げのみ）。波が続く限り保有
- **ドテン**: 保有中に逆方向ブレイクが出たら決済・反転
- **コスト**: スプレッド往復3pips計上。執行は終値、ストップは翌日から高安値で判定（ルックアヘッドなし）

## 実行方法

```bash
# 1) エンジンの単体テスト
python3 tests/test_strategy.py

# 2) データQC（実データCSVを data/gbpjpy_daily_2026.csv に置いた後）
python3 src/data_qc.py --data data/gbpjpy_daily_2026.csv

# 3) ウォークフォワード探索（1-4月で選択、5-7月で検証）
python3 src/grid_search.py --data data/gbpjpy_daily_2026.csv \
    --train-end 2026-04-30 --eval-start 2026-01-01

# 4) 本番バックテスト
python3 src/backtest.py --data data/gbpjpy_daily_2026.csv --eval-start 2026-01-01

# 5) 統計検証（モンテカルロ＋有意性検定）
python3 src/validate.py --results results --sharpe-target 1.5 --risk-per-trade 0.03

# （デモ）合成データでのパイプライン一気通貫（性能主張ではない）
python3 tools/make_synthetic_demo.py && \
python3 src/backtest.py --data data/SYNTHETIC_demo_gbpjpy.csv --out results/synthetic_demo --eval-start 2026-01-01 && \
python3 src/validate.py --results results/synthetic_demo
```

## リポジトリ構成

```
src/strategy.py      戦略＋バックテストエンジン（指標・執行・サイジング・指標計算）
src/backtest.py      実行ランナー（summary.json / trades.csv / equity.csv を出力）
src/validate.py      統計検証（ブロックブートストラップMC、NW t検定、符号反転検定、DD分布、リスク仕様チェック）
src/data_qc.py       データ品質検査（構造・連続性・実測アンカー照合）
src/grid_search.py   小規模ウォークフォワード探索（過剰適合防止設計）
tests/               エンジン単体テスト（手計算シナリオ28項目）
tools/               合成デモ生成・USDJPY参照ラン
data/                実測アンカー17点（出典付き）／USDJPY実データ138行／合成デモ
results/             実行結果（合成デモ・USDJPY参照・独立監査レポート）
docs/                手法の体系化・データブロッカー記録
```

## データブロッカーの解除（いずれか1つ）

1. 環境のネットワーク許可リストに `stooq.com` 等のデータホストを追加（推奨）
2. `data/gbpjpy_daily_2026.csv`（date,open,high,low,close）を用意してコミット
3. 新セッションで `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` を400以上に設定
4. 価格データを含む可能性のある手元リポジトリ（例: fx-1min-scalping-strategy）のセッション追加を指示

詳細: docs/data_blocker.md
