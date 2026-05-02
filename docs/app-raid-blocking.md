# Kick 公式アプリでもレイドをブロックする

公式アプリはネイティブアプリなので Userscript が動きません。それでも **アプリのまま守りたい** 人のために、すぐ使える設定ファイルを用意しました。

## 何が起きているか

Kick のレイドは Pusher WebSocket 経由で配信されます：

- 接続先: `wss://ws-us2.pusher.com/app/<APP_ID>`（クラスタ違いで `ws-mt1` / `ws-eu` / `ws-ap1` 等もあり）
- レイド時のイベント名: `App\\Events\\StreamHostEvent` / `App\\Events\\StreamHostedEvent`
- 同じ WebSocket でチャット・フォロワー数・サブスクリプション通知も流れている

→ レイドだけ消すには **WebSocketフレームを開いて当該イベントだけ drop** する必要がある。

---

## 比較表

| パス | コスト | 設定 | レイドブロック | チャット維持 | 出先で動く | 確実性 |
| --- | --- | --- | --- | --- | --- | --- |
| **α: NextDNS で Pusher 遮断** | 無料 | 5分 | ✅ | ❌ real-time 全死 | ✅ | ✅ |
| **β: Surge / Loon プラグイン** | $5〜$50 | 15分 | ⚠ | ✅ | ✅ | ❌ **未検証** |
| **γ: 自分の VPS + mitmproxy** | 既存VPSで0円 | 15分 | ✅ | ✅ | ✅ | ✅ **検証済み** |

> **VPSをお持ちならγが最善**です。コスト0で全部維持しつつアプリのままレイドブロック。

> 旧バージョンのこのドキュメントでは β を勧めていましたが、**Surge/Loon の WebSocket frame scripting は公式ドキュメントで保証されていない** ことが判明したため格下げしました（プラグインファイルは残してありますが「動けばラッキー」程度の扱いでお願いします）。

---

## Pathγ: 自分の VPS + mitmproxy（推奨・無料・全機能維持）

詳細手順 → **[docs/vps-setup.md](vps-setup.md)** に切り出しています。要点だけ：

```bash
# VPS にSSHして1コマンド
curl -fsSL https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/install-vps.sh | sudo bash

# 出るログから WireGuard QR を読んでiPhoneに登録
journalctl -u krb-mitmproxy -f
```

仕組み：
- mitmproxy v11+ の WireGuard モードでiPhoneのトラフィックを VPS に集約
- Pythonアドオンが Pusher WebSocket フレームを覗き、`StreamHostEvent` だけ削除
- それ以外（チャット等）は素通し

→ Kickアプリ・チャット・通知すべて動く。出先 LTE/5G でも動く。**コスト0**（既存VPSを使うので）。

[mitmproxyのアドオン全文（80行）](../proxy/mitmproxy_addon.py) ・ [systemd unit](../proxy/krb-mitmproxy.service) ・ [インストーラ](../proxy/install-vps.sh)

---

## Pathα: NextDNS で Pusher 遮断（無料・チャット死亡）

VPS を持っていない or VPS設定したくない人向けの**簡単パス**。ただし**Kickのチャットがリアルタイム更新されなくなる**のでコメントもできなくなります。視聴専門なら全く問題なし。

### 手順

1. [nextdns.io](https://nextdns.io/) で無料アカウントを作る（300k クエリ/月、ふつうの人は十分）
2. NextDNSダッシュボード → **Denylist** タブ → 以下を1行ずつ追加：

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

3. NextDNS ダッシュボード → **Setup** → **Apple → iOS** → 「**Download Configuration Profile**」 をタップ → Safariで開く → 設定アプリで「インストール」
4. 設定 → 一般 → VPN とデバイス管理 → DNS → NextDNS にチェックされていることを確認
5. Kick アプリで視聴開始 → レイド遮断、チャットは止まる

### 解除したい時
NextDNS のデバイスメニュー → Pause で一時停止、または構成プロファイルを削除。

---

## Pathβ: Surge / Loon プラグイン（実験的・動作未保証）

> ⚠️ **このパスは慎重に検討してください。** Surge ($49.99) や Loon ($4.99) のスクリプティングAPIに **`type=websocket-message` 相当の WebSocket frame body 編集機能が公式に明記されていない** ため、リポジトリに置いてあるプラグインファイル（[`kick-raid-blocker.sgmodule`](../proxy/kick-raid-blocker.sgmodule) / [`kick-raid-blocker.plugin`](../proxy/kick-raid-blocker.plugin)）が**実際の端末で動作しない可能性があります**。

確実性が必要な方は **Path γ（自分のVPS）** か **Pathα（NextDNS）** をご利用ください。それでも試したい方は、まず**返金可能な期間内**に検証することを推奨します（Apple App Store は購入後14日間以内なら返金申請可能）。

スクリプトの中身: [proxy/kick-raid-blocker-ws.js](../proxy/kick-raid-blocker-ws.js)

```javascript
const RAID_EVENTS = new Set([
  'App\\Events\\StreamHostEvent',
  'App\\Events\\StreamHostedEvent',
]);
const frame = JSON.parse($websocket.body);
if (RAID_EVENTS.has(frame.event)) {
  frame.event = 'App\\Events\\__krb_dropped__';
  $done({ body: JSON.stringify(frame) });
} else {
  $done({});
}
```

---

## Path A: ホーム画面追加（PWA）— アプリじゃないが最も楽

公式アプリにはこだわらない方には、**Safariで kick.com を開いてホーム画面に追加**する方法が一番簡単です（[README参照](../README.md#使い方)）。アプリそっくりの見た目で、既存のUserscriptがそのまま動きます。

---

## おすすめの選び方

| こんな人 | おすすめ |
| --- | --- |
| **VPSを持っている** | **Pathγ** （無料・全機能・本物アプリ） |
| 視聴のみ・コメントしない | Pathα（無料） |
| アプリじゃなくてもいい | Path A（PWA・無料・全機能） |
| 公式アプリ + 機能維持・VPSない | 残念ながら無料の解はなし。$5〜$50払って Pathβ をギャンブル試行する選択肢のみ |

---

## 関連リンク

- [VPS セットアップ詳細](vps-setup.md)
- [mitmproxy アドオン本体](../proxy/mitmproxy_addon.py)
- [Userscript 本体（ブラウザ用）](../kick-raid-blocker-mobile.user.js)
- [配布ページ](https://aiaidaisuki.github.io/kick-raid-blocker-mobile/)
- [Pusher Channels Protocol](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/)
- [KickLib（Kick イベント名の参考実装）](https://github.com/Bukk94/KickLib)
