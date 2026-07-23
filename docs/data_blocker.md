# データ取得ブロッカーの記録（2026-07-23時点）

## 結論

**2026年1月〜7月のGBP/JPY価格系列（バックテストの前提データ）は、このサンドボックス内では取得不能だった。** 以下は試行した全チャネルとその証拠。パフォーマンス検証はデータ供給後に `README.md` の手順で即実行できる。

## 試行と結果

| チャネル | 結果 | 証拠 |
|---|---|---|
| ブログ直接閲覧 (ameblo.jp) | ❌ プロキシがCONNECT 403で拒否 | プロキシstatusの relay failure ログに `ameblo.jp:443 connect_rejected` |
| 市場データAPI（Yahoo/Stooq/Dukascopy/exchangerate.host/er-api/TwelveData/AlphaVantage/Polygon/FMP/OANDA/TraderMade） | ❌ 全てCONNECT 403 | curl一括テストで全ホスト `HTTP 000 (CONNECT tunnel failed, response 403)` |
| 公的機関（ECB/BOJ/FRED/BoE/investing/Yahoo Japan） | ❌ 同上 | 同上 |
| パッケージレジストリ経由のデータ (pypi.org / registry.npmjs.org) | ❌ ゲートウェイの許可リスト外 | レスポンスボディ `Host not in allowlist: registry.npmjs.org` (HTTP 403) |
| WebSearch（Anthropic経由、唯一の外部チャネル） | ⚠️ 部分成功→予算枯渇 | 収集エージェント7体で日付別ページを145日分照会したが、ダイジェストに日付帰属の数値が含まれたのは17点のみ。途中でセッション上限（200回）に到達し `web search budget (200 of 200)` の拒否応答 |
| ユーザーのNotion「📊 市場データ」DB | ⚠️ USDJPYのみ | 実データ138行（2026-03-07〜07-22）を取得しCSV化。GBP系レートは無くGBPJPYへの換算不可 |
| ユーザーの他リポジトリ (fx-1min-scalping-strategy 等) | ⛔ 未調査 | セッションのGitHubスコープは Nyami00/Naminori のみ。リポジトリ追加はユーザーの明示指示が必要な仕様 |

到達可能だった外部ホストは `github.com` / `api.github.com` のみ（および Anthropic API 経由のWebSearch）。

## 収集できた実データ

- `data/gbpjpy_anchors_2026.json` — GBP/JPYの実測17点＋年間集計（出典付き）。QC用アンカーとして使用。
- `data/notion_usdjpy_daily_2026.csv` — ユーザー自身のNotion DBからのUSD/JPY日次終値138行（実データ）。

## 解除方法（いずれか1つで完了まで自走可能）

1. **推奨：環境のネットワーク許可リストにデータホストを追加**（Claude Code on the Web の環境設定 → ネットワークポリシー）。候補: `stooq.com`（無料・認証不要のCSV、日足/時間足）、または `query1.finance.yahoo.com`。追加後にセッションを再開して「データ取得からやり直して」と指示。
2. **GBP/JPY日次OHLC CSVをリポジトリに置く**：`data/gbpjpy_daily_2026.csv`（ヘッダ `date,open,high,low,close`、期間はウォームアップ用に2025-10-01頃〜2026-07-22推奨）。配置後 `python3 src/data_qc.py --data data/gbpjpy_daily_2026.csv` でアンカー照合→バックテスト実行。
3. **WebSearch予算の引き上げ**：環境変数 `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` を新セッションで引き上げ（145営業日×2クエリ＝目安400以上）。精度は落ちる（日次H/L中心、終値欠落あり）ためオプション1・2を推奨。
4. （補助）`Nyami00/fx-1min-scalping-strategy` や `Nyami00/investment-agent` に価格データが含まれる場合、「add Nyami00/fx-1min-scalping-strategy」とセッションに指示すれば内容を確認できる。
