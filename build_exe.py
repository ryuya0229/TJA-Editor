# build_exe.py
import PyInstaller.__main__
import os
import sys

# アイコンファイルのパス
icon_path = "taiko.ico"

# アイコンファイルが存在するか確認
if not os.path.exists(icon_path):
    print(f"警告: アイコンファイル '{icon_path}' が見つかりません。")
    icon_option = ""
else:
    print(f"アイコンファイル '{icon_path}' を使用します。")
    icon_option = f"--icon={icon_path}"

# PyInstaller コマンドライン引数を構築
args = [
    'tja_editor_main.py',  # エントリーポイントファイル
    '--name=TJA_Editor',
    '--windowed',           # コンソールウィンドウなし
    '--onefile',            # 単一exeファイル化
    '--clean',              # ビルドキャッシュクリーン
    '--add-data=tja_editor_config.json;.',  # 設定ファイル
    '--hidden-import=tkinter',
    '--hidden-import=chardet',
    '--collect-all=chardet',
    '--paths=.',            # カレントディレクトリ
]

# アイコンオプションを追加
if icon_option:
    args.append(icon_option)

# 追加の隠しインポート（必要な場合）
additional_imports = [
    'json',
    're',
    'os',
    'sys',
    'shutil',
    'datetime',
    'subprocess',
    'zipfile',
    'difflib',
    'time'
]

for imp in additional_imports:
    args.append(f'--hidden-import={imp}')

print("PyInstallerを実行します...")
PyInstaller.__main__.run(args)