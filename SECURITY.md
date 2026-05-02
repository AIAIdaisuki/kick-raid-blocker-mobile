# Security Policy

このプロジェクトは利用者の安全とプライバシーを最優先に設計しています。
ユーザースクリプトはブラウザ内で広い権限を持ちうるため、設計・配布の両方で以下の保証を維持します。

## 設計上の保証

このスクリプトは以下を **行いません**：

- 外部サーバへの通信（`fetch` / `XMLHttpRequest` / `WebSocket` / `GM.xmlHttpRequest` 等は一切使用しない）
- Cookie・localStorage（Kick自身のもの）の読み書き
- フォーム入力の傍受・キーロギング（`keydown` はタイミングのみ記録、内容は破棄）
- 他のサイトでの動作（`@match` で `kick.com` に限定）
- 他の拡張機能や Userscript への干渉
- アナリティクス・テレメトリ・クラッシュレポートの送信

これは CI（[`.github/workflows/security-check.yml`](.github/workflows/security-check.yml)）で **すべての push に対して自動チェック** されます。
禁止された API の使用や `@match` の拡大が検出されるとビルドが失敗し、リリースされません。

## 入力バリデーション

ストレージから読み込んだ設定は `sanitizeConfig()` で型・正規表現・サイズを厳格に検査され、
不正な値は黙って既定値に置き換えられます（[`kick-raid-blocker-mobile.user.js`](kick-raid-blocker-mobile.user.js) 参照）。

- 配信者slug: `/^[a-z0-9_-]{1,32}$/` のみ許可
- リスト最大: 500件
- ログ最大: 50件
- モード: `block-all` / `allow-list` / `block-list` のいずれかのみ

## 脆弱性報告

セキュリティ上の脆弱性を発見した場合は **公開Issueを建てる前に** GitHub の
[Security Advisories](https://github.com/AIAIdaisuki/kick-raid-blocker-mobile/security/advisories/new)
からプライベートに報告してください。

報告に含めてほしい内容：

- 影響範囲（情報漏洩・任意コード実行・誤動作 等）
- 再現手順
- 影響を受けるバージョン
- 可能であれば修正案

48時間以内に一次返信、確認後できるだけ早く修正版をリリースします。

## サプライチェーンの保護

- **2要素認証**: メンテナの GitHub アカウントは 2FA を有効化
- **ブランチ保護**: `main` への直接 push 不可、強制 push 不可
- **CI**: 上記セキュリティチェックがすべての push で自動実行
- **タグ付きリリース**: 重要な変更は `vX.Y.Z` 形式のタグでリリース
- **再現性**: minify せず難読化なしの単一ファイル（約470行）で配布

## 利用者ができる追加の確認

不安な方は以下の方法で確認できます：

1. **ソースを直接読む**: 単一ファイル・約470行・コメント付き → [kick-raid-blocker-mobile.user.js](kick-raid-blocker-mobile.user.js)
2. **最新リリースのコミットハッシュを確認**: [Releases](https://github.com/AIAIdaisuki/kick-raid-blocker-mobile/releases) から取得
3. **特定のリリースに固定**: 自動更新を切り、`@updateURL` を `main` でなく `v0.2.0` 等のタグに差し替えると、メンテナに何かあっても影響を受けません
4. **`grep -E 'fetch|XMLHttpRequest|WebSocket|xmlHttpRequest|eval' kick-raid-blocker-mobile.user.js`**
   で禁止APIが含まれていないことを自分で確認できます

## バージョンサポート

最新版のみセキュリティ更新を提供します。

| Version | Supported |
| --- | --- |
| 0.2.x | :white_check_mark: |
| < 0.2 | :x: |
