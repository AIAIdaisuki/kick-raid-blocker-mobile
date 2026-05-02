# Kick Raid Blocker Mobile

Kick.com のレイド（ホスト）による自動リダイレクトをブロックする Userscript です。
**iPhone / Android / PC のどれでも動きます**。アプリストアの審査も Apple Developer Program ($99/年) も Chrome Web Store の登録も不要です。

> 本スクリプトは ANON_LAB 氏の Chrome 拡張「Kick Raid Blocker」と同じコンセプトを、モバイル対応のためにゼロからクリーンルーム実装したものです（ソースコードは参照していません）。

## できること

- レイド/ホスト時の自動リダイレクトを検知してブロック
- 3 つのモード
  - **すべてブロック**（既定）
  - **許可リスト**: ここに入れた配信者のレイドだけ通す
  - **ブロックリスト**: ここに入れた配信者のレイドだけブロック
- ブロック時にトースト通知
- ブロック履歴（直近 50 件）
- 設定はすべて **Kick.com の右下の 🛡 ボタン** から完結（拡張メニュー不要なので iPhone でも操作可）

## インストール（スマホ完結）

### iPhone (Safari)

1. App Store で **[Userscripts](https://apps.apple.com/app/userscripts/id1463298887)**（無料）をインストール
2. iOS の **設定 → Safari → 機能拡張** で **Userscripts** をオン、**すべての Web サイト** に許可
3. Safari で本リポジトリの **`kick-raid-blocker-mobile.user.js` の Raw リンク**を開く
   - 例: `https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/kick-raid-blocker-mobile.user.js`
4. 「このスクリプトをインストールしますか？」と聞かれるので **OK**
5. `https://kick.com/` を開く → 右下に 🛡 ボタンが出れば成功

### Android (Kiwi Browser または Firefox)

**Kiwi Browser を使う場合:**
1. Play Store で **Kiwi Browser** をインストール
2. Kiwi で `chrome://extensions/` を開いて、**Tampermonkey** を Chrome Web Store からインストール
3. 上の Userscript の Raw リンクを Kiwi で開く → Tampermonkey が自動で取り込みダイアログを出す → **インストール**
4. `https://kick.com/` を開いて 🛡 ボタンを確認

**Firefox を使う場合:**
1. Play Store で **Firefox** をインストール
2. メニュー → 拡張機能 → **Tampermonkey** を有効化
3. Userscript の Raw リンクを開く → インストール

### PC (Chrome / Firefox / Edge / Safari)

1. ブラウザに [Tampermonkey](https://www.tampermonkey.net/) または [Violentmonkey](https://violentmonkey.github.io/) をインストール
2. Userscript の Raw リンクを開く → インストール

## 使い方

1. `https://kick.com/<配信者>` を開く
2. 右下の 🛡 ボタンをタップ → 設定パネルが開く
3. モード・許可/ブロックリストを設定して **保存**

レイドが発生して URL が `/<別の配信者>` に切り替わろうとすると、自動的にキャンセルされます。
ブロックされると下の方にトースト通知が出ます。

## 仕組み（ざっくり）

クリーンルーム実装なので、Kick の内部 API を直接フックするのではなく、**「自分が何かタップ/スワイプしたか直近にあるか」** を基準に判定しています：

| シグナル | 判定 |
| --- | --- |
| 配信ページ A → 配信ページ B への遷移 | 候補 |
| 直近 1.5 秒以内にタップ・キー入力・スクロールがある | ユーザー操作 → **通す** |
| 直近の操作なし | プログラム遷移（= レイドの可能性大）→ **ブロック** |

防御層：

1. `history.pushState` / `replaceState`（SPA / Next.js ルーター）
2. `Location.assign` / `Location.replace`
3. `location.href = ...` セッター（可能な環境のみ）
4. 合成された `<a>` クリック（`isTrusted=false`）

つまり「Kick が `<channel>` ページから別の `<channel>` ページへ、ユーザー操作なしに切り替えようとしたら止める」が本質です。
ブラウズページ・カテゴリ・VOD 等への遷移は対象外なので、サイトの通常動作には影響しません。

## 注意点

- 配信終了後に**自分でクリック**して別配信に飛ぶのは普通に動きます。ブロックされるのは「自動」で飛ぶケースだけ
- Kick の DOM 構造が大きく変わると追従が必要になる場合があります（Issue で教えてください）
- 「許可リスト」「ブロックリスト」のキーは `kick.com/<slug>` の `<slug>` 部分（小文字）です

## セキュリティ・プライバシー

このスクリプトは以下を **行いません**（CIで毎push自動チェック）：

- 外部サーバへの通信（`fetch` / `XMLHttpRequest` / `WebSocket` 等は一切なし）
- Cookie・パスワード・支払い情報の読み書き
- 他サイトでの動作（`@match` で `kick.com` のみ）
- アナリティクス・テレメトリ・トラッキング

設定とブロック履歴はすべて **あなたの端末のローカルストレージのみ** に保存されます。
履歴は設定パネルの「履歴をクリア」でいつでも消せます。

ストレージから読んだ設定は厳格に型・正規表現バリデーション（slug は `[a-z0-9_-]{1,32}` のみ許可、リストは最大500件、ログは最大50件）されるので、ストレージが万一汚染されても安全側に倒れます。

詳細・脆弱性報告手順: [SECURITY.md](SECURITY.md) ／ 自分で確認: 約470行の1ファイルなので読み切れます → [kick-raid-blocker-mobile.user.js](kick-raid-blocker-mobile.user.js)

**特定バージョンに固定したい方**：自動更新を切って、`@updateURL` を `main` ではなく [タグ](https://github.com/AIAIdaisuki/kick-raid-blocker-mobile/releases) (`v0.2.0` 等) に差し替えると、リポジトリに何かあっても影響を受けません。

## ライセンス

MIT License — 自由に使って改変・再配布できます。

## クレジット

- 元のコンセプト・PC 版オリジナル拡張: [Kick Raid Blocker (ANON_LAB)](https://chromewebstore.google.com/detail/kick-raid-blocker/plbneahggclbbkgihoecnbajehndkpgp) / [Firefox 版](https://addons.mozilla.org/en-US/firefox/addon/kick-raid-blocker/)
- 本 Userscript（モバイル対応のクリーンルーム実装）: AIAIdaisuki

## Issue / 要望

[GitHub Issues](https://github.com/AIAIdaisuki/kick-raid-blocker-mobile/issues) までどうぞ。
