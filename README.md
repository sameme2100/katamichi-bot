# 片道GO Discord通知Bot

トヨタレンタカー公式の「片道GO!」掲載ページを定期チェックし、
前回確認時になかった案件をDiscord Webhookへ通知します。

公式ページ:
https://cp.toyota.jp/rentacar/?padid=ag270_fr_top_onewayma_m

## 一番簡単な動かし方

GitHub Actionsで5分ごとに動かす想定です。

1. このフォルダをGitHubの新しいリポジトリへアップロード
2. Discordで通知先チャンネルのWebhookを作成
3. GitHubリポジトリの Settings → Secrets and variables → Actions
4. Secrets に `DISCORD_WEBHOOK_URL` を作成してWebhook URLを入れる
5. Actions → 「片道GO監視」→ Run workflow で一度手動実行
6. 2回目以降、新しく掲載された案件だけDiscordへ通知

初回実行では現在掲載されている案件を「既知」として記録し、
大量通知を防ぐためDiscordには送りません。

## 絞り込み

GitHubの Settings → Secrets and variables → Actions → Variables から設定できます。

- `FILTER_DEPARTURE` : 出発店舗に含めたい文字
- `FILTER_ARRIVAL` : 返却先に含めたい文字
- `FILTER_KEYWORD` : 車種・条件などを含めた全項目に対する文字検索

例:
FILTER_DEPARTURE=神奈川
FILTER_ARRIVAL=静岡

## 注意

片道GOのページ構造が変更された場合、解析部分 (`parse_records`) の修正が必要になる可能性があります。

また、短い間隔でのアクセスは公式サイトに負荷をかけるため、
このサンプルでは5分間隔にしています。
