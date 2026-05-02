# VPS で Kick 公式アプリのレイドをブロックする (Path γ)

VPS（Linux サーバ）を1台お持ちなら、これが**最良のアプリ向け対策**です。

- ✅ **追加コスト 0**（既に持っている VPS を使う）
- ✅ **公式アプリで動く**（PWAではない、本物のKickアプリ）
- ✅ **チャット・コメント・通知すべて維持**
- ✅ **出先・モバイル回線でも動く**
- ✅ **完全オープンソース・自分の VPS なので外部信頼不要**

## 仕組み

```
[iPhone Kick アプリ]
   ↓ WireGuard VPN
[VPS で動く mitmproxy（WireGuardモード）]
   ├── Pusher WebSocket フレームを Python addon が監視
   ├── App\Events\StreamHostEvent / StreamHostedEvent → 削除
   └── それ以外 → 素通し
   ↓
[Pusher / Kick サーバ]
```

mitmproxy v11 から組み込まれた WireGuard モードのおかげで、追加で WireGuard サーバや iptables を設定する必要がありません。

---

## 必要なもの

| 項目 | バージョン / 詳細 |
| --- | --- |
| VPS | Ubuntu 22.04 / 24.04 / Debian 12 など。**UDP 51820** を許可できること。CPU 1 vCPU・メモリ 512MB で十分 |
| ルート権限 | `sudo` または `root` SSH |
| ドメイン | 不要（IPアドレスでOK） |
| iPhone | 任意のバージョン（[WireGuard 公式アプリ](https://apps.apple.com/app/wireguard/id1441195209) 無料） |

## セットアップ（合計15分）

### 1. VPS にインストール（5分・コマンド3つ）

VPS に SSH して、リポジトリ提供のインストーラを実行します。

```bash
ssh root@<your-vps-ip>
```

```bash
curl -fsSL https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/install-vps.sh | sudo bash
```

このスクリプトは以下を行います：

- `python3-venv` を入れて mitmproxy v11+ を仮想環境にインストール
- 専用ユーザ `krb` 作成
- アドオン `mitmproxy_addon.py` を `/opt/krb/` にダウンロード
- systemd サービス `krb-mitmproxy.service` を作成・自動起動有効化
- UFW で UDP 51820 を許可

**インストール内容を読みたい場合**:
```bash
curl -fsSL https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/install-vps.sh | less
```

### 2. WireGuard QR コードを表示

```bash
journalctl -u krb-mitmproxy -f
```

少し待つと WireGuard サーバの QRコードが ASCII で表示されます。次の操作で iPhone から読み込みます。

### 3. iPhone の WireGuard アプリで取り込む

1. App Store から **WireGuard** をインストール（[公式 Apple App Store](https://apps.apple.com/app/wireguard/id1441195209)・無料）
2. アプリを開く → 右上の **+** → **「Create from QR code」**
3. PCの画面に出ているQRコードをカメラで読む
4. 名前を聞かれるので `KRB` などに → 保存
5. トグルを **ON** にすると VPN が起動

### 4. mitmproxy CA を iPhone に信頼インストール

WireGuard が ON の状態で：

1. Safari で [http://mitm.it](http://mitm.it) を開く
2. **「Apple iOS」** ボタンをタップ → 「許可」
3. 設定アプリ → **「プロファイルがダウンロードされました」** をタップ → インストール
4. 設定 → 一般 → **VPN とデバイス管理** → mitmproxy → **インストール**
5. 設定 → 一般 → 情報 → **証明書信頼設定** → mitmproxy のトグルを **ON**

ここで iOS が「すべての通信が傍受可能になる」と警告を出します。**自分の VPS で自分の証明書なので意図通り** です。`OK` で進みます。

### 5. Kick アプリで動作確認

1. iPhone のホーム画面から **Kick アプリを起動**
2. 普通に配信を視聴
3. レイドが起きても画面が遷移しなくなればOK

VPS のログで確認：
```bash
journalctl -u krb-mitmproxy --since "5 minutes ago" | grep "dropped"
```

レイドをブロックしたタイミングで `[KRB] dropped App\Events\StreamHostEvent on chatrooms.<id>` というログが出ます。

---

## 運用 Tips

### 一時的に止めたい
```bash
systemctl stop krb-mitmproxy
```
iPhone 側で WireGuard をオフにしても素通しになります（一時無効化）。

### 起動し直したい
```bash
systemctl restart krb-mitmproxy
```

### 設定確認
```bash
systemctl status krb-mitmproxy
journalctl -u krb-mitmproxy -n 50
```

### アンインストール
```bash
curl -fsSL https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/proxy/uninstall-vps.sh | sudo bash
```
そのあと iPhone 側で：
- WireGuard アプリで KRB プロファイルを削除
- 設定 → VPN とデバイス管理 → mitmproxy CA プロファイルを削除

---

## セキュリティ・プライバシーに関する重要な注意

- mitmproxy CA を信頼すると、その VPS から **HTTPSの中身が原理上覗ける** 状態になります（自分の VPS なので問題ないですが、CAインストールしたまま放置はNG）
- WireGuard トンネルは公開鍵認証で他人は接続不可。プライベートキーは VPS の `/opt/krb/conf/` 配下に保管
- このアドオンは **`App\\Events\\StreamHost(ed)?Event` だけを drop** し、他のフレームは一切触りません（[ソースコード](../proxy/mitmproxy_addon.py)で全行確認可能、約80行）
- mitmproxy 自身のソースコードは [github.com/mitmproxy/mitmproxy](https://github.com/mitmproxy/mitmproxy) で完全公開されています
- VPS が乗っ取られると、信頼している CA で任意のサイトを偽装される恐れがあります → **VPS の SSH キー認証・rootログイン禁止・自動更新の有効化** などの一般的な VPS 防御は別途必須

## トラブルシューティング

### QRコードが表示されない
- `systemctl status krb-mitmproxy` で起動確認
- `journalctl -u krb-mitmproxy -n 100` でエラー確認
- ファイアウォール (UFW / クラウド側 SecGroup) で UDP 51820 が空いているか

### iPhoneで WireGuard 接続できない
- VPS の **パブリック IP** を WireGuard アプリの設定で確認
- VPS のセキュリティグループで UDP 51820 が開いているか
- iOS 設定 → 一般 → VPN で WireGuard が有効か

### レイドが止まらない
- Kick が新しいクラスタ (例: `ws-newregion.pusher.com`) を使い始めた可能性
- `journalctl -u krb-mitmproxy -f` でレイド時のフレームを観察 → 必要ならアドオンの `RAID_EVENTS` セットを更新して Issue で教えてください

### iPhone のすべての通信が遅い／切れる
- mitmproxy の負荷が高い → VPS のスペックを上げる、または `--mode wireguard@<ip>:51820` で別ポートに分離
- 自宅ネットワークと VPS のレイテンシが大きすぎる場合、視聴体験が落ちます → 地理的に近い VPS を選ぶ

---

## 関連リンク

- [本リポジトリ README](../README.md)
- [docs/app-raid-blocking.md](app-raid-blocking.md) — 全パスの比較
- [SECURITY.md](../SECURITY.md)
- [mitmproxy WireGuard mode 公式記事](https://www.mitmproxy.org/posts/wireguard-mode/)
- [mitmproxy v11 リリースノート](https://github.com/mitmproxy/mitmproxy/releases)
