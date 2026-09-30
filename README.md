# MSX LiveBridge

> このリポジトリはVer1.0.4の**ソース公開用**です。Windows完成版は[GitHub Releases](https://github.com/rx7nana/MSX-LiveBridge/releases)から取得してください。以下の一般ユーザー向け説明でいう `_internal`、内包MGSDRV、`licenses/` 等はWindows配布ZIPの構成を指し、本ソースツリーには含みません。開発手順は末尾と [docs/BUILD.md](docs/BUILD.md) を参照してください。


**MSX LiveBridge** は、Webブラウザ上の **msxplay** で作成・再生したMMLを、VSIFを介してMSX実機の音源で演奏するためのWindowsアプリケーションです。

msxplayで通常どおりMMLを編集し、Compile / PLAYすることで、MSX実機のPSG・OPLL・SCCから演奏できます。

msxplay自体を改造する必要はありません。

## 対応バージョン

**MSX LiveBridge Ver1.0.4**

Ver1.0.4は、Chrome Web Storeから実際にインストールした拡張を使用して最終実機テスト済みです。開発版拡張は使用せず、Chrome Web Store版のみを有効にした状態で確認しています。MGSDRV由来データの現行バイナリへの内包配布は許諾済みです。本体独自部分はMIT License（Copyright (c) 2026 NANA）です。
Google ChromeとMicrosoft Edgeでは、同じChrome Web Store版のChromium拡張を使用します。

## 主な機能

- msxplayのCompile / PLAYに連動したMSX実機演奏
- PSG対応
- OPLL対応
- SCC対応
- SCC波形RAM書き込み対応
- PAUSE / RESUME連動
- 前方・後方シーク対応
- 連続シーク対応
- MML編集後の再Compileへの追従
- 曲終端でのフェードアウト
- 再生終了後の実機音源無音化
- FT232H / FT232R / Customプロファイル
- Chromium拡張によるmsxplayとの自動連携

ブラウザ側とMSX実機側では処理経路が異なるため、PLAY、PAUSE、SEEK等の操作から実機音声が反応するまでに多少の時間差が生じる場合があります。

MSX LiveBridgeでは厳密な同時発音より、操作順序と演奏状態の一貫性を優先しています。

## 必要な環境

### Windows側

- Windows 10 / 11 x64（64bit版）。Windows 11開発PCで配布フォルダ検証済み。別のクリーンWindowsでの検証は未実施
- MSX LiveBridge
- Google ChromeまたはMicrosoft Edge（Chromium版）
- MSX LiveBridge Chromium拡張
- 対応FTDIを使用したVSIF
- Windows用FTDI D2XXドライバー（別途導入）

### MSX側

MSX LiveBridgeは、既存のVSIF受信環境を使用します。

現在の実機検証では、MSX-DOS上からNGLOAD.COMを使用してVGM_msx.romを起動する環境を使用しています。

NGLOAD.COM、VGM_msx.rom等の第三者配布物については、MSX LiveBridgeとは別に適切な配布元・利用条件に従って用意してください。本アプリの同梱物としては案内していません。

受信プログラムは使用するVSIFに対応した版を組み合わせてください。古い受信ROMでは通信形式が合わない場合があります。演奏する音源に応じて、OPLLやSCC等も必要です。

## 対応音源

現在確認済みの音源は以下です。

- PSG
- OPLL
- SCC

SCCについては波形RAM書き込みにも対応しています。

## FTDI設定

通常は **自動** を選択してください。

選択可能なプロファイル：

- 自動
- FT232H
- FT232R
- Custom

### FT232H

実機確認済みです。

- 240,000 baud
- async bit-bang
- clock幅 32

### FT232R

プロファイルを用意していますが、Ver1.0.4時点では実機確認未完了です。

初期設定：

- 240,000 baud
- clock幅 25

FT232R環境では調整が必要になる可能性があります。

### Custom

baud rate、clock幅等を手動設定するためのプロファイルです。

通常利用では変更する必要はありません。

## 導入方法

Windows版は[GitHub Releases](https://github.com/rx7nana/MSX-LiveBridge/releases)から取得し、Chromium拡張はChrome Web Storeからインストールします。Microsoft Edgeでも同じChrome Web Store版を利用できます。

1. `MSXLiveBridge-1.0.4-win-x64.zip`をすべて展開します。
2. 展開したフォルダー全体を保存します。
3. `MSXLiveBridge.exe`を起動します。移動した場合も、移動先で一度起動するとブラウザ連携の登録先が更新されます。

現行Ver1.0.4のWindowsアプリは、**MSXLiveBridge.exeだけでは動作しません**。付属の`_internal`フォルダーを含め、フォルダー全体を同じ場所に置く必要があります。PythonやNode.js、Visual Studioを利用者がインストールする必要はありません。

FTDI D2XXドライバーとMSX側の受信環境は、各配布元の案内に従って別途準備してください。MGSDRV由来データは内部の変換EXEに内包されています。Windows利用者がMGSDRV.COMを追加する必要はありません。

### Chromium拡張のインストール

MSX LiveBridgeのChromium拡張は、[Chrome Web Store](https://chromewebstore.google.com/detail/msx-livebridge/cfkcbmejlakciepflheboofnphdkoghf)からインストールしてください。Google ChromeおよびMicrosoft Edgeで同じChrome Web Store版を利用できます。

**Google Chrome**

Chrome Web StoreからMSX LiveBridgeをインストールしてください。インストールして有効にした後は、通常は拡張機能を操作する必要はありません。

**Microsoft Edge**

Microsoft Edgeでも、Chrome Web Storeから同じMSX LiveBridge拡張をインストールできます。必要に応じて、Edgeで「他のストアからの拡張機能を許可する」を有効にしてからインストールしてください。

ChromeとEdgeで同じChrome Web Store版を使用します。Edge向けの別ストア版は現時点では提供しません。

拡張を導入・有効化した後は、すでに開いているmsxplayのページを一度再読み込みしてください。Windowsアプリを起動すると、そのWindowsユーザーのブラウザとの連携を自動登録します。

## Chromium拡張

MSX LiveBridge用Chromium拡張は、インストールして有効にしておけば通常は操作不要です。

MSX LiveBridge Windowsアプリが起動している場合、拡張が自動的にローカルのMSX LiveBridgeと連携します。

Windowsアプリが起動していない場合、VSIFへの通信は行われません。

この場合もmsxplay自体は通常どおりブラウザ上で使用できます。

## 基本的な使い方

1. VSIFをPCとMSX実機へ接続します。
2. MSX側で必要な受信環境を起動します。
3. MSX LiveBridge Chromium拡張を有効にします。
4. WindowsでMSX LiveBridgeを起動します。
5. FTDI設定は通常「自動」のまま使用します。
6. ブラウザで[msxplay](https://msxplay.com/)を開きます。
7. MMLをCompileしてPLAYします。
8. MSX実機から演奏されることを確認します。

以後はmsxplayを通常どおり操作してください。

アプリの状態が「msxplay待機中」になることを確認してから再生してください。この表示はFTDIを検出した状態であり、MSX側の受信プログラムが正しく動作していることまで自動確認するものではありません。

Windowsアプリを後から起動した場合は、次のCompile / PLAYから連携します。ブラウザで再生中の曲が突然実機でも再生されることはありません。

## 再生操作

MSX LiveBridgeは、msxplay側の再生操作に追従します。

対応している主な操作：

- PLAY
- PAUSE
- RESUME
- SEEK
- 再Compile

シーク時にはWindows側で指定位置の音源状態を再構築します。再生中ならその位置から再開し、一時停止中なら停止状態を保ち、RESUMEで再開します。

ブラウザの表示・音声と実機音声の反応時刻には多少の差が生じる場合があります。

## MSX LiveBridgeの終了

MSX LiveBridgeのウィンドウを閉じるとアプリは完全終了します。

終了時には実機音源を無音化し、VSIFとの通信も終了します。

タスクトレイへ常駐して通信を続ける仕様ではありません。最小化しただけの場合は、アプリが起動したままなので演奏を続けます。

## トラブルシューティング

### VSIFが見つからない

- VSIFがPCへ正しく接続されているか確認してください。
- FTDI D2XXドライバーが導入されているか確認してください。
- FTDI設定を確認してください。複数のFTDI機器を接続している場合は、歯車の詳細設定で使用する機器を選択してください。
- 他のアプリが同じFTDIデバイスを使用していないか確認してください。

### msxplayでは鳴るがMSX実機から鳴らない

- MSX LiveBridgeが起動しているか確認してください。
- Chromium拡張が有効になっているか確認してください。
- MSX側の受信環境が起動しているか確認してください。
- MSX LiveBridgeの状態表示を確認してください。
- 拡張導入前から開いていたmsxplayは再読み込みし、もう一度Compile / PLAYしてください。

詳しい状態は、歯車の詳細設定にある「診断ログ」で確認できます。

### 「FTDIは使用中です」「FTDI検出エラー」と表示される

同じFTDIを使用する他のアプリを終了してください。回復しない場合はMSX LiveBridgeを終了し、Windows側のUSBを抜いて数秒待ってから挿し直し、アプリを起動してください。使用中と未接続は異なる状態です。

### FT232Rを使用している

FT232RプロファイルはVer1.0.4時点では実機確認未完了です。

必要に応じてCustom設定を使用してください。

## 既知の制約

- ブラウザ音声と実機音声は完全な同時再生ではありません。
- FT232RプロファイルはVer1.0.4時点で実機検証未完了です。
- 現在の実機確認対象はPSG、OPLL、SCCです。
- MSX側には別途VSIF受信環境が必要です。
- 現行拡張の対象は`https://msxplay.com/`です。別のサイトに設置したmsxplayへの対応は確認していません。
- 自動選択はFTDI機器の検出です。MSX側の起動や配線、受信プログラムの確認は別途必要です。

## MGSDRVについて

**MGSDRV (C) Ain./Gigamix**

作者：Ain.／管理・メンテナンス：Gigamix。公式案内：https://www.gigamix.jp/mgsdrv/

内部の`_internal/vendor/kss2vgm.exe`に、libkss / kss-drivers経由でMGSDRV 3.18由来の8083バイトのデータを内包しています。MGSDRV.COM単体は同梱していません。現在の内包配布形態は、権利管理者Gigamix小林氏から許諾を得ています。今回の配布整理によるMGSDRVプログラムの変更はありません。

`licenses/MGSDR320.TXT`は公式の現行説明書をそのまま収録したクレジット資料です。内包ドライバーを3.20へ更新したことを意味しません。今回の許諾はNGLOAD.COM、VGM_msx.romや他の音楽ドライバーへ拡張されません。

## 第三者ソフトウェア・クレジット

同梱内容・権利表示は`THIRD-PARTY-NOTICES.md`と`licenses`を参照してください。

- kss2vgm 0.1.4 / libkss：Mitsutaka Okazaki
- MGSDRV：Ain./Gigamix
- その他の内包音楽ドライバー：KINROU5、MPK、OPX4KSS、MoonBlaster replayer
- Python / Tcl/Tk / PyInstallerと、それらに組み込まれたライブラリ
- msxplay / VSIF / MAmidiMEmo・VGMPlayer：相互運用先・仕様調査元。これらのアプリ本体は同梱していません
- FTDI D2XX：別途導入するWindows用ドライバー。DLLは同梱していません

現在のkss2vgm公式バイナリには**商用利用・有料配布不可**の条件があります。本体ソースのライセンスとは別の条件です。MGSDRVについての許諾だけで、この条件が取り除かれるわけではありません。

各製品・技術はそれぞれの作者・権利者に帰属します。MSX LiveBridgeはそれらの公式製品を名乗るものではありません。

## 保存データ・プライバシー

Windowsアプリは`127.0.0.1:27183`のみで待ち受けます。拡張はmsxplayのMGSデータと操作を、このPC内のアプリへ渡します。アプリ・拡張に外部への送信やアクセス解析はありません。msxplayサイト自体の通信は、そのサイトの方針に従います。

設定・診断ログ・直近の演奏変換データは`%LOCALAPPDATA%\MSXLiveBridge`に保存します。演奏データはアプリの正常終了時に直近3実行分を残して整理します。終了してもデータがすべて消える方式ではありません。認証情報は起動ごとに生成し、正常終了時に削除します。公開ZIPには設定・演奏データ・認証情報を含みません。

## ライセンス

MSX LiveBridge独自部分はMIT License（Copyright (c) 2026 NANA）です。全文は`LICENSE.txt`を参照してください。第三者コンポーネントはMITへ変更せず、それぞれのライセンス・許諾条件に従います。


## 開発者向け：公開ソース

現行Ver1.0.4のChrome Web Store ID対応版を基準としています。WindowsはストアID `cfkcbmejlakciepflheboofnphdkoghf` と開発版ID `fcebnajmcgjhmkbgefjgaaadnjpdamnc` を許可します。正式配布はChrome / Edgeとも同じChrome Web Store版です。

2026-10-01、Google Chromeにストアから実インストールしたVer1.0.4拡張のみを有効にした最終実機テストで、次のすべてが正常と確認されました。

- Compile → PLAY、PSG / OPLL / SCC、SCC波形変化、正常テンポ
- PAUSE / RESUME、前方・後方・連続SEEK、PAUSE中SEEK、MML編集後の再Compile
- 開始前ノイズなし、残音なし、二重再生なし
- 終端フェード、終端後の完全無音、次回PLAY時の通常音量復帰
- 再生中のWindowsアプリ終了による無音化、Windowsアプリ再起動後のVSIF再検出

この結果はGoogle Chromeでの確認です。Microsoft Edgeで別途最終実機テストを完了したことを示すものではありません。

| 場所 | 内容 |
|---|---|
| src/ | UI、Bridge、再生状態管理、MGS/VGM処理、VSIFエンコード、FTDI検出、認証、終端フェード |
| native/ | Native Sender、FTDI呼出し、Connect、音源プロファイル、アイコン・バージョンリソース |
| extension/ | ストア提出版のmanifestと同梱JavaScript・LBアイコン。keyなし |
| config/manifest.unpacked.json | 開発版固定IDの公開鍵を含むmanifest |
| assets/ | 正式LB原本、各サイズPNG、マルチサイズICO |
| tests/ | 自動テスト、模擬FTDI、VSIFデコード補助。検証曲・ログは非同梱 |
| tools/ | 拡張のstore/unpacked別生成、依存変換器のハッシュ照合 |
| docs/BUILD.md | 開発環境、ビルド、依存物の取得、テストの手順 |

Windowsでの開発にはPython、MSVC/Windows SDK、PyInstaller、テストにはPillow/Node.jsを使います。kss2vgm公式0.1.4は条件を確認して別途用意してください。libkss、kss2vgm、MGSDRV由来データ、FTDI DLL、Python/Tcl/Tkランタイムはソースリポジトリへ含めません。一般ユーザーにはこれらの開発ツールは不要です。

実装のプライバシー方針は [PRIVACY.md](PRIVACY.md) を参照してください。楽曲・操作・認証・限定したURL確認を扱いますが、拡張から開発者・外部サーバー・第三者へ送りません。リモートコードを使用しません。

この公開整理で動作コードは変更していません。公開用ツリーでは、ビルド・テストの個人絶対パスの除去、非公開回帰データの外部指定、状態ファイル更新中の一時的な読取失敗に対応するテスト補助の調整を行っています。完成ZIP・実行ログ・認証情報・第三者バイナリはGitへ登録せず、`.gitignore` を維持してください。
