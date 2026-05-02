# Kick 公式アプリでもレイドをブロックする

公式アプリはネイティブアプリなので Userscript が動きません。それでもアプリで見たまま守りたい人のために、現実的な3つの方法を効果・難易度・コストで比較します。

## 技術的に何が起きているか

Kick のレイドは **Pusher WebSocket 経由** で配信されます：

- 接続先: `wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679`
- レイド時のイベント名: `App\\Events\\StreamHostEvent` / `App\\Events\\StreamHostedEvent`
- チャンネル: `chatrooms.<chatroomId>`

チャット・フォロー数・サブスク通知など**すべての real-time 通信が同じ WebSocket** を流れます。これがアプリ側ブロックの難しさの根本原因です。

## 比較表

| 方法 | 月額 | 設定難易度 | レイドブロック | チャットへの影響 | おすすめ度 |
| --- | --- | --- | --- | --- | --- |
| **A. ホーム画面追加（PWA）** | 無料 | ★☆☆☆☆ | 完全 | 影響なし | ⭐⭐⭐⭐⭐ |
| **B. NextDNSでPusherを遮断** | 無料 | ★★☆☆☆ | 完全 | 全 real-time が壊れる | ⭐⭐ |
| **C. 有料プロキシアプリ + 自作スクリプト** | $5〜 | ★★★★★ | 完全 | 影響なし | ⭐⭐⭐ |

---

## A. ホーム画面追加（一番おすすめ・無料・5分）

iPhone 標準機能で kick.com を「擬似アプリ」化します。**既に作成済みの Userscript v0.2.1 がそのまま動く**ため、追加開発不要・コスト0で完全なレイドブロックが手に入ります。

### 手順
1. iPhone で Userscripts アプリ（[App Store 無料](https://apps.apple.com/app/userscripts/id1463298887)）をインストール、設定 → Safari → 機能拡張 で有効化
2. このリポジトリのインストールリンクから Userscript を入れる: <https://aiaidaisuki.github.io/kick-raid-blocker-mobile/>
3. Safari で `https://kick.com/` を開く
4. **共有ボタン（□↑） → 「ホーム画面に追加」**
5. ホーム画面に Kick アイコンができる → タップすると全画面で開く（アドレスバー無し）

### 失うもの
- 公式アプリの一部の native UI（細かなアニメーションなど）
- iOS push 通知（Safari の web push で代替可能。Kick の通知許可をオンにすればOK）

### 得るもの
- ✅ Userscript によるレイドブロックが動く
- ✅ 設定変更も右下の 🛡 ボタンで完結
- ✅ chat / followers / subs などすべて通常通り
- ✅ コスト 0 円

---

## B. NextDNS で Pusher WebSocket を完全遮断（無料・乱暴）

Pusher の接続先 (`ws-us2.pusher.com`) を DNS レベルで全部止める方法。**レイドは止まりますがチャット等の real-time 機能もすべて死にます**。「視聴できれば良い、チャットいらない」派にはアリ。

### 手順
1. [NextDNS](https://nextdns.io/) で無料アカウントを作る（300k クエリ/月まで無料）
2. ダッシュボード → Denylist に以下を追加:
   ```
   ws-us2.pusher.com
   sockjs-us2.pusher.com
   ```
3. Setup タブから **Apple → iOS** の Configuration Profile をダウンロード
4. iPhone の設定 → プロファイル管理 → インストール
5. 設定 → 一般 → VPN とデバイス管理 → DNS で NextDNS が選択されていることを確認

### 副作用
- ❌ Kick アプリのチャット real-time 更新が止まる（再読み込み必要）
- ❌ フォロワー数・視聴者数の自動更新停止
- ❌ サブスク・ギフト通知が来ない
- ❌ 他サイトの Pusher 利用サービスにも影響（Notion 等は別の Pusher app を使うので影響なし）

### 解除方法
NextDNS のデバイスメニューから一時的にオフにできます。

---

## C. 有料プロキシアプリ + 自作スクリプト（$5〜・上級者向け）

Loon ($4.99) や Surge ($49.99) などの iOS 用 HTTPS-MITM プロキシアプリで、Pusher WebSocket フレームを inspect して `App\\Events\\StreamHostEvent` を含むメッセージだけ drop します。これだけが**外科的なブロック**を実現します。

### 必要なもの

- iOS App Store で **Loon**（$4.99）または **Surge**（$49.99）
- ルート CA 証明書のインストール（プロキシアプリが案内）
- iOS で「証明書を完全に信頼」設定

### 概念実装（Loon JavaScript script）

```javascript
// loon-kick-raid-blocker.js
// Pusher WebSocket frame interceptor for Kick raid blocking
// Drops App\\Events\\StreamHostEvent / StreamHostedEvent messages.

const body = $websocket.body;  // raw frame
try {
  const obj = JSON.parse(body);
  const evt = obj.event || '';
  if (evt === 'App\\Events\\StreamHostEvent' || evt === 'App\\Events\\StreamHostedEvent') {
    console.log('[KRB] dropped raid event', obj.channel);
    $done({ body: '' });   // drop frame
    return;
  }
} catch {}
$done({});  // pass through
```

Loon の設定で `wss://ws-us2.pusher.com/*` にこのスクリプトを bind します。

### 課題
- 設定が複雑（ルート証明書のインストール・信頼設定で iOS が何度も警告を出す）
- Kick がイベント名変えたら追従メンテ必要
- WebSocket scripting は iOS プロキシアプリの中でも比較的新しい機能で、挙動が安定しない場合がある
- 通信経路すべてがプロキシを通るためバッテリー消費が増える

これ用のスクリプトファイルが必要であれば追加で書き起こします → リクエストください。

---

## 結論：何をすべきか

### ほとんどの人 → A（ホーム画面追加）

公式アプリと体感差がほぼ無く、追加コスト0、レイドブロック完全動作。失うのは push 通知のみ（しかも Safari web push で代替可）。

**5分で終わるので、まずこれを試してから他を考える** のが合理的です。

### チャットいらない・絶対アプリ → B（NextDNS）

ただし real-time が壊れるので、視聴専門の人向け。

### コードを書きたい・お金払える → C（プロキシアプリ）

精密だが構築・維持コストが高い。技術的興味がある人向け。

---

## 関連リンク

- [Userscript 本体（v0.2.1）](../kick-raid-blocker-mobile.user.js)
- [配布ページ](https://aiaidaisuki.github.io/kick-raid-blocker-mobile/)
- [Pusher Channels Protocol](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)
- [KickLib（Kick イベント名の参考実装）](https://github.com/Bukk94/KickLib)
