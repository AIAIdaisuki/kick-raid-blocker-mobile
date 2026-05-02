# Kick 公式アプリでもレイドをブロックする

公式アプリはネイティブアプリなので Userscript が動きません。それでも **アプリのまま守りたい** 人のために、すぐ使える設定ファイルを用意しました。

## 何が起きているか

Kick のレイドは Pusher WebSocket 経由で配信されます：

- 接続先: `wss://ws-us2.pusher.com/app/<APP_ID>`（クラスタ違いで `ws-mt1` / `ws-eu` / `ws-ap1` 等もあり）
- レイド時のイベント名: `App\\Events\\StreamHostEvent` / `App\\Events\\StreamHostedEvent`
- 同じ WebSocket でチャット・フォロワー数・サブスクリプション通知も流れている

→ 「Pusher を全部止める」と乱暴だがレイドも消える（無料パス）。
→ 「Pusher の中の StreamHostEvent だけ消す」と外科的（有料パス）。

---

## 比較表

| パス | コスト | 設定時間 | レイドブロック | チャットへの影響 | おすすめ |
| --- | --- | --- | --- | --- | --- |
| **Pathα: NextDNS で Pusher 遮断** | 無料 | 5分 | ✅ 完全 | ❌ real-time 全死 | チャット見ない人 |
| **Pathβ: Surge + 自作 WebSocket スクリプト** | $49.99 | 15分 | ✅ 完全 | 影響なし | 全部欲しい人 |
| **Pathβ': Loon + 同スクリプト** | $4.99 | 15分 | ⚠ Loon 3.x以降のみ | 影響なし | 安く済ませたい人 |

---

## Pathα: NextDNS（無料・チャット死亡）

### 1. NextDNS アカウントを作る
[nextdns.io](https://nextdns.io/) で無料アカウント（300k クエリ/月、ふつうの人は十分）。

### 2. 用意した denylist を入れる
NextDNS ダッシュボード → **Denylist** タブ → 以下を1行ずつ追加：

```
ws-us2.pusher.com
ws-us2-mt1.pusher.com
ws-mt1.pusher.com
ws-eu.pusher.com
ws-ap1.pusher.com
ws-ap2.pusher.com
sockjs-us2.pusher.com
sockjs-mt1.pusher.com
```

リスト本体: [`proxy/nextdns-denylist.txt`](../proxy/nextdns-denylist.txt)

### 3. iPhone に NextDNS の構成プロファイルを入れる
NextDNS ダッシュボード → **Setup** タブ → **Apple → iOS** → 「**Download Configuration Profile**」をタップ
→ Safari で開く → 設定アプリで「インストール」

### 4. iOS の DNS が NextDNS になっていることを確認
設定 → 一般 → VPN とデバイス管理 → DNS → NextDNS にチェック

### 5. Kick アプリを開いて視聴
レイド時間になっても遷移しない。ただしチャットは更新されない。

### 解除したい時
NextDNS のデバイスメニュー → Pause で一時停止、もしくは構成プロファイルを削除。

---

## Pathβ: Surge（$49.99・チャット維持）

[Surge for iOS](https://apps.apple.com/app/surge-5/id1442620678) は HTTPS の中身までスクリプトで触れる、おそらく iOS で唯一の本格派プロキシアプリです。**WebSocket フレームの編集** に対応しているのが本ガイド的に重要。

### 1. Surge をインストール（$49.99）

### 2. ルート CA をインストール
Surge の Home → MitM → **Generate New CA Certificate** → **Install Certificate** → 設定アプリの指示に従って iOS にプロファイルインストール → 設定 → 一般 → 情報 → 証明書信頼設定 で **Surge Root CA を完全に信頼**

### 3. 本リポジトリのモジュールを取り込む
Surge → Modules → 右上の **+** → 「Install from URL」 → 以下を貼り付け：

```
https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/kick-raid-blocker.sgmodule
```

→ Install

### 4. MITM を有効化
Surge → Settings → MITM → ON

### 5. プロキシをアクティブにする
Surge ホームの **Start** をタップ → iOS に VPN プロファイルが出るので許可

### 6. Kick アプリで動作確認
レイドが起きると Surge のログに `[KRB] dropped raid event on chatrooms.<id>` と出ます。チャット・フォロワー数・サブ通知は通常通り。

### モジュールの中身
- [`proxy/kick-raid-blocker.sgmodule`](../proxy/kick-raid-blocker.sgmodule) — Surge module 設定
- [`proxy/kick-raid-blocker-ws.js`](../proxy/kick-raid-blocker-ws.js) — WebSocket フレーム書き換えスクリプト

---

## Pathβ': Loon（$4.99・上手く行けば安上がり）

[Loon](https://apps.apple.com/app/loon/id1373567447) は Surge より安く、3.x 以降で WebSocket スクリプティングに対応。

### 1. Loon をインストール（$4.99）

### 2. ルート CA をインストール（Surge と同じ流れ）

### 3. プラグインを取り込む
Loon → 設定 → プラグイン → URL から追加 → 以下を貼り付け：

```
https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/kick-raid-blocker.plugin
```

### 4. MITM をオンにして起動
Loon の MITM 設定で対象ホストが追加されていることを確認 → ホームの起動ボタン

### 注意
Loon の WebSocket scripting は新しい機能で、バージョンによっては動かないことがあります。動かない場合は Pathα か Pathβ にフォールバック。

---

## こんな組み合わせがおすすめ

> **アプリ視聴メイン + たまにチャット見たい** な人：
>
> - 普段のアプリ視聴は **Pathα（NextDNS）** で raid をブロック（チャット切れる）
> - チャット見たい時だけ **Safari で kick.com**（[ホーム画面追加 ガイド](../README.md#使い方)）→ Userscript v0.2.1 が raid をブロック + チャット動作
>
> どっちのモードでも raid に飛ばされません。

---

## Surge スクリプトの中身を確認したい方

短いので [全行貼ります](../proxy/kick-raid-blocker-ws.js)：

```javascript
const RAID_EVENTS = new Set([
  'App\\Events\\StreamHostEvent',
  'App\\Events\\StreamHostedEvent',
]);

const body = $websocket.body;
try {
  const frame = JSON.parse(body);
  if (RAID_EVENTS.has(frame.event)) {
    frame.event = 'App\\Events\\__krb_dropped__';
    $done({ body: JSON.stringify(frame) });
    return;
  }
} catch {}
$done({});
```

外部送信もテレメトリも一切なく、その場でフレームを書き換えるだけです。

---

## 関連リンク

- [本リポジトリのトップ](../README.md)
- [Userscript（ブラウザ用）](../kick-raid-blocker-mobile.user.js)
- [SECURITY.md](../SECURITY.md)
- [Pusher Channels Protocol](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)
- [KickLib（Kick イベント名の参考実装）](https://github.com/Bukk94/KickLib)
