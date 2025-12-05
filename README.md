# TJA Editor

![メイン画面](https://github.com/ryuya0229/TJA-Editor/blob/main/screanshot0.png)

**TJA Editor** は、太鼓さん次郎・太鼓の達人用TJA譜面を快適に作成できる国産エディタです。  
シンプルで高速、必要な機能はすべて揃っています。

## 主な機能

- 配布用ZIPが1クリックで完成（Ctrl+E）
- リアルタイムドンカツと100%一致の最大コンボ計算
- OGG/WAV音源からBPM・OFFSETを自動検出・補正
- スマートカンマ（Enterで自動でカンマ挿入）
- ヘッダー・譜面コマンドをメニューからワンクリック挿入
- 段位道場作成ツール完備
- ダークモード対応（Ctrl+D）
- 太鼓さん次郎で即プレビュー再生（F5）
- 最近使ったファイル10件保存
- 隠し機能：起動時に約0.1%の確率で「太鼓の達人 公式譜面エディタ」になる（笑）

## スクリーンショット

![ツールメニュー](images/screenshot_tools.png)
![段位道場作成](images/screenshot_dan.png)

## 動作環境

- Windows 10/11（推奨）
- Python 3.8以上

## インストール方法

```bash
git clone https://github.com/あなたのユーザー名/TJA-Editor.git
cd TJA-Editor
pip install numpy matplotlib chardet pydub librosa
python tja_sample.py
```
※PyInstallerでexe化して配布する場合は以下のコマンドでOKです：
```bash
pyinstaller --onefile --noconsole --icon=taiko.ico tja_sample.py
```

 ## 使い方

 - 「ファイル」→「開く or 新規作成
 - 「ヘッダー挿入」「譜面コマンド」から必要なものを選択
 - 譜面を書き込む（Enterで自動カンマ）
 - Ctrl+E で配布用ZIP完成！
 - F5 で太鼓さん次郎で即確認

 ## 開発者より
このエディタは「自作譜面を作るのがもっと楽しくなってほしい」という想いで作りました。
シンプルに、速く、正確に。
そして少しだけ遊び心を。
使ってくれてありがとう。
これからもずっと無料で使い続けてください。
開発者：りゅうちゃん
最終更新：2025年12月

 ## ライセンス
MIT License - 自由に使って、改造して、配布してください！
