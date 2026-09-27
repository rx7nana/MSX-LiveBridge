# ソースからのビルドとテスト

一般ユーザーはGitHub ReleasesのWindows ZIP全体を展開して利用します。以下は開発者向けです。ソースリポジトリだけでは依存バイナリがないため、そのまま完成EXEにはなりません。

## 開発環境

- Windows 10/11 x64。ビルド・テストの実確認はWindows 11。
- Python 3.12 x64（tkinter/Tcl/Tkを含むWindows版）。基準版は3.12.14。
- Visual Studio Build ToolsのC++デスクトップ開発、MSVCとWindows SDK（cl、rc）。基準版はMSVC 19.51、C++20、/MT。
- `requirements-dev.txt` のPyInstaller 6.22.3（EXE化）、Pillow 12.3.0（アイコンテスト）。通常実行コードは標準ライブラリのみ。
- Node.js（組み込みnode:testとWeb Cryptoが使える版）。基準検証は24.19.0。npmパッケージは不要。
- kss2vgm公式Windowsバイナリ0.1.4。下記の条件を確認して別途取得。

FTDI SDKのヘッダー・ライブラリはビルドに不要です。D2XXを動的に呼びます。実機再生時にはFTDI公式D2XXドライバーが必要ですが、自動テストは自作の模擬DLLを使い実機へ送信しません。

## 変換器の準備

[kss2vgm 0.1.4公式リリース](https://github.com/digital-sound-antiques/kss2vgm/releases/tag/0.1.4)の `kss2vgm-win-0.1.4.zip` を取得し、`kss2vgm-win-0.1.4/kss2vgm.exe` を `vendor/kss2vgm.exe` に置いてください（vendorディレクトリは必要に応じて作成）。リポジトリにはコミットしません。

- ZIP SHA-256: `5f1eb1a3d638bc99f025c90e65607ffa5d5f8b9554cef5558be45e33ef608818`
- EXE SHA-256: `36314759d87c41077e8cc8dcd69f174d97da688883a8e62e506b5d7b87bdeeb6`
- 公式バイナリの商用利用・有料配布不可条件を維持してください。MGSDRV等の内包データをMITと扱わないでください。
- MGSDRV等を本リポジトリへ展開・転載する手順ではありません。取得した依存物はローカルだけで使用します。

```bat
python tools\check-dependencies.py
```

## Windowsアプリ

Visual Studioの **x64 Native Tools Command Prompt** でリポジトリ直下へ移動し、実行します。Python仮想環境を有効にしてから実行してください。

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
call build-native.cmd
python tools\check-dependencies.py
python build-app.py
```

`build-native.cmd` はEngine、Connectおよび模擬FTDIを使うテスト用Senderを生成します。`build-connect.cmd` はConnectのみ再ビルドします。完成アプリを起動中には `build-app.py` は実行できません。

開発用出力は `dist/MSXLiveBridge/MSXLiveBridge.exe` と `_internal` です。EXE単体では動きません。生成物をGitHubのソースへアップロードしないでください。

これは開発用ビルド手順です。公開Windowsパッケージを再配布する場合は、依存ライブラリと内包ドライバーの全LICENSE/NOTICE、MGSDRV許諾、変換器の条件、Windows実機スモークを別途確認してください。`build-app.py` の出力だけを、その確認なしに正式配布ZIPと扱わないでください。環境・ツールチェーンによりバイナリハッシュは変わるため、元のEXEとのバイト一致は保証しません。

## Chromium拡張

`extension/` は提出版そのものに対応し、manifestにkeyはありません。開発版の固定ID用公開鍵は `config/manifest.unpacked.json` に分離しています。この公開鍵は秘密鍵や認証tokenではありません。

```bat
python tools\package-extension.py --target unpacked
python tools\package-extension.py --target store
```

開発時は `build/extension-unpacked/` をブラウザの「パッケージ化されていない拡張機能を読み込む」で指定します。提出ZIPは `build/MSXLiveBridge-Extension-1.0.4.zip`。ZIP直下にmanifestがあります。出力が既存の場合は事故防止のため停止するので、不要な出力を自分で整理してから再実行してください。

Windows側の許可IDは以下の2つです。keyなしの `extension/` を直接unpacked読み込みすると別IDになり、接続できない場合があります。

- Chrome Web Store: `cfkcbmejlakciepflheboofnphdkoghf`
- 開発版: `fcebnajmcgjhmkbgefjgaaadnjpdamnc`

Edge Add-ons固有IDは未確認です。ストア掲載・審査・一般公開の操作を、このビルド手順では行いません。

## 自動テスト

Nativeビルド後、リポジトリ直下で実行します。

```bat
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_control.mjs tests/test_extension.mjs
```

検証用楽曲と実機由来write列は公開していません。それらがない場合、該当テストは理由付きでskipし、模擬FTDI・合成write列・認証・拡張のテストは実行します。skipを全件合格と扱わないでください。

元の回帰資産を適法に利用できる開発者は、`MSXLB_TEST_FIXTURES` に非公開の入力フォルダを指定できます。必要なファイル名は `contrail.mgs`、独立した編集後データの `edited.mgs`、`writes.jsonl`、`baseline-initial.jsonl`、`baseline-seek.jsonl`。既存の特定データに対する期待値があるため、任意の曲への置き換えでは同一テストになりません。元データの取得・公開権を提供するものではありません。

変換器だけ別の場所に置く場合は `MSXLB_KSS2VGM` を指定できます。これらの環境変数・個人パスをソースへ書き込まないでください。

公開整理時の検証では、非公開入力を別フォルダから指定したPython回帰69件とJavaScript23件がすべて成功しました。非公開入力なしではPython47件成功・22件skipでした。Native/Windows EXEの再ビルドも成功し、拡張store ZIPは受理済みVer1.0.4 ZIPとSHA-256が一致しました。検証は公開ソースの別コピーで行い、生成物・ログ・検証曲はこのリポジトリへ含めていません。別のクリーンWindows環境での新規依存インストール検証や、再ビルドEXEによる実機確認を完了したという意味ではありません。
