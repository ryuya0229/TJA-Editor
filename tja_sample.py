import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, Toplevel, ttk
from tkinter import font as tkfont
from tkinter import Listbox, Scrollbar, Button, Entry, Label, Frame, LabelFrame, Checkbutton
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "MS Gothic"
import re
import sys
import subprocess
import os
import shutil
import json
import chardet
import datetime

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

class TJAEditor:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tja_editor_config.json")

    MAX_UNDO = 100
    MAX_RECENT = 10

    DAN_ITEMS = ["EXAM1", "EXAM2", "EXAM3", "EXAM4"]
    DAN_DEFAULTS = [
        ("魂ゲージ", "～以上", "98", "100"),
        ("良の数", "～以上", "0", "0"),
        ("不可の数", "～未満", "0", "0"),
        ("スコア", "～以上", "0", "0")
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("TJA Editor - 新規ファイル")
        self.root.geometry("1000x750")
        self.root.resizable(False, False)
        self.current_file = None
        self.current_encoding = 'cp932'
        self.dark_mode = False
        self.last_folder = os.path.expanduser("~")
        self.recent_files = []
        self.song_paths = []
        self.song_course_values = {}
        self.song_levels = {}
        self.song_genres = {}
        self.song_scoreinit = {}
        self.song_scorediff = {}
        self.song_courses_temp = {}
        self.dan_window = None
        self.search_window = None
        # フォント設定(全環境対応)
        if "BIZ UDPゴシック" in tkfont.families():
            self.main_font = ("BIZ UDPゴシック", 16)
        elif "Yu Gothic UI" in tkfont.families():
            self.main_font = ("Yu Gothic UI", 16)
        else:
            self.main_font = ("Consolas", 14)
        self._create_menu()
        self._create_widgets()
        self._bind_events()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.song_settings_frame = None
        self.load_config() 
        self.text.bind("<Return>", self.smart_comma_on_enter)
        # 行番号のクリックイベント
        self.linenumbers.bind("<Button-1>", self.on_linenumber_click)
        self.linenumbers.bind("<B1-Motion>", self.on_linenumber_drag)
        self.popup = tk.Menu(self.text, tearoff=0)
    
        self.popup.add_command(label="元に戻す          Ctrl+Z", command=lambda: self.text.event_generate("<<Undo>>"))
        self.popup.add_command(label="やり直す          Ctrl+Y", command=lambda: self.text.event_generate("<<Redo>>"))
        self.popup.add_separator()
        self.popup.add_command(label="切り取り          Ctrl+X", command=lambda: self.text.event_generate("<<Cut>>"))
        self.popup.add_command(label="コピー            Ctrl+C", command=lambda: self.text.event_generate("<<Copy>>"))
        self.popup.add_command(label="貼り付け          Ctrl+V", command=lambda: self.text.event_generate("<<Paste>>"))
        self.popup.add_command(label="削除              Del",    command=lambda: self.text.event_generate("<<Clear>>"))
        self.popup.add_separator()
        self.popup.add_command(label="すべて選択        Ctrl+A", command=lambda: self.text.tag_add("sel", "1.0", "end"))
    
        def show_popup(event):
            try:
                self.popup.tk_popup(event.x_root, event.y_root)
            finally:
                self.popup.grab_release()
    
        self.text.bind("<Button-3>", show_popup)
        self.text.bind("<Control-Button-1>", show_popup)

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="開く", command=self.open_file, accelerator="Ctrl+O")
        filemenu.add_separator()
        recent_menu = tk.Menu(filemenu, tearoff=0)
        filemenu.add_cascade(label="最近使ったファイル", menu=recent_menu)
        self.recent_menu = recent_menu
        self.update_recent_menu()
        filemenu.add_command(label="上書き保存", command=self.save_file, accelerator="Ctrl+S")
        filemenu.add_command(label="名前を付けて保存", command=self.save_as_file, accelerator="Ctrl+Shift+S")
        filemenu.add_separator()
        filemenu.add_command(label="終了", command=self.on_closing)
        menubar.add_cascade(label="ファイル", menu=filemenu)
    
        editmenu = tk.Menu(menubar, tearoff=0)
        editmenu.add_command(label="検索", command=self.open_search, accelerator="Ctrl+F")
        menubar.add_cascade(label="編集", menu=editmenu)
    
        viewmenu = tk.Menu(menubar, tearoff=0)
        self.viewmenu = viewmenu  # メニューを保存
        viewmenu.add_command(label="ダークモードに切り替え", command=self.toggle_dark_mode, accelerator="Ctrl+D")
        # グリッド線の表示/非表示
        self.show_grid = tk.BooleanVar(value=False)
        viewmenu.add_checkbutton(label="配置グリッド線を表示", variable=self.show_grid, 
                                 command=self.toggle_grid_lines)
        menubar.add_cascade(label="表示", menu=viewmenu)
    
        headermenu = tk.Menu(menubar, tearoff=0)
        headermenu.add_command(label="TITLE:", command=lambda: self.insert_with_input("TITLE:", "曲名を入力"))
        headermenu.add_command(label="SUBTITLE:", command=lambda: self.insert_with_input("SUBTITLE:", "サブタイトルを入力"))
        headermenu.add_command(label="LEVEL:", command=lambda: self.insert_with_input("LEVEL:", "レベル (1-10)", "7"))
        headermenu.add_command(label="SCOREINIT:", command=lambda: self.insert_with_input("SCOREINIT:", "初期スコア", "1000"))
        headermenu.add_command(label="SCOREMODE:", command=lambda: self.insert_with_input("SCOREMODE:", "スコアモード (1 or 2)", "2"))
        headermenu.add_command(label="SCOREDIFF:", command=lambda: self.insert_with_input("SCOREDIFF:", "スコア差分", "100"))
        headermenu.add_command(label="WAVE: (OGGからBPM取得)", command=self.insert_wave_with_bpm)
        headermenu.add_command(label="OFFSET:", command=lambda: self.insert_with_input("OFFSET:", "オフセット(秒)", "0"))
        coursemenu = tk.Menu(headermenu, tearoff=0)
        for course in ["Easy", "Normal", "Hard", "Oni", "Edit"]:
            coursemenu.add_command(label=course, command=lambda c=course: self.insert_course_only(c))
        headermenu.add_cascade(label="COURSE:", menu=coursemenu)
        menubar.add_cascade(label="ヘッダー挿入", menu=headermenu)
    
        notemenu = tk.Menu(menubar, tearoff=0)
        measuremenu = tk.Menu(notemenu, tearoff=0)
        measuremenu.add_command(label="#START", command=lambda: self.insert_syntax("#START\n"))
        measuremenu.add_command(label="#END", command=lambda: self.insert_syntax("#END\n"))
        measuremenu.add_command(label="#MEASURE 4/4", command=self.insert_measure)
        notemenu.add_cascade(label="小節・開始/終了", menu=measuremenu)
        speedmenu = tk.Menu(notemenu, tearoff=0)
        speedmenu.add_command(label="#BPMCHANGE", command=lambda: self.insert_with_input("#BPMCHANGE ", "新しいBPM", "120"))
        speedmenu.add_command(label="#SCROLL", command=lambda: self.insert_with_input("#SCROLL ", "スクロール速度", "1.0"))
        speedmenu.add_command(label="#HBSCROLL", command=lambda: self.insert_with_input("#HBSCROLL ", "HBSCROLL速度", "1.0"))
        speedmenu.add_command(label="#DELAY", command=lambda: self.insert_with_input("#DELAY ", "遅延時間(秒)", "1.0"))
        notemenu.add_cascade(label="速度・BPM", menu=speedmenu)
        notemenu.add_command(label="#GOGOSTART", command=lambda: self.insert_syntax("#GOGOSTART\n"))
        notemenu.add_command(label="#GOGOEND", command=lambda: self.insert_syntax("#GOGOEND\n"))
        notemenu.add_command(label="#BRANCHSTART", command=self.insert_branchstart)
        notemenu.add_command(label="#BARLINEON",   command=lambda: self.insert_syntax("#BARLINEON\n"))
        notemenu.add_command(label="#BARLINEOFF",  command=lambda: self.insert_syntax("#BARLINEOFF\n"))
        notemenu.add_command(label="#SECTION",     command=lambda: self.insert_syntax("#SECTION\n"))
        notemenu.add_command(label="#N", command=lambda: self.insert_syntax("#N\n"))
        notemenu.add_command(label="#E", command=lambda: self.insert_syntax("#E\n"))
        notemenu.add_command(label="#M", command=lambda: self.insert_syntax("#M\n"))
        p1menu = tk.Menu(notemenu, tearoff=0)
        p1menu.add_command(label="#P1START", command=lambda: self.insert_syntax("#P1START\n"))
        p1menu.add_command(label="#P1END", command=lambda: self.insert_syntax("#P1END\n"))
        notemenu.add_cascade(label="P1譜面", menu=p1menu)
        p2menu = tk.Menu(notemenu, tearoff=0)
        p2menu.add_command(label="#P2START", command=lambda: self.insert_syntax("#P2START\n"))
        p2menu.add_command(label="#P2END", command=lambda: self.insert_syntax("#P2END\n"))
        notemenu.add_cascade(label="P2譜面", menu=p2menu)
        menubar.add_cascade(label="譜面コマンド", menu=notemenu)
    
        dojomenu = tk.Menu(menubar, tearoff=0)
        dojomenu.add_command(label="段位道場設定", command=self.open_dan_window)
        menubar.add_cascade(label="段位道場", menu=dojomenu)
        
        toolmenu = tk.Menu(menubar, tearoff=0)
        # ========== 音源・タイミング調整 ==========
        if PYDUB_AVAILABLE:
            toolmenu.add_command(label="OFFSET自動計測(WAV/OGG対応)", command=self.auto_measure_offset_ogg)
            toolmenu.add_command(label="OFFSET自動調節(波形表示+精密調整)", command=self.auto_adjust_offset)
        else:
            toolmenu.add_command(label="OFFSET自動計測(無効・pydub未導入)",command=lambda: messagebox.showwarning("機能無効", "pydub がインストールされていないため利用できません"))
            toolmenu.add_command(label="BPMカウンター(タップテンポ)", command=self.open_bpm_counter)
            toolmenu.add_command(label="OFFSET一括調整", command=self.open_offset_adjuster)
        toolmenu.add_separator()
        
        # ========== プレビュー・再生 ==========
        toolmenu.add_command(label="太鼓さん次郎でプレビュー再生", command=self.preview_play, accelerator="F5")
        toolmenu.add_command(label="太鼓さん次郎のパスを再設定...", command=self.reset_taikojiro_path)
        toolmenu.add_separator()
        # ========== 譜面分析・検証 ==========
        toolmenu.add_command(label="エラーチェック", command=self.check_errors, accelerator="Ctrl+Shift+E")
        toolmenu.add_command(label="TODO管理", command=self.open_todo_manager, accelerator="Ctrl+T")
        toolmenu.add_separator()
        
        # ========== ファイル管理・配布 ==========
        toolmenu.add_command(label="配布用ZIPを作成", 
                             command=self.create_distribution_zip,
                             accelerator="Ctrl+E")
        toolmenu.add_separator()
        toolmenu.add_command(label="バックアップフォルダを開く", command=self.open_backup_folder)
        toolmenu.add_command(label="バックアップ履歴を表示・復元", command=self.show_backup_history)
        toolmenu.add_command(label="バックアップ比較", command=self.open_backup_compare)
        menubar.add_cascade(label="ツール", menu=toolmenu)
        
        # ヘルプメニュー追加（最後に追加するのが自然）
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="バージョン情報", command=self.show_version)
        helpmenu.add_separator()
        helpmenu.add_command(label="このエディタについて", command=self.show_about)
        menubar.add_cascade(label="ヘルプ", menu=helpmenu)
        self.root.config(menu=menubar)

    def _create_widgets(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.linenumbers = tk.Canvas(main_frame, width=80, bg="white", highlightthickness=0)
        self.linenumbers.pack(side=tk.LEFT, fill=tk.Y)
    
        center_frame = tk.Frame(main_frame)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        
    
        count_frame = tk.Frame(center_frame, width=230, bg="#f0f0f0", relief="sunken", bd=2)
        count_frame.pack(side=tk.RIGHT, fill=tk.Y)
        count_frame.pack_propagate(False)
    
        self.count_frame = count_frame
    
        title_lbl = tk.Label(count_frame, text="■ 各難易度統計 ■", bg="#f0f0f0", 
                             font=("メイリオ", 11, "bold"), fg="#333333")
        title_lbl.pack(pady=(10, 5))
    
        self.count_text = tk.Text(count_frame, width=30, height=28,
                                  font=("Courier New", 11), 
                                  bg="#f0f0f0", fg="#000000",
                                  relief="flat", state="disabled",
                                  wrap="none")
        self.count_text.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)
    
        # ========== 左側のメインエディタ ==========
        text_container = tk.Frame(center_frame)
        text_container.pack(fill=tk.BOTH, expand=True)
        
        # 横スクロールバー用のフレーム
        hscroll_frame = tk.Frame(center_frame)
        hscroll_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        hscroll = ttk.Scrollbar(hscroll_frame, orient=tk.HORIZONTAL)
        hscroll.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 縦スクロールバーの幅分の余白(右下の角を空ける)
        corner_spacer = tk.Frame(hscroll_frame, width=15)
        corner_spacer.pack(side=tk.RIGHT)
        
        vscroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text = tk.Text(text_container, yscrollcommand=vscroll.set, xscrollcommand=hscroll.set,
                            undo=True, maxundo=self.MAX_UNDO, font=self.main_font, wrap=tk.NONE)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        vscroll.config(command=self.text.yview)
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        hscroll.config(command=self.text.xview)
        vscroll.config(command=self.sync_scroll)  # この行を変更
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        hscroll.config(command=self.text.xview)
        
        # ========== ステータスバー ==========
        self.statusbar = tk.Label(self.root, text="準備完了", relief=tk.SUNKEN, anchor="w", font=("MS Gothic", 10))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    
        self.text.tag_configure("search", background="yellow", foreground="black")
        
        # ========== 構文ハイライト設定 ==========
        # ヘッダー行（青）
        self.text.tag_configure("header", foreground="#0066cc", font=(self.main_font[0], self.main_font[1], "bold"))
        # コメント（グレー）
        self.text.tag_configure("comment", foreground="#6a9955", font=(self.main_font[0], self.main_font[1], "italic"))
        # コマンド行（紫）
        self.text.tag_configure("command", foreground="#c586c0", font=(self.main_font[0], self.main_font[1], "bold"))
        # エラー行（赤下線）
        self.text.tag_configure("error", foreground="#ff0000", underline=True)
        # TODO（黄色背景）
        self.text.tag_configure("todo", background="#fff9c4", foreground="#000000")
        # 譜面行（通常のまま）
        # 数値（オレンジ）
        self.text.tag_configure("number", foreground="#b5cea8")
        
        # 起動後に1回だけ行番号更新
        self.root.after(100, self.update_linenumbers)

    def _bind_events(self):
        self.root.bind_all("<Control-o>", lambda e: self.open_file())
        self.root.bind_all("<Control-s>", lambda e: self.save_file())
        self.root.bind_all("<Control-Shift-s>", lambda e: self.save_as_file())
        self.root.bind_all("<Control-f>", lambda e: self.open_search())
        self.root.bind_all("<Control-d>", lambda e: self.toggle_dark_mode())
        self.root.bind_all("<Control-e>", lambda e: self.check_syntax_errors())
        self.root.bind_all("<Control-Shift-P>", lambda e: self.open_command_palette())
        self.root.bind("<F5>", lambda event: self.preview_play())
        self.root.bind_all("<Control-e>", lambda e: self.create_distribution_zip())
        self.root.bind_all("<Control-Shift-E>", lambda e: self.check_errors())
        self.root.bind_all("<Control-t>", lambda e: self.open_todo_manager())
        
        # キー入力中もリアルタイムで行番号を更新
        self.text.bind("<Key>", lambda e: self.root.after_idle(self.update_linenumbers))
        self.text.bind("<KeyRelease>", lambda e: (self.root.after_idle(self.update_all), self.on_text_change()))
        
        self.text.bind("<ButtonRelease>", lambda e: self.root.after_idle(self.update_linenumbers))
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        
        # マウスホイール
        self.text.bind("<MouseWheel>", lambda e: (
            self.text.yview_scroll(-int(e.delta/120), "units"),
            self.update_linenumbers()
        ) or "break")
        self.text.bind("<Shift-MouseWheel>", lambda e: self.text.xview_scroll(-int(e.delta/120), "units") or "break")
        self.statusbar.config(text="準備完了 | F5: プレビュー再生")
        self.text.bind("<<Modified>>", self._on_text_modified)

    def load_config(self):
        """起動時に設定を読み込む（recent_filesも確実に反映）"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.recent_files = config.get("recent_files", [])
                    self.last_folder = config.get("last_folder", os.path.expanduser("~"))
                    self.dark_mode = config.get("dark_mode", False)
                    
                    self.root.after(100, self.update_recent_menu)
                    self.root.after(150, self.apply_dark_mode)
                    self.syntax_theme_name = config.get("syntax_theme", None)
    
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                self.recent_files = []
        
    def save_config(self):
        """終了時に設定を保存"""
        config = {
            "recent_files": self.recent_files,
            "dark_mode": self.dark_mode,
            "last_folder": self.last_folder,
            "taikojiro_path": self.get_taikojiro_path(),
        }
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定保存エラー: {e}")    
    
    def apply_dark_mode(self):
        """ダークモードの見た目を強制的に適用（起動時用）"""
        if self.dark_mode:
            self.toggle_dark_mode(force=True)
        else:
            self.toggle_dark_mode(force=False)    
    
    def toggle_grid_lines(self):
        """グリッド線の表示/非表示を切り替え"""
        if self.show_grid.get():
            self.draw_grid_lines()
        else:
            self.clear_grid_lines()
    
    def clear_grid_lines(self):
        """グリッド線を完全にクリア"""
        # すべてのグリッド関連タグを削除
        grid_tags = ["grid_line_quarter", "grid_line_eighth", "grid_line_sixteenth"]
        
        for tag in grid_tags:
            # タグを完全に削除
            self.text.tag_remove(tag, "1.0", "end")
            
            # タグ設定をリセット（重要！）
            self.text.tag_configure(tag, background="")
        
        # Textウィジェットの更新を強制
        self.text.update_idletasks()
    
    def draw_grid_lines(self):
        """グリッド線を描画（コメント行対応版）"""
        self.clear_grid_lines()
        
        # BPMチェック
        bpm = self.get_current_bpm()
        if bpm is None:
            messagebox.showinfo("グリッド線", "BPM:が見つかりません。\nBPMを設定してください。")
            self.show_grid.set(False)
            return
        
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        
        in_chart = False
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            upper = stripped.upper()
            
            # 譜面開始
            if upper in ["#START", "#P1START", "#P2START"]:
                in_chart = True
                continue
            
            # 譜面終了
            if upper in ["#END", "#P1END", "#P2END"]:
                in_chart = False
                continue
            
            # 譜面内かつ譜面行のみにグリッド線を表示
            if in_chart:
                # 行全体がコメントの場合はスキップ
                if not stripped or stripped.startswith("//") or stripped.startswith(";"):
                    continue
                
                # 行の先頭が#で始まる命令文もスキップ
                if stripped.startswith("#"):
                    continue
                
                # 行内コメントを除去して譜面部分のみを取得
                # "//" または ";" 以降を除去
                chart_part = line
                for comment_marker in ["//", ";"]:
                    if comment_marker in chart_part:
                        chart_part = chart_part.split(comment_marker)[0]
                
                # コメント除去後の文字列をチェック
                chart_part_stripped = chart_part.strip()
                if not chart_part_stripped:
                    continue  # コメントのみの行
                
                # カンマを除いた文字列から数字をチェック
                clean_line = chart_part.replace(",", "").replace(" ", "").replace("\t", "")
                note_count = len([c for c in clean_line if c in "0123456789"])
                
                if note_count > 0:
                    # この小節の長さを計算
                    line_length = len(clean_line)
                    
                    # 16分音符単位でグリッドを描画（4/4拍子を仮定）
                    # 1小節最大16文字（16分音符×16）
                    for pos in range(0, line_length, 4):  # 4文字ごと（4分音符単位）
                        if pos < len(chart_part):
                            start_idx = f"{i}.{pos}"
                            end_idx = f"{i}.{pos+1}"
                            
                            # 4分音符の位置（濃いマーカー）
                            if pos % 16 == 0:
                                self.text.tag_add("grid_line_quarter", start_idx, end_idx)
                            # 8分音符の位置（中間マーカー）
                            elif pos % 8 == 0:
                                self.text.tag_add("grid_line_eighth", start_idx, end_idx)
                            # 16分音符の位置（薄いマーカー）
                            else:
                                self.text.tag_add("grid_line_sixteenth", start_idx, end_idx)
        
        # グリッド線のスタイル設定
        self.configure_grid_styles()
    
    def configure_grid_styles(self):
        """グリッド線のスタイルを設定"""
        if self.dark_mode:
            # ダークモード
            self.text.tag_configure("grid_line_quarter", background="#3a3a3a")
            self.text.tag_configure("grid_line_eighth", background="#2d2d2d")
            self.text.tag_configure("grid_line_sixteenth", background="#252525")
        else:
            # ライトモード
            self.text.tag_configure("grid_line_quarter", background="#e0e0e0")
            self.text.tag_configure("grid_line_eighth", background="#eeeeee")
            self.text.tag_configure("grid_line_sixteenth", background="#f5f5f5")
    
    def get_current_bpm(self):
        """現在のBPMを取得（コース対応版）"""
        content = self.text.get("1.0", tk.END)
        
        # カーソル位置のコースを特定
        cursor_line = int(self.text.index(tk.INSERT).split('.')[0])
        lines = content.splitlines()
        
        current_bpm = None
        current_course = None
        target_course = None
        
        for i, line in enumerate(lines):
            stripped = line.strip().upper()
            
            # COURSE検出
            if stripped.startswith("COURSE:"):
                current_course = stripped[7:].strip()
            
            # BPM検出
            if stripped.startswith("BPM:"):
                try:
                    current_bpm = float(stripped[4:].strip())
                except:
                    current_bpm = None
            
            # カーソルがこのコース内かチェック
            if i + 1 == cursor_line:
                target_course = current_course
                break
        
        return current_bpm  # 簡易版：最後に見つけたBPMを返す
                
    def open_backup_folder(self):
        """自動バックアップフォルダをエクスプローラーで開く"""
        if not self.current_file:
            messagebox.showwarning("未保存", "ファイルを保存してください")
            return
        
        backup_dir = os.path.join(os.path.dirname(self.current_file), ".backup")
        
        if not os.path.exists(backup_dir):
            messagebox.showinfo("バックアップなし", 
                               "まだバックアップが作成されていません")
            return
        
        # OS別でフォルダを開く
        if os.name == "nt":  # Windows
            os.startfile(backup_dir)
        elif os.name == "posix":  # macOS/Linux
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", backup_dir])

    def open_backup_compare(self):
        """バックアップ比較ツールを開く"""
        if not self.current_file:
            messagebox.showwarning("未保存", "ファイルを保存してください")
            return
        
        backup_dir = os.path.join(os.path.dirname(self.current_file), ".backup")
        if not os.path.exists(backup_dir):
            messagebox.showinfo("バックアップなし", 
                               "まだバックアップが作成されていません")
            return
        
        # 現在のファイル名に関連するバックアップを取得
        current_basename = os.path.basename(self.current_file)
        backups = []
        for fname in os.listdir(backup_dir):
            if fname.endswith(current_basename):
                full_path = os.path.join(backup_dir, fname)
                timestamp_str = fname.split("_")[0] + "_" + fname.split("_")[1]
                try:
                    dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                    display_time = dt.strftime("%Y年%m月%d日 %H:%M:%S")
                    backups.append((display_time, full_path))
                except:
                    pass
        
        if not backups:
            messagebox.showinfo("バックアップなし", 
                               f"{current_basename} のバックアップはありません")
            return
        
        backups.sort(reverse=True)
        
        # 比較ウィンドウ
        if hasattr(self, 'compare_window') and self.compare_window and self.compare_window.winfo_exists():
            self.compare_window.lift()
            return
        
        self.compare_window = Toplevel(self.root)
        self.compare_window.title(f"バックアップ比較 - {current_basename}")
        self.compare_window.geometry("1200x700")
        self.compare_window.transient(self.root)
        
        # 上部: バックアップ選択
        top_frame = Frame(self.compare_window)
        top_frame.pack(fill="x", padx=10, pady=10)
        
        Label(top_frame, text="比較するバックアップを選択:", 
              font=("メイリオ", 11, "bold")).pack(anchor="w")
        
        select_frame = Frame(top_frame)
        select_frame.pack(fill="x", pady=5)
        
        Label(select_frame, text="バージョン1:", font=("メイリオ", 10)).grid(row=0, column=0, padx=5)
        self.backup1_combo = ttk.Combobox(select_frame, values=[b[0] for b in backups], 
                                         state="readonly", width=30, font=("メイリオ", 9))
        self.backup1_combo.grid(row=0, column=1, padx=5)
        if len(backups) >= 2:
            self.backup1_combo.current(1)
        elif len(backups) >= 1:
            self.backup1_combo.current(0)
        
        Label(select_frame, text="バージョン2:", font=("メイリオ", 10)).grid(row=0, column=2, padx=5)
        self.backup2_combo = ttk.Combobox(select_frame, values=[b[0] for b in backups], 
                                         state="readonly", width=30, font=("メイリオ", 9))
        self.backup2_combo.grid(row=0, column=3, padx=5)
        if len(backups) >= 1:
            self.backup2_combo.current(0)
        
        Button(select_frame, text="比較実行", command=lambda: self.execute_compare(backups),
               font=("メイリオ", 10), width=12).grid(row=0, column=4, padx=10)
        
        # 中央: 比較結果表示エリア
        result_frame = Frame(self.compare_window)
        result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 左側: バージョン1
        left_frame = Frame(result_frame)
        left_frame.pack(side="left", fill="both", expand=True)
        
        self.left_label = Label(left_frame, text="バージョン1", 
                               font=("メイリオ", 10, "bold"), bg="#e3f2fd")
        self.left_label.pack(fill="x")
        
        left_scroll = Scrollbar(left_frame)
        left_scroll.pack(side="right", fill="y")
        
        self.left_text = tk.Text(left_frame, yscrollcommand=left_scroll.set,
                                font=("Courier New", 9), wrap="none", state="disabled")
        self.left_text.pack(side="left", fill="both", expand=True)
        left_scroll.config(command=self.left_text.yview)
        
        # 右側: バージョン2
        right_frame = Frame(result_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        self.right_label = Label(right_frame, text="バージョン2", 
                                font=("メイリオ", 10, "bold"), bg="#f3e5f5")
        self.right_label.pack(fill="x")
        
        right_scroll = Scrollbar(right_frame)
        right_scroll.pack(side="right", fill="y")
        
        self.right_text = tk.Text(right_frame, yscrollcommand=right_scroll.set,
                                 font=("Courier New", 9), wrap="none", state="disabled")
        self.right_text.pack(side="left", fill="both", expand=True)
        right_scroll.config(command=self.right_text.yview)
        
        # 色の設定
        self.left_text.tag_configure("added", background="#c8e6c9")
        self.left_text.tag_configure("removed", background="#ffcdd2")
        self.left_text.tag_configure("changed", background="#fff9c4")
        
        self.right_text.tag_configure("added", background="#c8e6c9")
        self.right_text.tag_configure("removed", background="#ffcdd2")
        self.right_text.tag_configure("changed", background="#fff9c4")
        
        # 下部: 統計情報
        stats_frame = Frame(self.compare_window)
        stats_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.stats_label = Label(stats_frame, text="比較を実行してください", 
                                font=("メイリオ", 9), fg="gray")
        self.stats_label.pack()
        
        # 保存用
        self.backup_list = backups
        
        # 閉じるボタン
        Button(self.compare_window, text="閉じる", command=self.compare_window.destroy,
               width=15, font=("メイリオ", 10)).pack(pady=10)
    
    def execute_compare(self, backups):
        """バックアップの比較を実行"""
        idx1 = self.backup1_combo.current()
        idx2 = self.backup2_combo.current()
        
        if idx1 == -1 or idx2 == -1:
            messagebox.showwarning("未選択", "両方のバージョンを選択してください", 
                                  parent=self.compare_window)
            return
        
        if idx1 == idx2:
            messagebox.showwarning("同一選択", "異なるバージョンを選択してください", 
                                  parent=self.compare_window)
            return
        
        path1 = backups[idx1][1]
        path2 = backups[idx2][1]
        
        try:
            with open(path1, 'r', encoding=self.current_encoding, errors='replace') as f:
                content1 = f.read().splitlines()
            with open(path2, 'r', encoding=self.current_encoding, errors='replace') as f:
                content2 = f.read().splitlines()
        except Exception as e:
            messagebox.showerror("読み込みエラー", f"ファイルの読み込みに失敗しました\n{e}", 
                                parent=self.compare_window)
            return
        
        # 差分計算
        import difflib
        diff = list(difflib.unified_diff(content1, content2, lineterm=''))
        
        # 表示
        self.display_diff(content1, content2, diff)
    
    def display_diff(self, content1, content2, diff):
        """差分を表示"""
        self.left_text.config(state="normal")
        self.right_text.config(state="normal")
        
        self.left_text.delete("1.0", tk.END)
        self.right_text.delete("1.0", tk.END)
        
        # 簡易的な差分表示
        max_lines = max(len(content1), len(content2))
        
        added = 0
        removed = 0
        changed = 0
        
        for i in range(max_lines):
            line1 = content1[i] if i < len(content1) else ""
            line2 = content2[i] if i < len(content2) else ""
            
            if line1 == line2:
                # 同じ行
                self.left_text.insert("end", line1 + "\n")
                self.right_text.insert("end", line2 + "\n")
            elif line1 and not line2:
                # 左だけにある（削除された）
                self.left_text.insert("end", line1 + "\n", "removed")
                self.right_text.insert("end", "\n")
                removed += 1
            elif not line1 and line2:
                # 右だけにある（追加された）
                self.left_text.insert("end", "\n")
                self.right_text.insert("end", line2 + "\n", "added")
                added += 1
            else:
                # 両方あるが内容が違う（変更）
                self.left_text.insert("end", line1 + "\n", "changed")
                self.right_text.insert("end", line2 + "\n", "changed")
                changed += 1
        
        self.left_text.config(state="disabled")
        self.right_text.config(state="disabled")
        
        # 統計表示
        self.stats_label.config(
            text=f"追加: {added}行 / 削除: {removed}行 / 変更: {changed}行",
            fg="black"
        )

    def open_bpm_counter(self):
        """リアルタイムBPMカウンターウィンドウを開く"""
        if hasattr(self, 'bpm_window') and self.bpm_window and self.bpm_window.winfo_exists():
            self.bpm_window.lift()
            return
        
        self.bpm_window = Toplevel(self.root)
        self.bpm_window.title("BPMカウンター (タップテンポ)")
        self.bpm_window.geometry("500x400")
        self.bpm_window.resizable(False, False)
        self.bpm_window.transient(self.root)
        
        # タップ記録用
        self.tap_times = []
        self.bpm_result = 0
        
        # 説明ラベル
        Label(self.bpm_window, text="曲に合わせてスペースキーまたはボタンをタップ！", 
              font=("メイリオ", 12, "bold")).pack(pady=20)
        
        # BPM表示
        self.bpm_display = Label(self.bpm_window, text="0.0", 
                                font=("Arial", 72, "bold"), fg="#0066cc")
        self.bpm_display.pack(pady=20)
        
        Label(self.bpm_window, text="BPM", 
              font=("メイリオ", 14)).pack()
        
        # タップ回数表示
        self.tap_count_label = Label(self.bpm_window, text="タップ回数: 0", 
                                     font=("メイリオ", 11))
        self.tap_count_label.pack(pady=10)
        
        # タップボタン
        tap_btn = Button(self.bpm_window, text="TAP (Space)", 
                         command=self.on_tap, 
                         font=("メイリオ", 16, "bold"),
                         bg="#4CAF50", fg="white",
                         width=20, height=2)
        tap_btn.pack(pady=20)
        
        # ボタンフレーム
        btn_frame = Frame(self.bpm_window)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="リセット", command=self.reset_bpm, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="TJAに挿入", command=self.insert_bpm_to_tja, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="閉じる", command=self.bpm_window.destroy, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        
        # スペースキーバインド
        self.bpm_window.bind("<space>", lambda e: self.on_tap())
        self.bpm_window.focus_set()

    def on_tap(self):
        """タップ時の処理"""
        import time
        current_time = time.time()
        self.tap_times.append(current_time)
        
        # 古いタップ（5秒以上前）を削除
        self.tap_times = [t for t in self.tap_times if current_time - t < 5.0]
        
        # タップ回数更新
        self.tap_count_label.config(text=f"タップ回数: {len(self.tap_times)}")
        
        # 2回以上タップがあればBPMを計算
        if len(self.tap_times) >= 2:
            intervals = []
            for i in range(1, len(self.tap_times)):
                intervals.append(self.tap_times[i] - self.tap_times[i-1])
            
            # 平均間隔からBPMを計算
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 0:
                self.bpm_result = 60.0 / avg_interval
                self.bpm_display.config(text=f"{self.bpm_result:.1f}")
        
        # タップボタンのフィードバック（色を一瞬変える）
        if hasattr(self, 'bpm_window') and self.bpm_window.winfo_exists():
            for widget in self.bpm_window.winfo_children():
                if isinstance(widget, Button) and "TAP" in widget.cget("text"):
                    original_bg = widget.cget("bg")
                    widget.config(bg="#45a049")
                    self.bpm_window.after(100, lambda: widget.config(bg=original_bg))

    def reset_bpm(self):
        """BPMカウンターをリセット"""
        self.tap_times = []
        self.bpm_result = 0
        self.bpm_display.config(text="0.0")
        self.tap_count_label.config(text="タップ回数: 0")
    
    def insert_bpm_to_tja(self):
        """計算したBPMをTJAに挿入"""
        if self.bpm_result == 0:
            messagebox.showwarning("BPM未計測", "先にタップしてBPMを計測してください。", 
                                  parent=self.bpm_window)
            return
        
        # 小数点以下を丸めるか確認
        rounded_bpm = round(self.bpm_result, 2)
        
        response = messagebox.askyesno(
            "BPM挿入確認",
            f"計測されたBPM: {self.bpm_result:.2f}\n\n"
            f"以下の値をTJAに挿入しますか？\n"
            f"BPM:{rounded_bpm}",
            parent=self.bpm_window
        )
        
        if response:
            self.text.insert(tk.INSERT, f"BPM:{rounded_bpm}\n")
            self.text.see(tk.INSERT)
            self.bpm_window.destroy()
            messagebox.showinfo("挿入完了", f"BPM:{rounded_bpm} を挿入しました！")
        
    def auto_adjust_offset(self):
        wave_path = self.find_wave_path()
        if not wave_path or not os.path.exists(wave_path):
            messagebox.showwarning("エラー", "音声ファイルが見つかりません")
            return
    
        try:
            # 音声読み込み（モノラル・44.1kHz統一）
            audio = AudioSegment.from_file(wave_path).set_channels(1).set_frame_rate(44100)
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            sr = audio.frame_rate
    
            # 最初の5秒間だけ解析
            limit = min(len(samples), sr * 5)
            segment = samples[:limit]
    
            # 閾値 = 平均 + 3σ（静寂部を無視して最初の音を確実に捉える）
            threshold = np.mean(np.abs(segment)) + 3 * np.std(np.abs(segment))
            hits = np.where(np.abs(segment) > threshold)[0]
    
            if len(hits) == 0:
                messagebox.showinfo("検出不可", "最初のドン音を検出できませんでした")
                return
    
            detected_sec = hits[0] / sr
            suggested_offset = round(-detected_sec, 3)
    
            # 波形表示
            time = np.arange(limit) / sr
            plt.figure(figsize=(10, 4))
            plt.plot(time, segment, color="blue", linewidth=0.8)
            plt.axvline(detected_sec, color="red", linestyle="--", linewidth=2, label=f"検出位置 {detected_sec:.3f}s")
            plt.axhline(threshold, color="orange", linestyle=":", label="閾値")
            plt.axhline(-threshold, color="orange", linestyle=":")
            plt.title(f"OFFSET自動調整 - {os.path.basename(wave_path)}")
            plt.xlabel("時間 (秒)")
            plt.ylabel("振幅")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()
    
            # ユーザー入力（キャンセル対応＋安全な変換）
            user_input = simpledialog.askstring(
                "OFFSET最終調整",
                f"自動検出値: {detected_sec:.3f} 秒\n"
                f"推奨OFFSET: {suggested_offset}\n\n"
                "最終的なOFFSET値を入力してください（例: -0.123）\n"
                "（空欄 = 推奨値を採用 / キャンセル = 中止）",
                initialvalue=str(suggested_offset)
            )
    
            # ← ここからが完全修正部分
            if user_input is None:  # キャンセルボタン押された
                return
            if user_input.strip() == "":  # 空欄なら自動値を使う
                final_offset = suggested_offset
            else:
                try:
                    final_offset = round(float(user_input.strip()), 3)
                except ValueError:
                    messagebox.showerror("入力エラー", "数値を入力してください")
                    return
    
            # 最終確認（ズレが大きすぎる場合は警告）
            if abs(final_offset + detected_sec) > 0.020:  # 20ms以上ズレたら要注意
                if not messagebox.askyesno(
                    "確認",
                    f"検出値との差が {abs(final_offset + detected_sec):.3f}秒 あります。\n"
                    "それでも適用しますか？"
                ):
                    return
    
            # 適用
            self._apply_offset_to_tja(final_offset)
            messagebox.showinfo("完了", f"OFFSET を {final_offset} に設定しました！")
    
        except Exception as e:
            messagebox.showerror("解析エラー", f"音声解析中にエラーが発生しました:\n{e}")

    def create_distribution_zip(self):
        """ツール → 配布用ZIPを作成（readmeなし・画像も自動収集）"""
        if not self.current_file:
            messagebox.showwarning("未保存", "先にTJAファイルを保存してください。")
            return

        tja_path = self.current_file
        tja_dir = os.path.dirname(tja_path)
        tja_name = os.path.basename(tja_path)
        song_title = os.path.splitext(tja_name)[0]

        # WAVEファイルを探す（既存のfind_wave_pathを使用）
        wave_path = self.find_wave_path()
        if not wave_path or not os.path.exists(wave_path):
            messagebox.showwarning("音声ファイル未検出", 
                                 "WAVE: で指定された音声ファイルが見つかりません。\n"
                                 "TJAと同じフォルダに配置してください。")
            return
        wave_name = os.path.basename(wave_path)

        # 画像ファイルを自動収集（png/jpg/jpeg/gif/bmp）
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        extra_files = []
        for f in os.listdir(tja_dir):
            if f.lower().endswith(image_exts):
                full_path = os.path.join(tja_dir, f)
                if os.path.isfile(full_path) and f.lower() not in [tja_name.lower(), wave_name.lower()]:
                    extra_files.append(full_path)

        # 保存先を選択
        zip_path = filedialog.asksaveasfilename(
            title="配布用ZIPの保存場所とファイル名を指定",
            initialdir=tja_dir,
            initialfile=f"{song_title}.zip",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")]
        )
        if not zip_path:
            return  # キャンセル

        try:
            import zipfile
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(tja_path, arcname=tja_name)
                zf.write(wave_path, arcname=wave_name)
                for img_path in extra_files:
                    zf.write(img_path, arcname=os.path.basename(img_path))

            # 完了メッセージ
            file_list = f"・{tja_name}\n・{wave_name}"
            if extra_files:
                file_list += "\n・" + "\n・".join(os.path.basename(p) for p in extra_files)
            else:
                file_list += "\n（画像ファイルは検出されませんでした）"

            messagebox.showinfo(
                "配布用ZIP作成完了",
                f"以下のファイルを含むZIPを作成しました。\n\n"
                f"{os.path.basename(zip_path)}\n\n"
                f"{file_list}\n\n"
                f"このままアップロード可能です。"
            )

            # Windowsなら保存フォルダを開く
            if os.name == "nt":
                os.startfile(os.path.dirname(zip_path))

        except Exception as e:
            messagebox.showerror("ZIP作成エラー", f"ZIPの作成に失敗しました。\n\n{e}")
    
    def find_wave_path(self):
        """TJA内の WAVE: 行から音声ファイルパスを返す（同じフォルダ優先）"""
        content = self.text.get("1.0", tk.END)
        match = re.search(r"^WAVE:\s*([^\r\n#;\"']+)", content, re.MULTILINE | re.IGNORECASE)
        if not match:
            return None
        
        wave_name = match.group(1).strip().strip('"\'')
        
        # 1. TJAと同じフォルダにあるか
        if self.current_file:
            candidate = os.path.join(os.path.dirname(self.current_file), wave_name)
            if os.path.exists(candidate):
                return candidate
        
        # 2. 絶対パスならそのまま
        if os.path.isabs(wave_name) and os.path.exists(wave_name):
            return wave_name
        
        # 3. カレントフォルダ
        candidate = os.path.join(os.getcwd(), wave_name)
        if os.path.exists(candidate):
            return candidate
        
        # 見つからなかったら相対パスを返す（エラー表示用）
        if self.current_file:
            return os.path.join(os.path.dirname(self.current_file), wave_name)
        return wave_name
    
    def _apply_offset_to_tja(self, offset_value):
        """共通のOFFSET書き込み処理（再利用可能）"""
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        new_lines = []
        written = False
        for line in lines:
            if line.strip().upper().startswith("OFFSET:"):
                new_lines.append(f"OFFSET:{offset_value}")
                written = True
            else:
                new_lines.append(line)
        if not written:
            new_lines.insert(0, f"OFFSET:{offset_value}")

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", "\n".join(new_lines) + "\n")
        messagebox.showinfo("完了", f"OFFSET を {offset_value} に設定しました！\nF5で確認してください")
        
    def smart_comma_on_enter(self, event=None):
            """Enterキーを押したときに、譜面行の末尾に自動でカンマを付ける"""
            try:
                # 現在のカーソル位置
                cursor_pos = self.text.index("insert")
                line_start = f"{cursor_pos.split('.')[0]}.0"
                line_end   = f"{cursor_pos.split('.')[0]}.end"
                current_line_text = self.text.get(line_start, line_end)
    
                # 1. ヘッダー部分(#STARTより前) or #END以降なら何もしない
                text_before_cursor = self.text.get("1.0", cursor_pos)
                if "#START" not in text_before_cursor or "#END" in text_before_cursor:
                    return None  # 標準の改行に任せる
    
                # 2. 現在の行が譜面行か判定(1~8のどれかを含むか)
                stripped = current_line_text.rstrip()
                if not any(c in "12345678" for c in stripped):
                    return None  # 譜面じゃない行は普通に改行
    
                # 3. #で始まる命令文は自動カンマ挿入しない
                if stripped.lstrip().startswith("#"):
                    return None  # 命令文は標準の改行
    
                # 4. コメント行(//または;で始まる)は自動カンマ挿入しない
                if stripped.lstrip().startswith("//") or stripped.lstrip().startswith(";"):
                    return None  # コメント行は標準の改行
    
                # 5. 既にカンマがある or 空行なら何もしない
                if stripped.endswith(",") or not stripped:
                    return None
    
                # 6. カンマを自動挿入
                self.text.insert(line_end, ",")
    
                # 7. 少し待ってから改行(カンマが見えるようにしてから改行)
                self.text.after(10, lambda: self.text.insert("insert", "\n"))
    
                # 標準のEnter動作はキャンセル
                return "break"
    
            except Exception as e:
                # 万が一のエラーでもクラッシュしないように
                print(f"[SmartComma] Error: {e}")
                return None
        
    def reset_taikojiro_path(self):
        """メニューからいつでも太鼓さん次郎のパスを再設定可能"""
        if messagebox.askyesno(
            "パス再設定",
            "太鼓さん次郎の実行ファイル（Taikojiro.exe）を再度選択しますか？\n"
            "（現在の設定を上書きします）"
        ):
            path = filedialog.askopenfilename(
                title="太鼓さん次郎の実行ファイルを選択",
                filetypes=[("実行ファイル", "Taikojiro.exe"), ("すべてのファイル", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            if path:
                self.set_taikojiro_path(path)
                messagebox.showinfo("設定完了", f"新しいパスを登録しました！\n{os.path.basename(path)}")
            else:
                messagebox.showinfo("キャンセル", "変更をキャンセルしました")
    
    def update_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        valid_files = []
        for path in self.recent_files:
            if os.path.exists(path):
                valid_files.append(path)
                display_name = os.path.basename(path)
                if len(display_name) > 40:
                    display_name = "…" + display_name[-38:]
                # ← 正しい書き方（クロージャ対策も完璧）
                self.recent_menu.add_command(
                    label=f"{len(valid_files)}. {display_name}",
                    command=lambda p=path: self.open_file_path(p)
                )
        self.recent_files = valid_files
    
        if valid_files:
            self.recent_menu.add_separator()
            self.recent_menu.add_command(label="履歴をクリア", command=self.clear_recent_files)
        else:
            self.recent_menu.add_command(label="(履歴なし)", state="disabled")

    def clear_recent_files(self):
        """最近使ったファイル一覧をクリア（メニュー＋設定ファイル両方）"""
        if messagebox.askyesno("確認", "最近使ったファイルの履歴をすべて削除しますか？"):
            self.recent_files = []
            self.update_recent_menu()
            self.save_config()  # ← これが抜けていた！
            messagebox.showinfo("完了", "最近使ったファイルの履歴をクリアしました")

    def open_file_path(self, path):
        """最近使ったファイルから開く用（パスを直接渡す）"""
        if os.path.exists(path):
            self.open_file(path)   # ← ここは path をそのまま渡す
        else:
            messagebox.showwarning("ファイルが見つかりません", 
                                    f"次のファイルは存在しません:\n{path}\n\n履歴から削除します。")
            if path in self.recent_files:
                self.recent_files.remove(path)
            self.update_recent_menu()
            self.save_config()

    def sync_scroll(self, *args):
        """縦スクロールバーとテキスト、行番号を同期"""
        self.text.yview(*args)
        self.update_linenumbers()

    def _on_text_modified(self, event=None):
        self.text.edit_modified(False)
        self.update_linenumbers()

    def toggle_dark_mode(self, force=None):
        """
        force=None  : 通常のトグル動作
        force=True  : 強制ダークモード
        force=False : 強制ライトモード
        """
        if force is not None:
            self.dark_mode = force
        else:
            self.dark_mode = not self.dark_mode
        
        if self.dark_mode:
            # ダークモードカラー
            bg, fg, ins, sel = "#1e1e1e", "#d4d4d4", "#d4d4d4", "#264f78"
            linenum_bg = "#1e1e1e"
            status_bg, status_fg = "#2d2d30", "#d4d4d4"
            count_bg, count_fg = "#2b2b2b", "#ffffff"
            
            # 構文ハイライト色（ダークモード）
            header_fg = "#4fc3f7"
            comment_fg = "#6a9955"
            command_fg = "#c586c0"
            error_fg = "#f44336"
            todo_bg = "#5a5a3c"
            number_fg = "#b5cea8"
            
            # グリッド線色（ダークモード）
            grid_quarter = "#3a3a3a"
            grid_eighth = "#2d2d2d"
            grid_sixteenth = "#252525"
        else:
            # ライトモードカラー
            bg, fg, ins, sel = "white", "black", "black", "lightblue"
            linenum_bg = "white"
            status_bg, status_fg = "SystemButtonFace", "black"
            count_bg, count_fg = "#f0f0f0", "#000000"
            
            # 構文ハイライト色（ライトモード）
            header_fg = "#0066cc"
            comment_fg = "#6a9955"
            command_fg = "#c586c0"
            error_fg = "#ff0000"
            todo_bg = "#fff9c4"
            number_fg = "#098658"
            
            # グリッド線色（ライトモード）
            grid_quarter = "#e0e0e0"
            grid_eighth = "#eeeeee"
            grid_sixteenth = "#f5f5f5"
        
        # ====== 1. メインエディタ ======
        self.text.config(bg=bg, fg=fg, insertbackground=ins, selectbackground=sel)
        
        # ====== 2. 行番号エリア ======
        self.linenumbers.config(bg=linenum_bg)
        
        # ====== 3. ステータスバー ======
        self.statusbar.config(bg=status_bg, fg=status_fg)
        
        # ====== 4. 統計欄 ======
        self.count_frame.config(bg=count_bg)
        self.count_text.config(bg=count_bg, fg=count_fg)
        # 統計欄内のラベルも更新
        for widget in self.count_frame.winfo_children():
            if isinstance(widget, (tk.Label, tk.Frame)):
                widget.config(bg=count_bg, fg=count_fg)
            elif isinstance(widget, tk.Text):
                widget.config(bg=count_bg, fg=count_fg)
        
        # ====== 5. スクロールバースタイル ======
        style = ttk.Style()
        if self.dark_mode:
            style.theme_use('clam')
            style.configure("Vertical.TScrollbar", 
                           background="#3c3c3c", 
                           troughcolor="#1e1e1e", 
                           arrowcolor="#d4d4d4",
                           bordercolor="#1e1e1e")
            style.configure("Horizontal.TScrollbar", 
                           background="#3c3c3c", 
                           troughcolor="#1e1e1e", 
                           arrowcolor="#d4d4d4",
                           bordercolor="#1e1e1e")
        else:
            style.theme_use('default')
            style.configure("Vertical.TScrollbar", 
                           background="#c0c0c0", 
                           troughcolor="#f0f0f0")
            style.configure("Horizontal.TScrollbar", 
                           background="#c0c0c0", 
                           troughcolor="#f0f0f0")
        
        # ====== 6. 構文ハイライト色の更新 ======
        self.text.tag_configure("header", foreground=header_fg)
        self.text.tag_configure("comment", foreground=comment_fg)
        self.text.tag_configure("command", foreground=command_fg)
        self.text.tag_configure("error", foreground=error_fg)
        self.text.tag_configure("todo", background=todo_bg)
        self.text.tag_configure("number", foreground=number_fg)
        
        # ====== 7. グリッド線のスタイル更新 ======
        # グリッド線タグが存在する場合のみ設定
        grid_tags = ["grid_line_quarter", "grid_line_eighth", "grid_line_sixteenth"]
        for tag in grid_tags:
            try:
                # タグが使用されているかチェック
                ranges = self.text.tag_ranges(tag)
                if ranges:
                    # タグが存在するので色を更新
                    if tag == "grid_line_quarter":
                        self.text.tag_configure(tag, background=grid_quarter)
                    elif tag == "grid_line_eighth":
                        self.text.tag_configure(tag, background=grid_eighth)
                    elif tag == "grid_line_sixteenth":
                        self.text.tag_configure(tag, background=grid_sixteenth)
            except:
                pass
        
        # もしグリッド線が表示されているなら、スタイルを適用
        if hasattr(self, 'show_grid') and self.show_grid.get():
            self.text.tag_configure("grid_line_quarter", background=grid_quarter)
            self.text.tag_configure("grid_line_eighth", background=grid_eighth)
            self.text.tag_configure("grid_line_sixteenth", background=grid_sixteenth)
        
        # ====== 8. 行番号とステータスバーの更新 ======
        self.update_linenumbers()
        self.update_statusbar()
        
        # ====== 9. ポップアップメニューの色 ======
        if hasattr(self, 'popup'):
            if self.dark_mode:
                self.popup.config(bg="#2d2d30", fg="#d4d4d4", 
                                activebackground="#3e3e42", 
                                activeforeground="#ffffff")
            else:
                self.popup.config(bg="SystemMenu", fg="SystemMenuText",
                                activebackground="SystemHighlight",
                                activeforeground="SystemHighlightText")
        
        # ====== 10. 設定保存 ======
        self.save_config()
        
        # ====== 11. メニュー表示を更新 ======
        if hasattr(self, 'viewmenu'):
            label = "ライトモードに切り替え" if self.dark_mode else "ダークモードに切り替え"
            try:
                self.viewmenu.entryconfig(0, label=label)
            except:
                pass
        
        # ====== 12. 開いているサブウィンドウにも適用 ======
        self._apply_dark_mode_to_windows()
        
        # 少し待ってから再度更新（確実に適用されるように）
        self.root.after(100, self._finalize_dark_mode)
    
    def _apply_dark_mode_to_windows(self):
        """開いているサブウィンドウにもダークモードを適用"""
        if self.dark_mode:
            bg, fg = "#2d2d30", "#d4d4d4"
        else:
            bg, fg = "SystemButtonFace", "black"
        
        # 既存のウィンドウに適用
        windows_to_check = [
            'dan_window', 'search_window', 'todo_window',
            'offset_window', 'bpm_window', 'compare_window',
            'palette_window'
        ]
        
        for window_name in windows_to_check:
            if hasattr(self, window_name):
                window = getattr(self, window_name)
                if window and window.winfo_exists():
                    try:
                        self._apply_dark_mode_to_widget(window, bg, fg)
                    except:
                        pass
    
    def _apply_dark_mode_to_widget(self, widget, bg, fg):
        """ウィジェットとその子ウィジェットにダークモードを適用"""
        try:
            # ウィジェットタイプに応じて設定
            if isinstance(widget, (tk.Toplevel, tk.Frame, tk.LabelFrame)):
                widget.config(bg=bg)
                if isinstance(widget, tk.LabelFrame):
                    # LabelFrameのタイトル色も変更
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Label):
                            child.config(bg=bg, fg=fg)
            elif isinstance(widget, (tk.Label, tk.Button)):
                widget.config(bg=bg, fg=fg)
            elif isinstance(widget, (tk.Entry, tk.Text, tk.Listbox)):
                widget.config(bg=bg if bg != "SystemButtonFace" else "white", 
                             fg=fg, 
                             insertbackground=fg)
            elif isinstance(widget, ttk.Combobox):
                # ttk.Comboboxのスタイル設定
                style = ttk.Style()
                if self.dark_mode:
                    style.configure("TCombobox", 
                                   fieldbackground=bg,
                                   background=bg,
                                   foreground=fg)
        except:
            pass
        
        # 子ウィジェットにも再帰的に適用
        try:
            for child in widget.winfo_children():
                self._apply_dark_mode_to_widget(child, bg, fg)
        except:
            pass
    
    def _finalize_dark_mode(self):
        """ダークモード適用の最終処理"""
        # 行番号を再度更新（確実に色が反映されるように）
        self.update_linenumbers()
        
        # テキストエリアの表示を更新
        self.text.update_idletasks()
        
        # ダークモード切り替え後のフォーカス設定
        self.text.focus_set()
        
    def update_all(self):
        self.update_linenumbers()
        self.update_status()
        self.update_statusbar()
        filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
        self.root.title(f"TJA Editor - {filename}")

    def update_statusbar(self):
        """ステータスバーにブレッドクラム情報と基本情報を表示"""
        try:
            # 基本情報の取得（修正前のロジック）
            line, col = self.text.index(tk.INSERT).split('.')
            total_notes = len(re.findall(r'[12345678]', self.text.get("1.0", tk.END)))
            filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
            mode = "ダーク" if self.dark_mode else "ライト"
            
            cursor_pos = self.text.index("insert")
            line_num = int(cursor_pos.split('.')[0])
            
            if self.current_file:
                filename = os.path.basename(self.current_file)
            else:
                filename = "新規ファイル"
            
            lines = self.text.get("1.0", tk.END).splitlines()
            total_lines = len(lines)
            
            # ====== COURSE ブロック検出 ======
            course_blocks = []
            current_block_start = None
            current_course_name = None
            
            for i, line_text in enumerate(lines):
                u = line_text.strip().upper()
                if u.startswith("COURSE:"):
                    if current_block_start is not None:
                        course_blocks.append((current_block_start, i, current_course_name))
                    current_block_start = i
                    current_course_name = u[7:].strip()
            
            if current_block_start is not None:
                course_blocks.append((current_block_start, total_lines, current_course_name))
            
            # ====== 現在どの COURSE にいるか ======
            current_course = None
            current_block = None
            for start, end, raw in course_blocks:
                if start <= line_num - 1 < end:
                    current_block = (start, end)
                    course_map = {
                        "0": "かんたん", "1": "ふつう", "2": "むずかしい",
                        "3": "鬼", "4": "裏鬼",
                        "EASY": "かんたん", "NORMAL": "ふつう", "HARD": "むずかしい",
                        "ONI": "鬼", "EDIT": "裏鬼", "URA": "裏鬼"
                    }
                    current_course = course_map.get(raw, raw)
                    break
            
            # ====== COURSE 外ならヘッダー ======
            if current_block is None:
                # 現在行が空行かチェック
                current_line = lines[line_num - 1].strip() if line_num - 1 < len(lines) else ""
                if not current_line:
                    # 空行の場合は「空行」と表示
                    breadcrumb = [filename, "ヘッダー部分", "空行", f"行 {line_num}"]
                elif current_line.startswith("#"):
                    # #で始まる命令文の場合は命令文を表示（#START/#END系以外）
                    current_line_upper = current_line.upper()
                    if current_line_upper in ["#START", "#END", "#P1START", "#P2START", "#P1END", "#P2END"]:
                        # #START/#END系は特別扱い（譜面開始/終了）
                        if current_line_upper in ["#START", "#P1START", "#P2START"]:
                            breadcrumb = [filename, "ヘッダー部分", "譜面開始", f"行 {line_num}"]
                        else:
                            breadcrumb = [filename, "ヘッダー部分", "譜面終了", f"行 {line_num}"]
                    else:
                        # それ以外の命令文
                        command_name = current_line.split()[0] if " " in current_line else current_line
                        breadcrumb = [filename, "ヘッダー部分", command_name, f"行 {line_num}"]
                else:
                    breadcrumb = [filename, "ヘッダー部分", f"行 {line_num}"]
            else:
                start_line, end_line = current_block
                
                # ====== COURSE 内部解析 ======
                in_chart = False
                after_end = False
                
                measure_count = 0
                current_measure_started = False
                
                for i in range(start_line + 1, min(line_num, end_line)):
                    line_text = lines[i]
                    u = line_text.strip().upper()
                    
                    if u in ["#START", "#P1START", "#P2START"]:
                        in_chart = True
                        after_end = False
                        measure_count = 0
                        current_measure_started = False
                        continue
                    
                    if u in ["#END", "#P1END", "#P2END"]:
                        in_chart = False
                        after_end = True
                        continue
                    
                    if in_chart:
                        # コメント行や空行は無視
                        if u.startswith("//") or u.startswith(";") or not u:
                            continue
                        # #で始まる命令文も無視（小節カウントに影響しない）
                        if u.startswith("#"):
                            continue
                        if "," in line_text:
                            measure_count += 1
                            current_measure_started = False
                        else:
                            current_measure_started = True
                
                # ====== 現在行の状態 ======
                current_line = lines[line_num - 1].strip() if line_num - 1 < len(lines) else ""
                current_line_upper = current_line.upper()
                is_start_line = current_line_upper in ["#START", "#P1START", "#P2START"]
                is_end_line = current_line_upper in ["#END", "#P1END", "#P2END"]
                
                current_line_in_measure = False
                if in_chart and line_num - 1 < end_line:
                    if current_line and not current_line.startswith("#") and not current_line.startswith("//") and not current_line.startswith(";"):
                        current_line_in_measure = True
                        if "," not in current_line:
                            measure_count += 1
                
                # 現在行が空行かチェック
                if not current_line:
                    # 空行の場合
                    breadcrumb = [filename, f"[{current_course}]", "空行", f"行 {line_num}"]
                elif current_line.startswith("#"):
                    # #で始まる行の場合
                    if current_line_upper in ["#START", "#END", "#P1START", "#P2START", "#P1END", "#P2END"]:
                        # #START/#END系は特別扱い
                        if is_start_line:
                            breadcrumb = [filename, f"[{current_course}]", "譜面開始", f"行 {line_num}"]
                        elif is_end_line:
                            breadcrumb = [filename, f"[{current_course}]", "譜面終了", f"行 {line_num}"]
                    else:
                        # それ以外の命令文
                        command_name = current_line.split()[0] if " " in current_line else current_line
                        breadcrumb = [filename, f"[{current_course}]", command_name, f"行 {line_num}"]
                else:
                    # 通常行の場合
                    breadcrumb = [filename, f"[{current_course}]"]
                    
                    if is_start_line:
                        breadcrumb.append("譜面開始")
                    elif in_chart:
                        breadcrumb.append("譜面編集中")
                        if measure_count > 0:
                            breadcrumb.append(f"小節 {measure_count}")
                        else:
                            if current_measure_started or current_line_in_measure:
                                breadcrumb.append("小節 1")
                    elif is_end_line or after_end:
                        breadcrumb.append("譜面終了")
                    else:
                        breadcrumb.append("ヘッダー部分")
                    
                    breadcrumb.append(f"行 {line_num}")
            
            # ブレッドクラム部分を結合
            breadcrumb_text = " > ".join(breadcrumb)
            
            # 基本情報を追加（修正前のupdate_statusbarの形式）
            status_text = f"{breadcrumb_text} │ 行:{line} 列:{int(col)+1} │ 総ノート:{total_notes} │ {mode}モード"
            
            self.statusbar.config(text=status_text)
            
        except Exception as e:
            print(f"ステータスバー更新エラー: {e}")  # デバッグ用
            # エラー時は簡易表示
            try:
                line, col = self.text.index(tk.INSERT).split('.')
                total_notes = len(re.findall(r'[12345678]', self.text.get("1.0", tk.END)))
                filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
                mode = "ダーク" if self.dark_mode else "ライト"
                self.statusbar.config(
                    text=f"{filename} │ 行:{line} 列:{int(col)+1} │ 総ノート:{total_notes} │ {mode}モード"
                )
            except:
                self.statusbar.config(text="準備完了")
        
        # 定期的に更新
        self.root.after(200, self.update_statusbar)
    
    def get_taikojiro_path(self):
        """設定ファイルから太鼓さん次郎の実行ファイルパスを取得"""
        if not os.path.exists(self.CONFIG_FILE):
            return None
        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                path = config.get("taikojiro_path")
                return path if path and os.path.isfile(path) else None
        except Exception:
            return None

    def on_linenumber_click(self, event):
        """行番号をクリックしたときの処理"""
        # テキストエリアにフォーカスを当てる
        self.text.focus_set()
        
        try:
            # テキストウィジェットの該当位置のインデックスを取得
            text_index = self.text.index(f"@0,{event.y}")
            line_num = int(text_index.split('.')[0])
            
            # その行を選択
            self.text.tag_remove("sel", "1.0", "end")
            self.text.tag_add("sel", f"{line_num}.0", f"{line_num}.end")
            self.text.mark_set("insert", f"{line_num}.0")
            self.text.see(f"{line_num}.0")
            
            # ドラッグ開始位置を記録
            self.drag_start_line = line_num
        except:
            pass
    
    def on_linenumber_drag(self, event):
        if not hasattr(self, 'drag_start_line'):
            return
    
        self.text.focus_set()
    
        try:
            # --- 自動スクロール ---
            margin = 20
            if event.y < margin:
                self.text.yview_scroll(-1, "units")
            elif event.y > self.linenumbers.winfo_height() - margin:
                self.text.yview_scroll(1, "units")
    
            # --- 行位置取得 ---
            text_index = self.text.index(f"@0,{event.y}")
            line_num = int(text_index.split('.')[0])
    
            start = min(self.drag_start_line, line_num)
            end = max(self.drag_start_line, line_num)
    
            self.text.tag_remove("sel", "1.0", "end")
            self.text.tag_add("sel", f"{start}.0", f"{end}.end")
            self.text.mark_set("insert", f"{line_num}.0")
    
            # スクロール位置へ移動
            self.text.see(f"{line_num}.0")
    
            # ★ 行番号を更新（重要）
            self.update_linenumbers()
    
        except:
            pass

    def get_line_from_y(self, y):
        """Y座標から行番号を取得"""
        try:
            # スクロール位置を考慮
            visible_start = self.text.index("@0,0")
            start_line = int(visible_start.split('.')[0])
            
            # テキストエリアの各行の位置を確認
            for line_num in range(start_line, start_line + 100):  # 表示範囲内のみチェック
                bbox = self.text.bbox(f"{line_num}.0")
                if bbox is None:
                    break
                
                x, bbox_y, width, height = bbox
                
                # クリック位置がこの行の範囲内か判定
                if bbox_y <= y <= bbox_y + height:
                    return line_num
            
            return None
        except:
            return None

    def set_taikojiro_path(self, path):
        """設定ファイルに太鼓さん次郎のパスを保存"""
        config = {}
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                pass
        config["taikojiro_path"] = path
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("設定保存エラー", f"設定ファイルの保存に失敗しました:\n{e}")

    def preview_play(self):
        """F5キー押下時に呼び出されるプレビュー再生処理"""
        # ファイルが保存されていない場合は警告
        if not self.current_file:
            messagebox.showwarning(
                "ファイル未保存",
                "プレビュー再生するには、まずファイルを保存してください。"
            )
            return

        # 未保存の変更があれば自動保存
        if self.text.edit_modified():
            if not messagebox.askyesno(
                "自動保存",
                "変更が保存されていません。\n自動で上書き保存しますか？"
            ):
                return
            self.save_file()  # current_file が存在するので上書き保存が走る

        # 太鼓さん次郎のパス取得
        tj_path = self.get_taikojiro_path()
        if not tj_path:
            # 初回はファイル選択ダイアログでパスを登録
            path = filedialog.askopenfilename(
                title="太鼓さん次郎の実行ファイルを選択してください",
                filetypes=[("実行ファイル", "Taikojiro.exe"), ("すべてのファイル", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            if not path:
                return  # キャンセルされた場合
            self.set_taikojiro_path(path)
            tj_path = path

        # 起動
        try:
            import subprocess
            subprocess.Popen(
                [tj_path, self.current_file],
                cwd=os.path.dirname(tj_path)  # 起動ディレクトリを正しく設定
            )
            self.statusbar.config(
                text=f"プレビュー起動: {os.path.basename(self.current_file)}"
            )
        except Exception as e:
            messagebox.showerror(
                "起動失敗",
                f"太鼓さん次郎を起動できませんでした。\n\n{e}"
            )
    
    def update_linenumbers(self, event=None):
        self.linenumbers.delete("all")
        total_lines = int(self.text.index('end-1c').split('.')[0])
        if total_lines == 0:
            total_lines = 1
        
        # 行番号の桁数に応じて動的に幅を計算
        digits = len(str(total_lines))
        canvas_w = max(60, 40 + digits * 12)
        self.linenumbers.config(width=canvas_w)
        
        color = "#777777" if not self.dark_mode else "#e0e0e0"
        
        # テキストエリアの実際の表示高さ
        visible_height = self.text.winfo_height()
        
        # 実際に画面に表示されている行だけを描画
        for line_num in range(1, total_lines + 1):
            index = f"{line_num}.0"
            
            try:
                bbox = self.text.bbox(index)
                if bbox is None:
                    continue
                
                x, y, width, height = bbox
                
                # 画面内に表示されているかチェック
                # 下端チェックを厳密に: 行の下端が画面外なら描画しない
                if y < -height or y + height > visible_height:
                    continue
                
                y_center = y + height // 2
                
                self.linenumbers.create_text(canvas_w - 10, y_center, anchor="e", 
                                            text=str(line_num), fill=color, font=self.main_font)
            except:
                continue

    def update_status(self):
        res = self.count_don_katsu_in_chart()
        lines = []
    
        for course, d, k, combo, level in res:
            level_str = f"★{level}" if level != "?" else "？？"
            lines.append(f"【{course}】  {level_str}")
            lines.append(f" ドン　　　：{d}")
            lines.append(f" カツ　　　：{k}")
            lines.append(f" 最大コンボ：{combo}")
            lines.append("\n")

    
        text = "\n".join(lines) if lines else "譜面がありません"
    
        if hasattr(self, 'count_text'):
            self.count_text.config(state="normal")
            self.count_text.delete("1.0", tk.END)
            self.count_text.insert("1.0", text)
            self.count_text.config(state="disabled")
        else:
            self.count_label.config(text=text)

    def open_offset_adjuster(self):
        """OFFSET一括調整ウィンドウを開く"""
        if hasattr(self, 'offset_window') and self.offset_window and self.offset_window.winfo_exists():
            self.offset_window.lift()
            return
        
        # 現在のOFFSET値を取得
        content = self.text.get("1.0", tk.END)
        current_offset = self.get_current_offset(content)
        
        self.offset_window = Toplevel(self.root)
        self.offset_window.title("OFFSET一括調整")
        self.offset_window.geometry("600x500")
        self.offset_window.resizable(False, False)
        self.offset_window.transient(self.root)
        
        # 説明
        Label(self.offset_window, text="OFFSETをリアルタイムでプレビュー調整", 
              font=("メイリオ", 14, "bold")).pack(pady=15)
        
        # 現在値表示
        info_frame = Frame(self.offset_window)
        info_frame.pack(pady=10)
        
        Label(info_frame, text="現在のOFFSET:", 
              font=("メイリオ", 11)).grid(row=0, column=0, padx=5)
        Label(info_frame, text=f"{current_offset:.3f}" if current_offset is not None else "未設定", 
              font=("メイリオ", 11, "bold"), fg="#0066cc").grid(row=0, column=1, padx=5)
        
        # スライダーフレーム
        slider_frame = Frame(self.offset_window)
        slider_frame.pack(pady=20, padx=30, fill="x")
        
        Label(slider_frame, text="調整値:", font=("メイリオ", 11)).pack()
        
        # 調整値表示
        self.offset_value_label = Label(slider_frame, text="0.000", 
                                        font=("Arial", 36, "bold"), fg="#009688")
        self.offset_value_label.pack(pady=10)
        
        # スライダー
        self.offset_slider = tk.Scale(slider_frame, from_=-0.5, to=0.5, resolution=0.001,
                                      orient=tk.HORIZONTAL, length=500,
                                      command=self.on_offset_change,
                                      showvalue=0)
        self.offset_slider.set(0)
        self.offset_slider.pack(pady=10)
        
        # 範囲ラベル
        range_frame = Frame(slider_frame)
        range_frame.pack(fill="x")
        Label(range_frame, text="-0.5秒", font=("メイリオ", 9)).pack(side="left")
        Label(range_frame, text="+0.5秒", font=("メイリオ", 9)).pack(side="right")
        
        # 微調整ボタン
        fine_frame = Frame(self.offset_window)
        fine_frame.pack(pady=15)
        
        Label(fine_frame, text="微調整:", font=("メイリオ", 10)).pack()
        
        btn_frame = Frame(fine_frame)
        btn_frame.pack(pady=5)
        
        Button(btn_frame, text="-0.01", command=lambda: self.adjust_offset(-0.01),
               width=6).pack(side="left", padx=2)
        Button(btn_frame, text="-0.001", command=lambda: self.adjust_offset(-0.001),
               width=6).pack(side="left", padx=2)
        Button(btn_frame, text="リセット", command=lambda: self.offset_slider.set(0),
               width=8).pack(side="left", padx=2)
        Button(btn_frame, text="+0.001", command=lambda: self.adjust_offset(0.001),
               width=6).pack(side="left", padx=2)
        Button(btn_frame, text="+0.01", command=lambda: self.adjust_offset(0.01),
               width=6).pack(side="left", padx=2)
        
        # 適用ボタンフレーム
        apply_frame = Frame(self.offset_window)
        apply_frame.pack(pady=20)
        
        Button(apply_frame, text="適用してTJAに反映", command=self.apply_offset,
               width=20, font=("メイリオ", 11, "bold"),
               bg="#4CAF50", fg="white").pack(side="left", padx=5)
        Button(apply_frame, text="キャンセル", command=self.offset_window.destroy,
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        
        # 保存用
        self.original_offset = current_offset
    
    def get_current_offset(self, content):
        """現在のOFFSET値を取得"""
        import re
        match = re.search(r'^OFFSET:\s*(-?\d+\.?\d*)', content, re.MULTILINE | re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except:
                return None
        return None
    
    def on_offset_change(self, value):
        """スライダー変更時"""
        offset = float(value)
        self.offset_value_label.config(text=f"{offset:+.3f}")
    
    def adjust_offset(self, delta):
        """微調整ボタン"""
        current = self.offset_slider.get()
        new_value = current + delta
        # 範囲チェック
        if -0.5 <= new_value <= 0.5:
            self.offset_slider.set(new_value)
    
    def apply_offset(self):
        """調整したOFFSETをTJAに適用"""
        adjustment = self.offset_slider.get()
        
        if adjustment == 0:
            messagebox.showinfo("変更なし", "OFFSET値が変更されていません。", 
                               parent=self.offset_window)
            return
        
        # 新しいOFFSET値を計算
        if self.original_offset is not None:
            new_offset = self.original_offset + adjustment
        else:
            new_offset = adjustment
        
        # 確認ダイアログ
        if self.original_offset is not None:
            message = (f"現在のOFFSET: {self.original_offset:.3f}\n"
                      f"調整値: {adjustment:+.3f}\n"
                      f"新しいOFFSET: {new_offset:.3f}\n\n"
                      f"この値を適用しますか？")
        else:
            message = (f"OFFSETが未設定です。\n"
                      f"新しいOFFSET: {new_offset:.3f}\n\n"
                      f"この値を適用しますか？")
        
        response = messagebox.askyesno("OFFSET適用確認", message, 
                                       parent=self.offset_window)
        
        if response:
            self._apply_offset_to_tja(new_offset)
            self.offset_window.destroy()
            messagebox.showinfo("適用完了", 
                               f"OFFSETを {new_offset:.3f} に設定しました！\n"
                               f"F5でプレビュー再生して確認してください。")

    def count_don_katsu_in_chart(self):
        """
        現在のテキストから譜面統計を計算する関数
        戻り値: [(course, don, katsu, combo, level), ...]
        """
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        results = []        # (course, don, katsu, combo, level)
        current = "不明"
        current_level = "?"
        in_chart = False
        don = katsu = 0
    
        # コース名マッピング
        map_course = {
            "easy": "かんたん", "normal": "ふつう", "hard": "むずかしい",
            "oni": "鬼", "edit": "裏鬼", "ura": "裏鬼",
            "0": "かんたん", "1": "ふつう", "2": "むずかしい",
            "3": "鬼", "4": "裏鬼"
        }
    
        for line in lines:
            s = line.strip().lower()
    
            # COURSE 切り替え
            m = re.match(r"course:\s*([^\s#;]+)", s, re.I)
            if m:
                c = m.group(1).strip().lower()
                current = map_course.get(c, c.capitalize())
                current_level = "?"
    
            # LEVEL 取得
            lm = re.match(r"level:\s*(\d+)", s, re.I)
            if lm:
                current_level = lm.group(1)
    
            # 譜面開始
            if s in ["#start", "#p1start", "#p2start"]:
                if in_chart:
                    results.append((current, don, katsu, don + katsu, current_level))
                    don = katsu = 0
                in_chart = True
                continue
    
            # 譜面終了
            if s in ["#end", "#p1end", "#p2end"]:
                if in_chart:
                    results.append((current, don, katsu, don + katsu, current_level))
                    don = katsu = 0
                in_chart = False
                continue
    
            # ノートカウント（コメント除外）
            if in_chart and not line.lstrip().startswith('#'):
                # "//" や ";" コメントを除外
                line_clean = re.split(r"//|;", line)[0]
                for ch in line_clean:
                    if ch in '13':  # ドン系
                        don += 1
                    elif ch in '24':  # カツ系
                        katsu += 1
    
        # 最後の譜面が閉じられていない場合も結果に追加
        if in_chart and (don + katsu > 0):
            results.append((current, don, katsu, don + katsu, current_level))
    
        return results if results else [("なし", 0, 0, 0, "?")]

    def update_title(self):
        """ウィンドウのタイトルを現在開いているファイル名＋変更マークで更新"""
        base = "TJA Editor"
        if self.current_file:
            base += f" - {os.path.basename(self.current_file)}"
        if self.text.edit_modified():
            base += " ●"   # 変更があるときは ● を付ける（お好みで * でもOK）
        self.root.title(base)
        
    def check_errors(self):
        """譜面の一般的なエラーを自動検出（完全修正版）"""
        content = self.text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("エラーチェック", "譜面が空です。")
            return
        
        lines = content.splitlines()
        errors = []
        
        # エラー検出ロジック
        start_count = 0
        end_count = 0
        in_chart = False
        has_course = False
        has_level = False
        has_bpm = False
        has_wave = False
        
        # コースごとの管理
        current_course = None
        course_balloons = {}  # {course: balloon_start_count}
        course_balloon_ends = {}  # {course: balloon_end_count}
        course_balloon_defs = {}  # {course: balloon_defined}
        course_has_measure = {}  # {course: has_measure_definition}
        course_bpm_values = {}  # {course: [bpm_values]}
        course_scroll_values = {}  # {course: [scroll_values]}
        
        # 状態管理
        balloon_stack = []  # 風船の開始位置（行番号）を記録
        in_branch = False
        branch_start_line = 0
        current_bpm = None
        current_scroll = 1.0
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            upper = stripped.upper()
            
            # 1. #START/#END の対応チェック
            if upper in ["#START", "#P1START", "#P2START"]:
                if in_chart:
                    errors.append((i, "警告", "#START が閉じられていません（二重開始）"))
                start_count += 1
                in_chart = True
                balloon_stack = []  # 新しい譜面開始で風船スタックをクリア
            elif upper in ["#END", "#P1END", "#P2END"]:
                if not in_chart:
                    errors.append((i, "エラー", "#END に対応する #START がありません"))
                end_count += 1
                in_chart = False
                # 終了時点で未完了の風船があるかチェック
                if balloon_stack:
                    for line_num in balloon_stack:
                        errors.append((line_num, "エラー", "風船が開始されましたが終了していません"))
                balloon_stack = []
            
            # 2. COURSE 切り替え
            if upper.startswith("COURSE:"):
                has_course = True
                course_value = stripped[7:].strip().upper()
                # 数字を名前に変換
                course_map = {"0": "EASY", "1": "NORMAL", "2": "HARD", "3": "ONI", "4": "EDIT"}
                current_course = course_map.get(course_value, course_value)
                # コースが切り替わったら状態を初期化
                if current_course not in course_balloons:
                    course_balloons[current_course] = 0
                    course_balloon_ends[current_course] = 0
                    course_balloon_defs[current_course] = 0
                    course_has_measure[current_course] = False
                    course_bpm_values[current_course] = []
                    course_scroll_values[current_course] = []
            
            # 3. LEVEL の存在チェック
            if upper.startswith("LEVEL:"):
                has_level = True
                try:
                    level = int(stripped[6:].strip())
                    if not (1 <= level <= 10):
                        errors.append((i, "警告", f"LEVELの値({level})は1〜10の範囲内であるべきです"))
                except:
                    errors.append((i, "エラー", "LEVELの値が無効です（数値を指定してください）"))
            
            # 4. BPM 定義チェック
            if upper.startswith("BPM:"):
                has_bpm = True
                try:
                    bpm_value = float(stripped[4:].strip())
                    current_bpm = bpm_value
                    if current_course:
                        course_bpm_values[current_course].append(bpm_value)
                    if bpm_value <= 0:
                        errors.append((i, "エラー", f"BPM値({bpm_value})は正の数である必要があります"))
                    elif bpm_value < 30 or bpm_value > 300:
                        errors.append((i, "警告", f"BPM値({bpm_value})が極端です（通常は30〜300の範囲）"))
                except:
                    errors.append((i, "エラー", "BPMの値が無効です（数値を指定してください）"))
            
            # 5. WAVE 定義チェック
            if upper.startswith("WAVE:"):
                has_wave = True
                wave_file = stripped[5:].strip()
                if not wave_file:
                    errors.append((i, "エラー", "WAVEファイル名が指定されていません"))
                elif not wave_file.lower().endswith(('.ogg', '.wav', '.mp3')):
                    errors.append((i, "警告", f"WAVEファイル({wave_file})は通常.ogg/.wav/.mp3形式です"))
            
            # 6. #MEASURE 定義チェック
            if upper.startswith("#MEASURE"):
                try:
                    measure_str = stripped[8:].strip()
                    if "/" in measure_str:
                        numerator, denominator = measure_str.split("/")
                        num = int(numerator.strip())
                        den = int(denominator.strip())
                        if num <= 0 or den <= 0:
                            errors.append((i, "エラー", f"#MEASUREの値({measure_str})は正の数である必要があります"))
                        if current_course:
                            course_has_measure[current_course] = True
                    else:
                        errors.append((i, "エラー", f"#MEASUREの書式が不正です: {measure_str} (例: 4/4)"))
                except:
                    errors.append((i, "エラー", f"#MEASUREの値が無効です: {stripped[8:]}"))
            
            # 7. #BPMCHANGE チェック
            if upper.startswith("#BPMCHANGE"):
                try:
                    bpm_change = float(stripped[10:].strip())
                    if bpm_change <= 0:
                        errors.append((i, "エラー", f"#BPMCHANGE値({bpm_change})は正の数である必要があります"))
                    elif bpm_change < 30 or bpm_change > 300:
                        errors.append((i, "警告", f"#BPMCHANGE値({bpm_change})が極端です"))
                    if current_course:
                        course_bpm_values[current_course].append(bpm_change)
                except:
                    errors.append((i, "エラー", "#BPMCHANGEの値が無効です（数値を指定してください）"))
            
            # 8. #SCROLL チェック
            if upper.startswith("#SCROLL"):
                try:
                    scroll_value = float(stripped[7:].strip())
                    if scroll_value <= 0:
                        errors.append((i, "エラー", f"#SCROLL値({scroll_value})は正の数である必要があります"))
                    elif scroll_value < 0.5 or scroll_value > 3.0:
                        errors.append((i, "警告", f"#SCROLL値({scroll_value})が極端です（通常は0.5〜3.0の範囲）"))
                    if current_course:
                        course_scroll_values[current_course].append(scroll_value)
                except:
                    errors.append((i, "エラー", "#SCROLLの値が無効です（数値を指定してください）"))
            
            # 9. #BRANCHSTART チェック
            if upper.startswith("#BRANCHSTART"):
                if in_branch:
                    errors.append((i, "エラー", "#BRANCHSTART が閉じられていません（二重開始）"))
                in_branch = True
                branch_start_line = i
                try:
                    params = stripped[12:].strip()
                    if "," in params:
                        acc, roll = params.split(",")
                        acc_val = int(acc.strip())
                        roll_val = int(roll.strip())
                        if not (0 <= acc_val <= 100):
                            errors.append((i, "警告", f"分岐精度条件({acc_val}%)は0〜100の範囲であるべきです"))
                        if roll_val < 0:
                            errors.append((i, "警告", f"分岐ロール条件({roll_val})は0以上の値であるべきです"))
                    else:
                        errors.append((i, "エラー", "#BRANCHSTARTの書式が不正です（例: #BRANCHSTART 90,10）"))
                except:
                    errors.append((i, "エラー", "#BRANCHSTARTの値が無効です"))
            
            # 10. 分岐譜面終了チェック（簡易）
            if upper == "#N" or upper == "#E" or upper == "#M":
                in_branch = False
            
            # 11. 全角数字チェック（譜面行）
            if in_chart and not stripped.startswith("#") and not stripped.startswith("//") and not stripped.startswith(";"):
                if any(c in "０１２３４５６７８９" for c in stripped):
                    errors.append((i, "エラー", "全角数字が含まれています（半角に修正してください）"))
            
            # 12. 風船(7)のペアリングチェック
            if in_chart and not stripped.startswith("#") and not stripped.startswith("//") and not stripped.startswith(";"):
                # 風船の開始と終了を追跡
                for j, char in enumerate(stripped):
                    if char == '7':
                        if not balloon_stack:
                            # 風船開始
                            balloon_stack.append(i)
                            if current_course:
                                course_balloons[current_course] = course_balloons.get(current_course, 0) + 1
                        else:
                            # 風船終了
                            balloon_stack.pop()
                            if current_course:
                                course_balloon_ends[current_course] = course_balloon_ends.get(current_course, 0) + 1
            
            # 13. BALLOON定義チェック（複数行対応）
            if upper.startswith("BALLOON:"):
                balloon_line = stripped[8:].strip()
                j = i
                # 複数行にまたがる定義を収集
                while j < len(lines) and j == i or (lines[j].strip() and 
                                                   not lines[j].strip().upper().startswith(("COURSE:", "LEVEL:", "#START", "#END", 
                                                                                           "TITLE:", "BPM:", "WAVE:", "OFFSET:"))):
                    if j > i and lines[j-1].strip().endswith(','):
                        balloon_line += lines[j].strip()
                    elif j > i:
                        break
                    j += 1
                
                # 数値部分を抽出
                numbers = [v.strip() for v in balloon_line.split(",") if v.strip().isdigit()]
                balloon_defined = len(numbers)
                
                # 数値の妥当性チェック
                for num_str in numbers:
                    num = int(num_str)
                    if num <= 0:
                        errors.append((i, "警告", f"BALLOON値({num})は正の数であるべきです"))
                
                if current_course:
                    course_balloon_defs[current_course] = course_balloon_defs.get(current_course, 0) + balloon_defined
                else:
                    errors.append((i, "警告", "COURSE定義より前にBALLOONが定義されています"))
        
        # 14. #START/#END の数の一致チェック
        if start_count != end_count:
            errors.append((0, "エラー", f"#START({start_count}個) と #END({end_count}個) の数が一致しません"))
        
        # 15. COURSE/LEVEL/BPM/WAVE 未定義チェック
        if not has_course:
            errors.append((0, "警告", "COURSE: が定義されていません"))
        if not has_level:
            errors.append((0, "警告", "LEVEL: が定義されていません"))
        if not has_bpm:
            errors.append((0, "警告", "BPM: が定義されていません"))
        if not has_wave:
            errors.append((0, "警告", "WAVE: が定義されていません"))
        
        # 16. コースごとの風船チェック
        for course in set(list(course_balloons.keys()) + list(course_balloon_defs.keys())):
            balloon_start = course_balloons.get(course, 0)
            balloon_end = course_balloon_ends.get(course, 0)
            balloon_defined = course_balloon_defs.get(course, 0)
            
            # 開始と終了の数が一致するか
            if balloon_start != balloon_end:
                errors.append((0, "エラー", f"[{course}] 風船の開始({balloon_start}個)と終了({balloon_end}個)の数が一致しません"))
            
            # BALLOON定義との一致チェック
            if balloon_start > 0 and balloon_defined == 0:
                errors.append((0, "警告", f"[{course}] 風船が{balloon_start}個ありますが、BALLOON: が定義されていません"))
            elif balloon_start != balloon_defined and balloon_defined > 0:
                errors.append((0, "警告", f"[{course}] 風船の個数({balloon_start}個) と BALLOON: の定義数({balloon_defined}個) が一致しません"))
            
            # #MEASURE定義チェック
            if not course_has_measure.get(course, False):
                errors.append((0, "警告", f"[{course}] #MEASURE が定義されていません（例: #MEASURE 4/4）"))
            
            # BPM値のチェック
            bpm_values = course_bpm_values.get(course, [])
            if len(bpm_values) > 0:
                # BPM変化の急激さをチェック
                for j in range(1, len(bpm_values)):
                    ratio = max(bpm_values[j], bpm_values[j-1]) / min(bpm_values[j], bpm_values[j-1])
                    if ratio > 2.0:  # BPMが2倍以上変化
                        errors.append((0, "警告", f"[{course}] BPMの変化が急激です ({bpm_values[j-1]} → {bpm_values[j]})"))
        
        # 17. カンマの連続チェック
        for i, line in enumerate(lines, 1):
            if ",," in line:
                errors.append((i, "警告", "カンマが連続しています（空の小節）"))
            # 行末の不要なカンマチェック
            if line.rstrip().endswith(',') and i < len(lines):
                next_line = lines[i].strip()
                if next_line and not next_line.startswith(('#', '//', ';')):
                    errors.append((i, "警告", "行末に余分なカンマがあります（次の行と結合される可能性）"))
        
        # 18. 不完全な風船があるかチェック
        if balloon_stack:
            for line_num in balloon_stack:
                errors.append((line_num, "エラー", "風船が開始されましたが終了していません"))
        
        # 19. 分岐が閉じられていないかチェック
        if in_branch:
            errors.append((branch_start_line, "エラー", "#BRANCHSTART が閉じられていません"))
        
        # 20. OFFSET値のチェック
        offset_line = None
        for i, line in enumerate(lines, 1):
            if line.strip().upper().startswith("OFFSET:"):
                offset_line = i
                try:
                    offset_val = float(line.strip()[7:].strip())
                    if abs(offset_val) > 5.0:
                        errors.append((i, "警告", f"OFFSET値({offset_val})が大きすぎます（通常は-2.0〜2.0の範囲）"))
                except:
                    errors.append((i, "エラー", "OFFSETの値が無効です（数値を指定してください）"))
                break
        
        if offset_line is None:
            errors.append((0, "警告", "OFFSET: が定義されていません"))
        
        # 結果表示
        if not errors:
            messagebox.showinfo("エラーチェック", "エラーは見つかりませんでした！\n譜面は正常です。")
            return
        
        # エラーウィンドウを表示
        self.show_error_window(errors)
    
    def show_error_window(self, errors):
        """エラー一覧ウィンドウを表示"""
        win = Toplevel(self.root)
        win.title(f"エラーチェック結果 - {len(errors)}件")
        win.geometry("800x500")
        win.transient(self.root)
        
        Label(win, text=f"検出されたエラー: {len(errors)}件", 
              font=("メイリオ", 12, "bold")).pack(pady=10)
        
        frame = Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        scrollbar = Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        
        listbox = Listbox(frame, yscrollcommand=scrollbar.set, 
                         font=("MS Gothic", 10), selectmode="single")
        
        for line_num, error_type, message in errors:
            if line_num == 0:
                display = f"[{error_type}] 全体: {message}"
            else:
                display = f"[{error_type}] 行{line_num}: {message}"
            listbox.insert("end", display)
        
        listbox.pack(fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        def jump_to_error():
            sel = listbox.curselection()
            if not sel:
                return
            line_num, error_type, message = errors[sel[0]]
            if line_num > 0:
                self.text.see(f"{line_num}.0")
                self.text.mark_set("insert", f"{line_num}.0")
                self.text.tag_remove("sel", "1.0", "end")
                self.text.tag_add("sel", f"{line_num}.0", f"{line_num}.end")
                win.destroy()
        
        listbox.bind("<Double-Button-1>", lambda e: jump_to_error())
        
        btn_frame = Frame(win)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="該当行にジャンプ", command=jump_to_error, 
               width=18, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="閉じる", command=win.destroy, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)

    def open_todo_manager(self):
        """TODO管理ウィンドウを開く"""
        if hasattr(self, 'todo_window') and self.todo_window and self.todo_window.winfo_exists():
            self.todo_window.lift()
            return
        
        # TODOコメントを検索
        todos = self.find_todos()
        
        self.todo_window = Toplevel(self.root)
        self.todo_window.title(f"TODO管理 - {len(todos)}件")
        self.todo_window.geometry("800x500")
        self.todo_window.transient(self.root)
        
        # 説明
        info_frame = Frame(self.todo_window)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        Label(info_frame, text="譜面内のTODO/FIXMEコメントを管理", 
              font=("メイリオ", 12, "bold")).pack(anchor="w")
        Label(info_frame, text="例: ; TODO: ここの密度を下げる  または  // FIXME: ゴーゴー位置修正", 
              font=("メイリオ", 9), fg="gray").pack(anchor="w")
        
        # TODOリスト
        list_frame = Frame(self.todo_window)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.todo_listbox = Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                    font=("MS Gothic", 10), selectmode="single")
        
        if todos:
            for line_num, todo_type, message in todos:
                display = f"行{line_num}: [{todo_type}] {message}"
                self.todo_listbox.insert("end", display)
        else:
            self.todo_listbox.insert("end", "(TODOコメントはありません)")
        
        self.todo_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.todo_listbox.yview)
        
        # TODOデータを保存（ジャンプ用）
        self.current_todos = todos
        
        # ダブルクリックでジャンプ
        self.todo_listbox.bind("<Double-Button-1>", lambda e: self.jump_to_todo())
        
        # ボタンフレーム
        btn_frame = Frame(self.todo_window)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="該当行にジャンプ", command=self.jump_to_todo, 
               width=18, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="TODO挿入", command=self.insert_todo_comment, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="更新", command=self.refresh_todos, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="閉じる", command=self.todo_window.destroy, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
    
    def find_todos(self):
        """譜面内のTODO/FIXMEコメントを検索"""
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        todos = []
        
        import re
        
        for i, line in enumerate(lines, 1):
            # ; TODO: または // TODO: または ; FIXME: または // FIXME: を検索
            match = re.search(r'(?://|;)\s*(TODO|FIXME):\s*(.+)', line, re.IGNORECASE)
            if match:
                todo_type = match.group(1).upper()
                message = match.group(2).strip()
                todos.append((i, todo_type, message))
        
        return todos
    
    def jump_to_todo(self):
        """選択したTODOの行にジャンプ"""
        if not hasattr(self, 'current_todos') or not self.current_todos:
            return
        
        sel = self.todo_listbox.curselection()
        if not sel:
            messagebox.showwarning("未選択", "ジャンプするTODOを選択してください。", 
                                  parent=self.todo_window)
            return
        
        line_num, todo_type, message = self.current_todos[sel[0]]
        
        # 該当行にジャンプ
        self.text.see(f"{line_num}.0")
        self.text.mark_set("insert", f"{line_num}.0")
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", f"{line_num}.0", f"{line_num}.end")
        self.text.focus_set()
        
        # ウィンドウは閉じない（連続作業しやすいように）
    
    def insert_todo_comment(self):
        """カーソル位置にTODOコメントを挿入"""
        todo_text = simpledialog.askstring(
            "TODO挿入",
            "TODOコメントの内容を入力してください:",
            parent=self.todo_window
        )
        
        if todo_text:
            comment = f"; TODO: {todo_text}\n"
            self.text.insert(tk.INSERT, comment)
            self.text.see(tk.INSERT)
            
            # TODOリストを更新
            self.refresh_todos()
    
    def refresh_todos(self):
        """TODOリストを更新"""
        if not hasattr(self, 'todo_window') or not self.todo_window.winfo_exists():
            return
        
        todos = self.find_todos()
        self.current_todos = todos
        
        self.todo_listbox.delete(0, tk.END)
        
        if todos:
            for line_num, todo_type, message in todos:
                display = f"行{line_num}: [{todo_type}] {message}"
                self.todo_listbox.insert("end", display)
        else:
            self.todo_listbox.insert("end", "(TODOコメントはありません)")
        
        # タイトルも更新
        self.todo_window.title(f"TODO管理 - {len(todos)}件")

    def show_version(self):
        version_info = """
        TJA Editor
        バージョン: 1.0.0 (2025-12-05)
        ビルド: Final Release
        
        主な機能:
        ・配布用ZIP自動作成 (Ctrl+E)
        ・リアルタイムドンカツ完全対応の最大コンボ計算
        ・WAVEからのBPM自動検出
        ・OFFSET自動調整
        ・スマートカンマ挿入
        
        開発者: りゅうちゃん
        GitHub: https://github.com/ryuya0229/TJA-Editor
        
        このエディタは太鼓さん次郎/TJA譜面作成者のために作られました。
        ご自由にお使いください。
        """.strip()
        messagebox.showinfo("バージョン情報", version_info)

    def show_about(self):
        about_text = """
        TJA Editor - 次世代型TJAエディタ
        
        「1秒でも早く、1ノーツでも正確に」
        
        ・高速・軽量・安定
        ・リアルタイムドンカツと100%一致の最大コンボ
        ・配布ZIPが1クリックで完成
        ・音源からBPM/OFFSETを自動補正
        
        これからも自作譜面文化を支えるツールとして
        進化し続けます。
        
        ありがとうございます。
        """.strip()
        messagebox.showinfo("このエディタについて", about_text)
        
    def apply_syntax_highlighting(self):
        """構文ハイライトを適用"""
        # 既存のタグを削除
        for tag in ["header", "comment", "command", "error", "todo", "number"]:
            self.text.tag_remove(tag, "1.0", "end")
        
        content = self.text.get("1.0", "end-1c")
        lines = content.split("\n")
        
        for i, line in enumerate(lines, 1):
            line_start = f"{i}.0"
            line_end = f"{i}.end"
            stripped = line.strip()
            upper = stripped.upper()
            
            # 1. コメント行（// または ;）
            if stripped.startswith("//") or stripped.startswith(";"):
                # TODO/FIXMEコメントは特別扱い
                if "TODO:" in upper or "FIXME:" in upper:
                    self.text.tag_add("todo", line_start, line_end)
                else:
                    self.text.tag_add("comment", line_start, line_end)
            
            # 2. コマンド行（#で始まる）
            elif stripped.startswith("#"):
                self.text.tag_add("command", line_start, line_end)
            
            # 3. ヘッダー行（TITLE:, BPM: など）
            elif ":" in line:
                headers = [
                    "TITLE", "SUBTITLE", "BPM", "WAVE", "OFFSET", "DEMOSTART",
                    "GENRE", "SCOREMODE", "SCOREINIT", "SCOREDIFF", "COURSE",
                    "LEVEL", "BALLOON", "SONGVOL", "SEVOL", "MAKER"
                ]
            
                first_word = stripped.split(":")[0].upper()
                if first_word in headers:
                    # ヘッダー名部分だけ色を付ける
                    colon_pos = line.index(":")
                    header_end = f"{i}.{colon_pos}"
                    self.text.tag_add("header", line_start, header_end)
            
                    # 数値部分をハイライト（単体数値＋カンマ区切りの複数数値に対応）
                value_part = line[colon_pos + 1:].strip()
                
                # 単一数値 → 120, -1.25 など
                is_single_num = re.fullmatch(r"[0-9.\-]+", value_part)
                
                # カンマ区切り複数 → 5,10,15 など
                is_multi_num = re.fullmatch(r"[0-9.\-]+(,[0-9.\-]+)+", value_part)
                
                if value_part and (is_single_num or is_multi_num):
                    value_start = f"{i}.{colon_pos + 1 + line[colon_pos+1:].index(value_part)}"
                    value_end = f"{i}.{colon_pos + 1 + line[colon_pos+1:].index(value_part) + len(value_part)}"
                    self.text.tag_add("number", value_start, value_end)


            
            # 4. 行内コメントの処理（譜面行の後ろのコメント）
            if "//" in line or ";" in line:
                for sep in ["//", ";"]:
                    if sep in line:
                        comment_start_pos = line.index(sep)
                        comment_start = f"{i}.{comment_start_pos}"
                        
                        # TODO/FIXMEチェック
                        comment_part = line[comment_start_pos:].upper()
                        if "TODO:" in comment_part or "FIXME:" in comment_part:
                            self.text.tag_add("todo", comment_start, line_end)
                        else:
                            self.text.tag_add("comment", comment_start, line_end)
                        break
    
    def on_text_change(self, event=None):
        """テキスト変更時に構文ハイライトを更新"""
        # 変更があった行のみを更新（パフォーマンス向上）
        self.root.after_idle(self.apply_syntax_highlighting)
            
    def open_file(self, path=None):
        """ファイルを開く（recent_filesの重複防止・即時保存・メニュー更新を完全対応）"""
        if path is None:
            path = filedialog.askopenfilename(
                title="TJAファイルを開く",
                filetypes=[("TJAファイル", "*.tja"), ("すべてのファイル", "*.*")],
                initialdir=self.last_folder
            )
            if not path:
                return
    
        path = os.path.abspath(path)
        self.last_folder = os.path.dirname(path)
    
        try:
            # 文字エンコーディング自動判定
            with open(path, "rb") as f:
                raw = f.read()
                encoding = chardet.detect(raw)["encoding"] or "shift_jis"
                if encoding.lower().startswith("utf") and raw.startswith(b"\xef\xbb\xbf"):
                    encoding = "utf-8-sig"
    
            content = raw.decode(encoding, errors="replace")
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", content)
            self.text.edit_modified(False)
    
            self.current_file = path
            self.update_title()
            self.update_all()
    
            # === 最近使ったファイルの処理（重複なし・先頭移動・最大10個）===
            if path in self.recent_files:
                self.recent_files.remove(path)  # 既存があれば削除
            self.recent_files.insert(0, path)   # 先頭に追加
            if len(self.recent_files) > self.MAX_RECENT:
                self.recent_files = self.recent_files[:self.MAX_RECENT]
    
            # メニュー即時更新 + 設定ファイルに即時保存
            self.update_recent_menu()
            self.save_config()
            
            # 構文ハイライトを適用
            self.apply_syntax_highlighting()
            # self.update_breadcrumb()  # ← 削除
    
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルを開けませんでした:\n{e}")

    def save_file(self):
        if self.current_file:
            try:
                content = self.text.get("1.0", tk.END)
    
                # タイムスタンプ付き自動バックアップ
                if os.path.exists(self.current_file):
                    backup_dir = os.path.join(os.path.dirname(self.current_file), ".backup")
                    os.makedirs(backup_dir, exist_ok=True)
                    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    backup_name = f"{ts}_{os.path.basename(self.current_file)}"
                    shutil.copy2(self.current_file, os.path.join(backup_dir, backup_name))
    
                # ← 読み込んだエンコーディングで保存
                with open(self.current_file, 'w', encoding=self.current_encoding, newline='\n') as f:
                    f.write(content.rstrip() + "\n")
    
                self.text.edit_modified(False)
                messagebox.showinfo("保存完了", "上書き保存しました♪\n自動バックアップも作成済みです")
                self.update_all()
            except Exception as e:
                messagebox.showerror("保存エラー", f"保存に失敗しました…\n{e}")
        else:
            self.save_as_file()
        
    def save_as_file(self):
        """名前を付けて保存（TITLE:からファイル名を自動取得＆バックアップフォルダを常に確保）"""
        # デフォルトファイル名をTITLE:から取得
        default_filename = "新規譜面.tja"
        
        # 現在の内容からTITLE:を検索
        content = self.text.get("1.0", tk.END)
        title_match = re.search(r'^TITLE:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
        
        if title_match:
            title = title_match.group(1).strip()
            if title:
                # ファイル名として安全な文字に変換
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
                default_filename = f"{safe_title}.tja"
        
        # 保存ダイアログを表示（デフォルトファイル名を設定）
        file_path = filedialog.asksaveasfilename(
            initialdir=self.last_folder,
            initialfile=default_filename,
            defaultextension=".tja",
            filetypes=[("TJAファイル", "*.tja"), ("すべてのファイル", "*.*")]
        )
        
        if file_path:
            self.last_folder = os.path.dirname(file_path)
            try:
                content = self.text.get("1.0", tk.END)
                
                # ★ 常にバックアップフォルダを作成しておく（新規保存時も含む）
                backup_dir = os.path.join(os.path.dirname(file_path), ".backup")
                os.makedirs(backup_dir, exist_ok=True)
                print(f"[DEBUG] バックアップフォルダを確保: {backup_dir}")
                
                # ★ タイムスタンプ付き自動バックアップ（既存ファイルがある場合のみ）
                if os.path.exists(file_path):
                    print(f"[DEBUG] 既存ファイルを検出: {file_path}")
                    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    backup_name = f"{ts}_{os.path.basename(file_path)}"
                    backup_path = os.path.join(backup_dir, backup_name)
                    
                    try:
                        shutil.copy2(file_path, backup_path)
                        print(f"[DEBUG] バックアップ作成成功: {backup_path}")
                        
                        # 従来の ~ バックアップも残す（オプション）
                        backup = file_path + "~"
                        shutil.copy2(file_path, backup)
                        print(f"[DEBUG] 簡易バックアップも作成: {backup}")
                    except Exception as backup_error:
                        print(f"[DEBUG] バックアップ作成失敗: {backup_error}")
                
                # メインの保存処理
                with open(file_path, 'w', encoding=self.current_encoding, newline='\n') as f:
                    f.write(content.rstrip() + "\n")
                
                self.current_file = file_path
                self.text.edit_modified(False)
                self.update_all()
                
                # 成功メッセージ
                filename = os.path.basename(file_path)
                is_new_file = not self.current_file or not os.path.exists(file_path)
                
                if is_new_file:
                    message_text = f"新規保存しました！\nファイル名: {filename}"
                else:
                    message_text = f"名前を付けて保存しました！\nファイル名: {filename}"
                    if os.path.exists(file_path):
                        message_text += "\n（既存ファイルは自動バックアップされました）"
                
                messagebox.showinfo("保存完了", message_text)
                
                # 最近ファイル追加
                if file_path in self.recent_files:
                    self.recent_files.remove(file_path)
                self.recent_files.insert(0, file_path)
                self.recent_files = self.recent_files[:self.MAX_RECENT]
                self.update_recent_menu()
                
            except Exception as e:
                messagebox.showerror("保存エラー", f"保存に失敗しました…\n{e}")

    def open_command_palette(self):
        """コマンドパレットを開く（VSCode風）"""
        if hasattr(self, 'palette_window') and self.palette_window and self.palette_window.winfo_exists():
            self.palette_window.lift()
            self.palette_entry.focus_set()
            return
        
        self.palette_window = Toplevel(self.root)
        self.palette_window.title("コマンドパレット")
        self.palette_window.geometry("700x450")
        self.palette_window.transient(self.root)
        
        # ウィンドウを中央に配置
        self.palette_window.update_idletasks()
        x = (self.palette_window.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.palette_window.winfo_screenheight() // 2) - (450 // 2)
        self.palette_window.geometry(f"+{x}+{y}")
        
        # 検索バー
        search_frame = Frame(self.palette_window, bg="#f0f0f0", height=60)
        search_frame.pack(fill="x")
        search_frame.pack_propagate(False)
        
        Label(search_frame, text="🔍", font=("メイリオ", 16), bg="#f0f0f0").pack(side="left", padx=10)
        
        self.palette_entry = Entry(search_frame, font=("メイリオ", 12), relief="flat")
        self.palette_entry.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=15)
        self.palette_entry.focus_set()
        
        # コマンドリスト
        list_frame = Frame(self.palette_window)
        list_frame.pack(fill="both", expand=True)
        
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.palette_listbox = Listbox(list_frame, yscrollcommand=scrollbar.set,
                                       font=("メイリオ", 10), activestyle="none",
                                       selectmode="single", relief="flat")
        self.palette_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.palette_listbox.yview)
        
        # 利用可能なコマンド一覧
        self.commands = [
            # ファイル操作
            ("ファイルを開く", "Ctrl+O", self.open_file),
            ("上書き保存", "Ctrl+S", self.save_file),
            ("名前を付けて保存", "Ctrl+Shift+S", self.save_as_file),
            
            # 編集
            ("検索", "Ctrl+F", self.open_search),
            ("TODO管理", "Ctrl+T", self.open_todo_manager),
            
            # 表示
            ("ダークモード切り替え", "Ctrl+D", self.toggle_dark_mode),
            ("フォント設定", "", self.open_font_settings),
            
            # ヘッダー挿入
            ("TITLE挿入", "", lambda: self.insert_with_input("TITLE:", "曲名を入力")),
            ("SUBTITLE挿入", "", lambda: self.insert_with_input("SUBTITLE:", "サブタイトルを入力")),
            ("BPM挿入", "", lambda: self.insert_with_input("BPM:", "BPMを入力", "120")),
            ("LEVEL挿入", "", lambda: self.insert_with_input("LEVEL:", "レベル (1-10)", "7")),
            ("OFFSET挿入", "", lambda: self.insert_with_input("OFFSET:", "オフセット(秒)", "0")),
            ("WAVE挿入(BPM自動取得)", "", self.insert_wave_with_bpm),
            
            # 譜面コマンド
            ("#START挿入", "", lambda: self.insert_syntax("#START\n")),
            ("#END挿入", "", lambda: self.insert_syntax("#END\n")),
            ("#GOGOSTART挿入", "", lambda: self.insert_syntax("#GOGOSTART\n")),
            ("#GOGOEND挿入", "", lambda: self.insert_syntax("#GOGOEND\n")),
            ("#BPMCHANGE挿入", "", lambda: self.insert_with_input("#BPMCHANGE ", "新しいBPM", "120")),
            ("#SCROLL挿入", "", lambda: self.insert_with_input("#SCROLL ", "スクロール速度", "1.0")),
            
            # ツール
            ("エラーチェック", "Ctrl+Shift+E", self.check_errors),
            ("BPMカウンター", "", self.open_bpm_counter),
            ("OFFSET一括調整", "", self.open_offset_adjuster),
            ("AI添削", "", self.ai_autoreview),
            ("配布用ZIP作成", "Ctrl+E", self.create_distribution_zip),
            ("バックアップ比較", "", self.open_backup_compare),
            ("バックアップ履歴", "", self.show_backup_history),
            ("バックアップフォルダを開く", "", self.open_backup_folder),
            
            # プレビュー
            ("太鼓さん次郎でプレビュー", "F5", self.preview_play),
            ("太鼓さん次郎のパス設定", "", self.reset_taikojiro_path),
            
            # 段位道場
            ("段位道場設定", "", self.open_dan_window),
        ]
        
        # 初期表示
        self.update_command_list("")
        
        # イベントバインド
        self.palette_entry.bind("<KeyRelease>", self.on_palette_search)
        self.palette_entry.bind("<Return>", lambda e: self.execute_selected_command())
        self.palette_entry.bind("<Down>", lambda e: self.move_selection(1))
        self.palette_entry.bind("<Up>", lambda e: self.move_selection(-1))
        self.palette_entry.bind("<Escape>", lambda e: self.palette_window.destroy())
        
        self.palette_listbox.bind("<Double-Button-1>", lambda e: self.execute_selected_command())
        self.palette_listbox.bind("<Return>", lambda e: self.execute_selected_command())
        
        # 最初の項目を選択
        if self.palette_listbox.size() > 0:
            self.palette_listbox.selection_set(0)
            self.palette_listbox.activate(0)
    
    def on_palette_search(self, event):
        """検索ボックスの入力時"""
        query = self.palette_entry.get()
        self.update_command_list(query)
    
    def update_command_list(self, query):
        """コマンドリストを更新（曖昧検索対応）"""
        self.palette_listbox.delete(0, tk.END)
        
        query_lower = query.lower()
        
        # 曖昧検索: クエリの各文字が順番に含まれているかチェック
        for name, shortcut, func in self.commands:
            name_lower = name.lower()
            
            # 完全一致または部分一致
            if query_lower in name_lower:
                display = f"{name}"
                if shortcut:
                    display += f"  ({shortcut})"
                self.palette_listbox.insert("end", display)
            # 曖昧検索（各文字が順番に含まれる）
            elif self.fuzzy_match(query_lower, name_lower):
                display = f"{name}"
                if shortcut:
                    display += f"  ({shortcut})"
                self.palette_listbox.insert("end", display)
        
        # 結果がない場合
        if self.palette_listbox.size() == 0:
            self.palette_listbox.insert("end", "(該当するコマンドがありません)")
        else:
            self.palette_listbox.selection_set(0)
            self.palette_listbox.activate(0)
    
    def fuzzy_match(self, query, text):
        """曖昧検索マッチング"""
        query_idx = 0
        for char in text:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1
        return query_idx == len(query)
    
    def move_selection(self, delta):
        """選択を上下に移動"""
        current = self.palette_listbox.curselection()
        if not current:
            return "break"
        
        current_idx = current[0]
        new_idx = current_idx + delta
        
        if 0 <= new_idx < self.palette_listbox.size():
            self.palette_listbox.selection_clear(0, tk.END)
            self.palette_listbox.selection_set(new_idx)
            self.palette_listbox.activate(new_idx)
            self.palette_listbox.see(new_idx)
        
        return "break"
    
    def execute_selected_command(self):
        """選択したコマンドを実行"""
        selection = self.palette_listbox.curselection()
        if not selection:
            return
        
        selected_text = self.palette_listbox.get(selection[0])
        
        # "(該当するコマンドがありません)" の場合は何もしない
        if selected_text.startswith("("):
            return
        
        # コマンド名を抽出（ショートカット部分を除去）
        command_name = selected_text.split("  (")[0]
        
        # 該当するコマンドを実行
        for name, shortcut, func in self.commands:
            if name == command_name:
                self.palette_window.destroy()
                try:
                    func()
                except Exception as e:
                    messagebox.showerror("エラー", f"コマンドの実行に失敗しました。\n{e}")
                break

    def show_backup_history(self):
        """バックアップ履歴を見やすく表示して復元可能にする"""
        if not self.current_file:
            messagebox.showwarning("未保存", "ファイルを保存してください")
            return
        
        backup_dir = os.path.join(os.path.dirname(self.current_file), ".backup")
        if not os.path.exists(backup_dir):
            messagebox.showinfo("バックアップなし", "まだバックアップが作成されていません")
            return
        
        # 現在のファイル名に関連するバックアップだけ抽出
        current_basename = os.path.basename(self.current_file)
        backups = []
        for fname in os.listdir(backup_dir):
            if fname.endswith(current_basename):
                full_path = os.path.join(backup_dir, fname)
                # タイムスタンプ部分を抽出（例: "2025-12-05_14-30-45"）
                timestamp_str = fname.split("_")[0] + "_" + fname.split("_")[1]
                try:
                    # 人間が読みやすい形式に変換
                    dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                    display_time = dt.strftime("%Y年%m月%d日 %H:%M:%S")
                    backups.append((display_time, full_path))
                except:
                    pass
        
        if not backups:
            messagebox.showinfo("バックアップなし", f"{current_basename} のバックアップはありません")
            return
        
        # 新しい順にソート
        backups.sort(reverse=True)
        
        # ダイアログ表示
        win = Toplevel(self.root)
        win.title(f"バックアップ履歴 - {current_basename}")
        win.geometry("600x400")
        win.transient(self.root)
        
        Label(win, text=f"「{current_basename}」のバックアップ履歴", 
              font=("メイリオ", 12, "bold")).pack(pady=10)
        
        frame = Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        scrollbar = Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        
        listbox = Listbox(frame, yscrollcommand=scrollbar.set, 
                         font=("MS Gothic", 10), selectmode="single")
        for display_time, _ in backups:
            listbox.insert("end", display_time)
        listbox.pack(fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        def restore_backup():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("未選択", "復元するバックアップを選択してください", parent=win)
                return
            
            selected_time, selected_path = backups[sel[0]]
            
            if not messagebox.askyesno(
                "復元確認",
                f"以下のバックアップを復元しますか？\n\n"
                f"【復元元】\n{selected_time}\n\n"
                f"※現在の編集内容は失われます（上書き保存していれば別のバックアップに残ります）",
                parent=win
            ):
                return
            
            try:
                with open(selected_path, 'r', encoding=self.current_encoding, errors='replace') as f:
                    content = f.read()
                
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", content)
                self.text.edit_modified(False)
                
                win.destroy()
                messagebox.showinfo("復元完了", f"{selected_time} のバックアップを復元しました")
                self.update_all()
                
            except Exception as e:
                messagebox.showerror("復元エラー", f"バックアップの復元に失敗しました\n{e}", parent=win)
        
        def open_folder():
            if os.name == "nt":
                os.startfile(backup_dir)
            else:
                import subprocess
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", backup_dir])
        
        btn_frame = Frame(win)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="復元", command=restore_backup, width=12, 
               font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="フォルダを開く", command=open_folder, width=14, 
               font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="閉じる", command=win.destroy, width=12, 
               font=("メイリオ", 10)).pack(side="left", padx=5)

    def open_search(self):
        # すでにウィンドウが存在する場合は最前面に持ってくるだけ
        if hasattr(self, 'search_window') and self.search_window is not None:
            try:
                if self.search_window.winfo_exists():
                    self.search_window.lift()
                    self.search_window.focus_force()
                    if hasattr(self, 'search_entry'):
                        self.search_entry.focus_set()
                    return
            except:
                pass
            # 存在チェック失敗時はクリーンアップ
            self.search_window = None
    
        # 新規作成
        self.search_window = Toplevel(self.root)
        self.search_window.title("検索")
        self.search_window.geometry("560x110")
        self.search_window.resizable(False, False)
        self.search_window.transient(self.root)
        self.search_window.grab_set()
        self.search_window.focus_force()
    
        # ← 閉じるボタンやXボタンで確実にクリーンアップ
        def on_search_close():
            self.clear_search_highlight()
            try:
                self.root.unbind_all("<F3>")
                self.root.unbind_all("<Shift-F3>")
            except:
                pass
            if self.search_window:
                self.search_window.destroy()
            self.search_window = None
    
        self.search_window.protocol("WM_DELETE_WINDOW", on_search_close)
    
        # メインフレーム
        main_frame = tk.Frame(self.search_window)
        main_frame.pack(padx=15, pady=15, fill=tk.X)
    
        # 検索ボックス
        tk.Label(main_frame, text="検索:", font=("メイリオ", 10)).pack(side=tk.LEFT)
        self.search_entry = tk.Entry(main_frame, font=("メイリオ", 11), width=40)
        self.search_entry.pack(side=tk.LEFT, padx=(5, 15), fill=tk.X, expand=True)
        self.search_entry.focus_set()
    
        # ボタンフレーム
        btn_frame = tk.Frame(self.search_window)
        btn_frame.pack(pady=(0, 10))
    
        tk.Button(btn_frame, text="次を検索 (F3)", width=14, command=self.find_next).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="前を検索 (Shift+F3)", width=14, command=self.find_prev).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="閉じる", width=10, command=on_search_close).pack(side=tk.LEFT, padx=20)
    
        # Enterで次検索、Shift+Enterで前検索
        self.search_entry.bind("<Return>", lambda e: self.find_next())
        self.search_entry.bind("<Shift-Return>", lambda e: self.find_prev())
    
        # グローバルショートカット(F3 / Shift+F3)も有効化
        self.root.bind_all("<F3>", lambda e: self.find_next() if self.search_window else None)
        self.root.bind_all("<Shift-F3>", lambda e: self.find_prev() if self.search_window else None)
    
        # 検索位置リセット
        self.search_positions = []
        self.current_match = -1
        
    def close_search(self):
        if self.search_window:
            self.clear_search_highlight()
            self.search_window.destroy()
            self.search_window = None

    def clear_search_highlight(self):
        if hasattr(self, 'text'):
            self.text.tag_remove("search", "1.0", tk.END)
            self.text.tag_remove(tk.SEL, "1.0", tk.END)

    def find_next(self):
        if not hasattr(self, 'search_entry') or not self.search_entry:
            return
        query = self.search_entry.get().strip()
        if not query:
            return
        self.clear_search_highlight()
        self.search_text(query, forward=True)

    def find_prev(self):
        query = self.search_entry.get()
        if not query: return
        self.clear_search_highlight()
        self.search_text(query, forward=False)
        
    def _on_enter_press(self, event=None):
        if not self.enter_held:
            self.enter_held = True
            self._update_line_numbers_loop()
        return None  # 通常のEnter動作を妨げない
    
    def _on_enter_release(self, event=None):
        self.enter_held = False
    
    def _update_line_numbers_loop(self):
        if self.enter_held:
            self.update_line_numbers()  # ← 既存の行番号更新関数
            self.root.after(50, self._update_line_numbers_loop)  # 50msごとに再実行
            
    def search_text(self, query, forward=True):
        self.clear_search_highlight()
        self.search_positions = []
        start = "1.0"
        while True:
            pos = self.text.search(query, start, stopindex=tk.END, regexp=False)
            if not pos: break
            end = f"{pos} + {len(query)}c"
            self.search_positions.append((pos, end))
            self.text.tag_add("search", pos, end)
            start = end
        if not self.search_positions:
            messagebox.showinfo("検索", "見つかりませんでした")
            return
        cursor = self.text.index(tk.INSERT)
        if forward:
            for i, (pos, _) in enumerate(self.search_positions):
                if self.text.compare(pos, ">=", cursor):
                    self.current_match = i
                    break
            else:
                self.current_match = 0
        else:
            for i in range(len(self.search_positions)-1, -1, -1):
                pos, _ = self.search_positions[i]
                if self.text.compare(pos, "<=", cursor):
                    self.current_match = i
                    break
            else:
                self.current_match = len(self.search_positions)-1
        pos, end = self.search_positions[self.current_match]
        self.text.see(pos)
        self.text.tag_add(tk.SEL, pos, end)
        self.text.mark_set(tk.INSERT, end)

    def insert_syntax(self, syntax):
        self.text.insert(tk.INSERT, syntax)
        self.text.see(tk.INSERT)
        self.root.after_idle(self.update_all)

    def insert_with_input(self, prefix, prompt, default=""):
        val = simpledialog.askstring("入力", prompt, initialvalue=default)
        if val is not None:
            self.insert_syntax(prefix + val + "\n")

    def insert_measure(self):
        m = simpledialog.askstring("小節", "小節を入力（例: 4/4）", initialvalue="4/4")
        if m:
            self.insert_syntax(f"#MEASURE {m}\n")

    def insert_branchstart(self):
        p = simpledialog.askstring("分岐条件", "精度条件（%）", initialvalue="90")
        r = simpledialog.askstring("分岐条件", "ロール条件", initialvalue="10")
        if p is not None and r is not None:
            self.insert_syntax(f"#BRANCHSTART {p},{r}\n")

    def insert_course_only(self, course):
        self.insert_syntax(f"COURSE:{course}\n")

    def insert_wave_with_bpm(self):
        # librosa がなくても警告が出ない安全なインポートに変更
        if not LIBROSA_AVAILABLE:
            # librosa がないときは手動で WAVE と BPM を入力させる（超便利になるよ！）
            wave_name = simpledialog.askstring("WAVEファイル名", "WAVE: に記入するファイル名を入力してください（例: song.ogg）")
            if wave_name is None:
                return
            if not wave_name.strip():
                wave_name = "song.ogg"

            bpm_input = simpledialog.askfloat("BPM入力", "BPMを手動で入力してください", minvalue=30, maxvalue=300, initialvalue=140.0)
            if bpm_input is None:
                return

            wave_line = f"WAVE:{wave_name.strip()}\n"
            bpm_line = f"BPM:{bpm_input:.2f}\n"

            self.text.insert(tk.INSERT, wave_line + bpm_line)
            self.text.see(tk.INSERT)
            self.root.after_idle(self.update_all)
            messagebox.showinfo("完了", f"WAVE と BPM を手動で挿入しました！\n\nWAVE:{wave_name.strip()}\nBPM:{bpm_input:.2f}")
            return

        # ← ここから下は librosa があるときの処理（numba警告が出ないように修正済み）
        path = filedialog.askopenfilename(
            title="音声ファイルを選択（OGG/WAV対応）",
            filetypes=[("音声ファイル", "*.ogg *.wav *.mp3")]
        )
        if not path:
            return

        try:
            # numbaのFutureWarningを完全に抑える安全な読み込み方
            import librosa.core as lc
            y, sr = lc.load(path, sr=None, mono=True)
            # beat_track の代わりに軽量な onset 検出 + tempo 推定
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            bpm = round(float(tempo), 2)

        except Exception as e:
            # 何か失敗したら手動入力にフォールバック（超親切仕様に！）
            bpm_input = simpledialog.askfloat(
                "BPM自動取得失敗",
                f"音声解析に失敗しました…\n{os.path.basename(path)}\n\n手動でBPMを入力してください",
                minvalue=30, maxvalue=300, initialvalue=140.0
            )
            if bpm_input is None:
                return
            bpm = round(bpm_input, 2)

        wave = f"WAVE:{os.path.basename(path)}\n"
        bpm_line = f"BPM:{bpm}\n"
        self.text.insert(tk.INSERT, wave + bpm_line)
        self.text.see(tk.INSERT)
        self.root.after_idle(self.update_all)
        messagebox.showinfo("成功", f"{os.path.basename(path)}\nBPM: {bpm} を自動取得＆挿入しました")

    def open_dan_window(self):
        if hasattr(self, 'dan_window') and self.dan_window and self.dan_window.winfo_exists():
            self.dan_window.lift()
            return
        
        # === 必要な属性を関数内で定義 ===
        self.exam_types = ["魂ゲージ", "良の数", "可の数", "不可の数", "スコア", "連打数", "叩けた数", "最大コンボ数"]
        self.exam_codes = {"魂ゲージ":"g","良の数":"jp","可の数":"jg","不可の数":"jb","スコア":"s","連打数":"r","叩けた数":"h","最大コンボ数":"c"}
        self.comparisons_jp = ["～以上", "～未満"]
        self.comparisons = {"～以上":"m", "～未満":"l"}
        # =============================
        
        self.song_paths.clear()
        self.song_courses_temp.clear()
        self.song_course_values.clear()
        self.song_levels.clear()
        self.song_genres.clear()
        self.song_scoreinit.clear()
        self.song_scorediff.clear()
        self.dan_window = Toplevel(self.root)
        self.dan_window.protocol("WM_DELETE_WINDOW", self._close_dan_window)
        self.dan_window.title("段位道場設定")
        # 共通合格条件が収まる固定サイズに設定
        self.dan_window.geometry("1400x700")
        self.dan_window.resizable(False, False)  # サイズ固定
        
        # スクロール対応のメインフレーム
        main_frame = Frame(self.dan_window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # カラム分割（左：曲リスト、右：設定）
        left_frame = Frame(main_frame, width=350, relief="ridge", bd=2)
        left_frame.pack(side="left", fill="both", padx=(0, 5))
        left_frame.pack_propagate(False)
        
        right_frame = Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)
        
        # === 左フレーム: 曲リストと操作 ===
        # セクションタイトル
        Label(left_frame, text="■ 曲リスト", 
              font=("メイリオ", 12, "bold"), bg="#e0e0e0", fg="#333333",
              anchor="w", padx=10, pady=8).pack(fill="x")
        
        # タイトル入力（コンパクトに）
        title_frame = Frame(left_frame, padx=10, pady=5)
        title_frame.pack(fill="x", pady=(0, 5))
        Label(title_frame, text="TITLE:", font=("メイリオ", 10)).pack(side="left", padx=(0, 5))
        self.dan_title_entry = Entry(title_frame, font=("メイリオ", 10))
        self.dan_title_entry.pack(side="left", fill="x", expand=True)
        
        # ジャンル選択（コンパクトに）
        genre_frame = Frame(left_frame, padx=10, pady=5)
        genre_frame.pack(fill="x", pady=(0, 10))
        Label(genre_frame, text="ジャンル:", font=("メイリオ", 10)).pack(side="left", padx=(0, 5))
        if not hasattr(self, 'dan_genre_var'):
            self.dan_genre_var = tk.StringVar(value="金")
        genre_combo = ttk.Combobox(genre_frame, textvariable=self.dan_genre_var,
                                   values=["黄", "青", "赤", "銀", "金"],
                                   state="readonly", width=8, font=("メイリオ", 10))
        genre_combo.pack(side="left")
        
        # 曲リスト（スクロール対応）
        list_container = Frame(left_frame)
        list_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        list_scroll = Scrollbar(list_container)
        list_scroll.pack(side="right", fill="y")
        
        self.song_listbox = Listbox(list_container, 
                                    yscrollcommand=list_scroll.set,
                                    font=("MS Gothic", 10),
                                    selectmode=tk.SINGLE,
                                    height=12,
                                    relief="sunken",
                                    bd=2)
        self.song_listbox.pack(fill="both", expand=True)
        list_scroll.config(command=self.song_listbox.yview)
        
        # 曲追加ボタン（ステータス表示付き）
        add_remove_frame = Frame(left_frame)
        add_remove_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        self.add_button = Button(add_remove_frame, 
                                 text="曲を追加 (3曲まで)",
                                 command=self.add_song,
                                 font=("メイリオ", 10),
                                 bg="#4CAF50",
                                 fg="white",
                                 width=20)
        self.add_button.pack(side="left", padx=(0, 5))
        
        Button(add_remove_frame, 
               text="削除",
               command=self.remove_song,
               font=("メイリオ", 10),
               width=8).pack(side="left", padx=2)
        
        # 移動ボタン
        move_frame = Frame(left_frame)
        move_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        Button(move_frame, 
               text="▲ 上に移動",
               command=self.move_up,
               font=("メイリオ", 9),
               width=12).pack(side="left", padx=2)
        Button(move_frame, 
               text="▼ 下に移動",
               command=self.move_down,
               font=("メイリオ", 9),
               width=12).pack(side="left", padx=2)
        
        # === 右フレーム: 詳細設定 ===
        # タブ形式の設定エリア
        notebook = ttk.Notebook(right_frame)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # タブ1: 曲詳細設定
        song_tab = Frame(notebook)
        notebook.add(song_tab, text="各曲の詳細設定")
        
        # 曲設定フレーム（スクロール対応）
        song_scroll = Scrollbar(song_tab)
        song_scroll.pack(side="right", fill="y")
        
        song_canvas = tk.Canvas(song_tab, yscrollcommand=song_scroll.set)
        song_canvas.pack(side="left", fill="both", expand=True)
        song_scroll.config(command=song_canvas.yview)
        
        song_inner_frame = Frame(song_canvas)
        song_canvas.create_window((0, 0), window=song_inner_frame, anchor="nw")
        
        self.song_settings_frame = Frame(song_inner_frame, padx=10, pady=10)
        self.song_settings_frame.pack(fill="x")
        
        def update_song_scrollregion(event):
            song_canvas.configure(scrollregion=song_canvas.bbox("all"))
        
        song_inner_frame.bind("<Configure>", update_song_scrollregion)
        
        # 初期表示メッセージ
        Label(self.song_settings_frame, 
              text="曲を追加すると、ここに各曲の詳細設定が表示されます。",
              font=("メイリオ", 12),
              fg="gray",
              pady=20).pack()
        
        # タブ2: 合格条件設定
        condition_tab = Frame(notebook)
        notebook.add(condition_tab, text="合格条件")
        
        # 合格条件設定（スクロール対応）
        cond_scroll = Scrollbar(condition_tab)
        cond_scroll.pack(side="right", fill="y")
        
        cond_canvas = tk.Canvas(condition_tab, yscrollcommand=cond_scroll.set)
        cond_canvas.pack(side="left", fill="both", expand=True)
        cond_scroll.config(command=cond_canvas.yview)
        
        cond_inner_frame = Frame(cond_canvas, padx=15, pady=15)
        cond_canvas.create_window((0, 0), window=cond_inner_frame, anchor="nw")
        
        # 共通合格条件セクション
        common_frame = LabelFrame(cond_inner_frame, 
                                  text="共通合格条件 (全ての曲に適用)",
                                  font=("メイリオ", 11, "bold"),
                                  padx=15,
                                  pady=15,
                                  bg="#f8f8f8",
                                  relief="groove")
        common_frame.pack(fill="x", pady=(0, 15))
        
        # グリッドレイアウトで条件を整列（横幅に収まるように調整）
        self.common_type_combos = {}
        self.common_comp_combos = {}
        self.common_normal_entries = {}
        self.common_gold_entries = {}
        self.per_song_vars = {}
        self.per_song_frames = {}
        self.per_song_widgets = {}
        self.per_song_order = []
                
        # 説明ラベル
        Label(common_frame, 
              text="以下の条件は全ての曲に共通で適用されます。\n特定の曲だけ異なる条件を設定したい場合は「曲ごとに設定」にチェックを入れてください。",
              font=("メイリオ", 9),
              fg="#666666",
              bg="#f8f8f8",
              justify="left").pack(pady=(0, 10))
        
        # 共通条件の各項目の幅設定（1150pxに収まるように調整）
        column_widths = {
            'label': 6,    # 項目ラベル（少し狭く）
            'type': 14,     # 条件タイプ
            'comp': 8,      # 比較方法
            'normal': 8,    # 通常条件
            'gold': 8,      # 金条件
            'checkbox': 12  # チェックボックス
        }
        
        # 共通条件を配置するためのメインフレーム
        common_items_frame = Frame(common_frame, bg="#f8f8f8")
        common_items_frame.pack(fill="x", padx=5)
        
        self.common_type_combos = {}
        self.common_comp_combos = {}
        self.common_normal_entries = {}
        self.common_gold_entries = {}
        self.per_song_vars = {}
        self.per_song_frames = {}
        self.per_song_widgets = {}
        self.per_song_order = []
        
        for idx, (typ, comp, n, g) in enumerate(self.DAN_DEFAULTS):
            item = self.DAN_ITEMS[idx]
            
            # 各条件のフレーム
            item_frame = Frame(common_items_frame, bg="#f8f8f8")
            item_frame.pack(fill="x", pady=2, padx=5)
            
            # 項目ラベル - 左側に配置
            label_frame = Frame(item_frame, bg="#f8f8f8")
            label_frame.pack(side="left", padx=(0, 5))
            Label(label_frame, text=f"{item}:", 
                  font=("メイリオ", 10, "bold"),
                  width=column_widths['label'],
                  anchor="w",
                  bg="#f8f8f8").pack()
            
            # 設定ウィジェットのフレーム
            settings_frame = Frame(item_frame, bg="#f8f8f8")
            settings_frame.pack(side="left", fill="x", expand=True)
            
            # 条件タイプ選択
            tc = ttk.Combobox(settings_frame, 
                              values=self.exam_types, 
                              width=column_widths['type'],
                              state="readonly",
                              font=("メイリオ", 9))
            tc.pack(side="left", padx=2)
            tc.set(typ)
            
            # 比較方法選択
            cc = ttk.Combobox(settings_frame, 
                              values=self.comparisons_jp,
                              width=column_widths['comp'],
                              state="readonly",
                              font=("メイリオ", 9))
            cc.pack(side="left", padx=2)
            cc.set(comp)
            
            # 通常条件
            ne = Entry(settings_frame, 
                       width=column_widths['normal'],
                       font=("メイリオ", 9),
                       justify="center",
                       bg="#ffffff",
                       relief="sunken",
                       bd=1)
            ne.pack(side="left", padx=2)
            ne.insert(0, n)
            
            Label(settings_frame, text=" / ", 
                  font=("メイリオ", 9),
                  bg="#f8f8f8").pack(side="left", padx=1)
            
            # 金条件
            ge = Entry(settings_frame, 
                       width=column_widths['gold'],
                       font=("メイリオ", 9),
                       justify="center",
                       bg="#fffacd",
                       relief="sunken",
                       bd=1)
            ge.pack(side="left", padx=2)
            ge.insert(0, g)
            
            # 右側のチェックボックスフレーム
            checkbox_frame = Frame(settings_frame, bg="#f8f8f8")
            checkbox_frame.pack(side="right", padx=(10, 0))
            
            # 曲ごと設定チェックボックス
            var = tk.IntVar(value=0)
            cb = Checkbutton(checkbox_frame, 
                             text="曲ごとに設定",
                             variable=var,
                             command=lambda i=item: self.toggle_per_song(i),
                             font=("メイリオ", 9),
                             bg="#f8f8f8")
            cb.pack()
            
            # ウィジェットを保存
            self.common_type_combos[item] = tc
            self.common_comp_combos[item] = cc
            self.common_normal_entries[item] = ne
            self.common_gold_entries[item] = ge
            self.per_song_vars[item] = var
            
            # 個別設定フレーム（初期非表示） - cond_inner_frame内に配置
            pf = Frame(cond_inner_frame, padx=10, pady=10, bg="#f0f8ff", relief="ridge", bd=1)
            pf.pack_forget()
            self.per_song_frames[item] = pf
            self.per_song_widgets[item] = []
            
            self.update_common_state(item)
        
        # 共通アイテムフレームのサイズ調整
        common_items_frame.update_idletasks()
        
        # スクロール領域更新
        cond_inner_frame.bind("<Configure>", 
                             lambda e: cond_canvas.configure(scrollregion=cond_canvas.bbox("all")))
        
        # ========== 生成ボタンフレーム（右フレーム下部に配置）==========
        button_frame = Frame(right_frame, pady=10)
        button_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        
        self.gen_btn = Button(button_frame, 
                              text="TJAを生成して保存",
                              command=self.generate_dan_code,
                              font=("メイリオ", 12, "bold"),
                              bg="#2196F3",
                              fg="white",
                              padx=30,
                              pady=10,
                              relief="raised",
                              borderwidth=3)
        self.gen_btn.pack()
        
        # 初期化
        self.update_add_button()
        
        # ウィンドウ設定 - サイズ固定
        self.dan_window.minsize(1150, 700)
        self.dan_window.maxsize(1150, 700)
        
        # 初回表示
        self.update_song_settings()
    
    def _close_dan_window(self):
        # ← マウスホイールバインディング解除
        if hasattr(self, 'dan_window') and self.dan_window:
            try:
                self.dan_window.unbind_all("<MouseWheel>")
            except:
                pass
        
        # ← ウィジェット完全破棄
        if hasattr(self, 'per_song_widgets'):
            for item in self.per_song_widgets:
                for widget_tuple in self.per_song_widgets[item]:
                    for w in widget_tuple:
                        try:
                            if w.winfo_exists():
                                w.destroy()
                        except:
                            pass
        
        if self.dan_window:
            self.dan_window.destroy()
            self.dan_window = None
    
        # 不要な曲設定を削除(曲数に合わせて整理)
        if hasattr(self, 'song_courses_temp'):
            self.song_courses_temp = {
                i: self.song_courses_temp[i]
                for i in range(len(self.song_paths))
                if i in self.song_courses_temp
            }
    
        if hasattr(self, 'song_settings_frame') and self.song_settings_frame:
            try:
                self.update_song_settings()
            except:
                pass

    def toggle_per_song(self, item):
        var = self.per_song_vars[item]
        is_per_song = var.get()  # True=曲ごと、False=共通
    
        frame = self.per_song_frames[item]
    
        if is_per_song:
            # チェックON → フレーム表示
            if item not in self.per_song_order:
                self.per_song_order.append(item)
            
            # cond_inner_frame内に配置（合格条件タブ内）
            frame.pack(pady=15, fill=tk.X)
            
            # ウィジェットを作成
            if item not in self.per_song_widgets or len(self.per_song_widgets[item]) == 0:
                self.create_per_song_widgets(item)
        else:
            # チェックOFF → フレーム非表示
            frame.pack_forget()
            if item in self.per_song_order:
                self.per_song_order.remove(item)
    
            # ウィジェットを完全に削除
            if item in self.per_song_widgets:
                for widget_tuple in self.per_song_widgets[item]:
                    for w in widget_tuple:
                        try:
                            w.destroy()
                        except:
                            pass
                self.per_song_widgets[item] = []
    
        # 共通設定の有効/無効切り替え
        self.update_common_state(item)

    def update_common_state(self, item):
        state = "disabled" if self.per_song_vars[item].get() else "readonly"
        bg = "#f0f0f0" if self.per_song_vars[item].get() else "white"
        self.common_type_combos[item].config(state=state)
        self.common_comp_combos[item].config(state=state)
        self.common_normal_entries[item].config(state="disabled" if self.per_song_vars[item].get() else "normal", bg=bg)
        self.common_gold_entries[item].config(state="disabled" if self.per_song_vars[item].get() else "normal", bg=bg)

    def create_per_song_widgets(self, item):
        frame = self.per_song_frames[item]
        
        # フレームをクリア
        for widget in frame.winfo_children():
            widget.destroy()
        
        # タイトルフレーム
        title_frame = Frame(frame, bg="#f0f8ff")
        title_frame.pack(fill="x", pady=(0, 5))
        Label(title_frame, text=f"【{item}】 曲ごとの設定", 
              font=("メイリオ", 10, "bold"), bg="#f0f8ff").pack(anchor="w")
        
        self.per_song_widgets[item] = []
        
        # 各曲の設定（最大3曲）
        for i in range(3):
            song_frame = Frame(frame, bg="#f0f8ff")
            song_frame.pack(fill="x", pady=2)
            
            # 曲番号ラベル
            Label(song_frame, text=f"曲{i+1}:", font=("MS Gothic", 10), 
                  bg="#f0f8ff", width=6, anchor="w").pack(side="left", padx=(5, 5))
            
            # 条件タイプ選択（少し狭く）
            tc = ttk.Combobox(song_frame, values=self.exam_types, width=12, 
                             state="readonly", font=("MS Gothic", 9))
            tc.pack(side="left", padx=2)
            tc.set(self.common_type_combos[item].get())
            
            # 比較方法選択
            cc = ttk.Combobox(song_frame, values=self.comparisons_jp, width=8, 
                             state="readonly", font=("MS Gothic", 9))
            cc.pack(side="left", padx=2)
            cc.set(self.common_comp_combos[item].get())
            
            # 通常条件
            ne = Entry(song_frame, width=8, font=("MS Gothic", 9))
            ne.pack(side="left", padx=2)
            ne.insert(0, self.common_normal_entries[item].get())
            
            # スラッシュ
            Label(song_frame, text="/", font=("MS Gothic", 11), bg="#f0f8ff").pack(side="left", padx=2)
            
            # 金条件
            ge = Entry(song_frame, width=8, font=("MS Gothic", 9))
            ge.pack(side="left", padx=2)
            ge.insert(0, self.common_gold_entries[item].get())
            
            self.per_song_widgets[item].append((tc, cc, ne, ge))
        
        # フレームのサイズを調整
        frame.update_idletasks()

    def update_song_settings(self):
        if not hasattr(self, 'song_listbox') or not self.song_listbox.winfo_exists():
            return
        
        self.song_listbox.delete(0, tk.END)
        if self.song_paths:
            for i, path in enumerate(self.song_paths):
                # ファイル名を短く表示
                fname = os.path.basename(path)
                if len(fname) > 25:
                    fname = fname[:22] + "..."
                self.song_listbox.insert(tk.END, f"{i+1}. {fname}")
        else:
            self.song_listbox.insert(tk.END, "（曲を追加してください）")
    
        # フレームは必ず最初から作成
        container = self.dan_window.winfo_children()[0].winfo_children()[0]
        if not hasattr(self, 'song_settings_frame') or not self.song_settings_frame.winfo_exists():
            self.song_settings_frame = LabelFrame(container, text="■ 各曲の設定 ■", 
                                                font=("メイリオ", 11, "bold"), padx=8, pady=8)
            self.song_settings_frame.pack(fill=tk.X, pady=(8, 0), before=self.gen_btn)
    
        for w in self.song_settings_frame.winfo_children():
            w.destroy()
    
        course_names = ["Easy", "Normal", "Hard", "Oni", "Edit"]
        course_jp   = ["かんたん", "ふつう", "むずかしい", "鬼", "裏鬼"]
        genres = ["ポップス","キッズ","アニメ","ボーカロイド","ゲームミュージック","バラエティ","クラシック","ナムコオリジナル"]
    
        # ウィジェットの幅を調整（横幅1150pxに収まるように）
        column_widths = {
            0: 4,    # 曲番号
            1: 28,   # ファイル名
            2: 12,   # 難易度
            3: 4,    # LEVEL
            4: 6,    # GENREラベル
            5: 20,   # GENRE選択（少し狭く）
            6: 5,    # INITラベル
            7: 7,    # INIT入力
            8: 5,    # DIFFラベル
            9: 7     # DIFF入力
        }
    
        for i in range(max(len(self.song_paths), 1)):
            row = Frame(self.song_settings_frame)
            row.pack(fill=tk.X, pady=2)
    
            if i < len(self.song_paths):
                path = self.song_paths[i]
                fname = os.path.basename(path)
                # ファイル名表示を短く
                disp = fname if len(fname) <= 20 else fname[:17] + "..."
    
                # 曲番号
                Label(row, text=f"曲{i+1}", font=("MS Gothic", 10, "bold"), 
                      width=column_widths[0], anchor="w").grid(row=0, column=0, padx=(2,2), sticky="w")
    
                # ファイル名
                Label(row, text=disp, font=("MS Gothic", 9), fg="#333399", 
                      anchor="w", width=column_widths[1]).grid(row=0, column=1, padx=(0,2), sticky="w")
    
                # 難易度選択
                avail = self.song_course_values.get(i, [])
                avail_jp = [course_jp[course_names.index(c)] for c in avail if c in course_names]
                cur = self.song_courses_temp.get(i, avail_jp[0] if avail_jp else "鬼")
                cbox = ttk.Combobox(row, values=avail_jp, width=column_widths[2]-2, 
                                   font=("MS Gothic", 9), state="readonly")
                cbox.set(cur)
                cbox.grid(row=0, column=2, padx=2, sticky="w")
                cbox.bind("<<ComboboxSelected>>", lambda e, idx=i, cb=cbox: self.on_course_changed(idx, cb))
    
                # LEVEL表示
                lv = self.song_levels.get(i, "?")
                Label(row, text=f"★{lv}", font=("MS Gothic", 10), fg="#0066cc", 
                      width=column_widths[3], anchor="w").grid(row=0, column=3, padx=2, sticky="w")
    
                # GENRE選択
                Label(row, text="GENRE:", font=("MS Gothic", 9, "bold"), fg="#008800",
                      width=column_widths[4], anchor="w").grid(row=0, column=4, padx=(8,1), sticky="w")
                gbox = ttk.Combobox(row, values=genres, width=column_widths[5]-2, 
                                   font=("MS Gothic", 8), state="readonly")
                gbox.set(self.song_genres.get(i, "ナムコオリジナル"))
                gbox.grid(row=0, column=5, padx=1, sticky="w")
                gbox.bind("<<ComboboxSelected>>", lambda e, idx=i: self.song_genres.__setitem__(idx, gbox.get()))
    
                # INIT
                Label(row, text="INIT:", font=("MS Gothic", 9, "bold"), fg="#0000aa",
                      width=column_widths[6], anchor="w").grid(row=0, column=6, padx=(8,1), sticky="w")
                init_e = Entry(row, width=column_widths[7], font=("MS Gothic", 9), 
                              justify="center", bg="#f0f8ff")
                init_e.insert(0, self.song_scoreinit.get(i, ""))
                init_e.grid(row=0, column=7, padx=1, sticky="w")
    
                # DIFF
                Label(row, text="DIFF:", font=("MS Gothic", 9, "bold"), fg="#cc4400",
                      width=column_widths[8], anchor="w").grid(row=0, column=8, padx=(6,1), sticky="w")
                diff_e = Entry(row, width=column_widths[9], font=("MS Gothic", 9), 
                              justify="center", bg="#fff0f0")
                diff_e.insert(0, self.song_scorediff.get(i, ""))
                diff_e.grid(row=0, column=9, padx=1, sticky="w")
    
            else:
                Label(row, text="曲を追加すると設定がここに表示されます", 
                      font=("MS Gothic", 9), fg="#999999")\
                    .grid(row=0, column=0, columnspan=10, pady=6)
    
            # 各列の重量設定
            row.grid_columnconfigure(1, weight=1)
            for col in range(10):
                if col != 1:
                    row.grid_columnconfigure(col, weight=0)
        
        # サイズを変更しない - 固定サイズのまま
        # ウィンドウのレイアウトを更新するだけ
        if hasattr(self, 'dan_window') and self.dan_window:
            self.dan_window.update_idletasks()
            
    def on_course_changed(self, song_idx, combobox):
        selected = combobox.get()
        self.song_courses_temp[song_idx] = selected
        self.update_level_and_genre(song_idx)

    def update_level_and_genre(self, song_idx):
        if song_idx >= len(self.song_paths):
            return
        path = self.song_paths[song_idx]
        selected_jp = self.song_courses_temp.get(song_idx, "鬼")
        course_map = {"かんたん":"Easy","ふつう":"Normal","むずかしい":"Hard","鬼":"Oni","裏鬼":"Edit"}
        target = course_map.get(selected_jp, "Oni")
        level = "?"
        scoreinit = ""
        scorediff = ""
        genre = "ナムコオリジナル"
        try:
            with open(path, 'r', encoding='shift_jis', errors='ignore') as f:
                content = f.read()
            current_course = None
            for line in content.splitlines():
                s = line.strip()
                m = re.match(r"COURSE:\s*([^\s]+)", s, re.I)
                if m:
                    c = m.group(1).strip()
                    if c in ["0","1","2","3","4"]:
                        c = ["Easy","Normal","Hard","Oni","Edit"][int(c)]
                    current_course = c.capitalize()
                if current_course == target:
                    lm = re.match(r"LEVEL:\s*(\d+)", s, re.I)
                    if lm: level = lm.group(1)
                    im = re.match(r"SCOREINIT:\s*(\d+)", s, re.I)
                    if im: scoreinit = im.group(1)
                    dm = re.match(r"SCOREDIFF:\s*(\d+)", s, re.I)
                    if dm: scorediff = dm.group(1)
                    gm = re.match(r"GENRE:\s*(.+)", s, re.I)
                    if gm: genre = gm.group(1).strip()
        except Exception:
            pass
        self.song_levels[song_idx] = level
        self.song_scoreinit[song_idx] = scoreinit
        self.song_scorediff[song_idx] = scorediff
        self.song_genres[song_idx] = genre
        self.update_song_settings()

    def add_song(self):
        if len(self.song_paths) >= 3:
            messagebox.showwarning("警告", "段位道場は3曲までです", parent=self.dan_window)
            return
        path = filedialog.askopenfilename(filetypes=[("TJA files", "*.tja")], parent=self.dan_window)
        if path:
            idx = len(self.song_paths)
            self.song_paths.append(path)
            avail = self.parse_courses_from_tja(path)
            self.song_course_values[idx] = avail
            jp_names = ["かんたん","ふつう","むずかしい","鬼","裏鬼"]
            course_names = ["Easy","Normal","Hard","Oni","Edit"]
            available_jp = [jp_names[course_names.index(c)] for c in avail if c in course_names]
            default_jp = available_jp[0] if available_jp else "鬼"
            self.song_courses_temp[idx] = default_jp
            self.song_levels[idx] = "?"
            self.song_genres[idx] = "ナムコオリジナル"
            self.song_scoreinit[idx] = ""
            self.song_scorediff[idx] = ""
            self.update_song_settings()
            self.update_add_button()
            self.root.after(200, lambda: self.update_level_and_genre(idx))

    def remove_song(self):
        sel = self.song_listbox.curselection()
        if not sel: return
        idx = sel[0]
        self.song_paths.pop(idx)
        for d in [self.song_course_values, self.song_levels, self.song_genres, self.song_courses_temp, self.song_scoreinit, self.song_scorediff]:
            if idx in d:
                del d[idx]
            new_d = {k-1 if k > idx else k: v for k, v in d.items() if k != idx}
            d.clear()
            d.update(new_d)
        self.update_song_settings()
        self.update_add_button()

    def update_add_button(self):
        cur = len(self.song_paths)
        rem = 3 - cur
        self.add_button.config(text=f"曲追加 ({rem}/3)", state="normal" if rem > 0 else "disabled")

    def move_up(self):
        sel = self.song_listbox.curselection()
        if not sel or sel[0] == 0: return
        idx = sel[0]
        self.song_paths[idx-1], self.song_paths[idx] = self.song_paths[idx], self.song_paths[idx-1]
        for d in [self.song_course_values, self.song_levels, self.song_genres, self.song_courses_temp, self.song_scoreinit, self.song_scorediff]:
            if idx in d and idx-1 in d:
                d[idx-1], d[idx] = d[idx], d[idx-1]
        self.update_song_settings()
        self.song_listbox.selection_set(idx-1)

    def move_down(self):
        sel = self.song_listbox.curselection()
        if not sel or sel[0] == len(self.song_paths)-1: return
        idx = sel[0]
        self.song_paths[idx], self.song_paths[idx+1] = self.song_paths[idx+1], self.song_paths[idx]
        for d in [self.song_course_values, self.song_levels, self.song_genres, self.song_courses_temp, self.song_scoreinit, self.song_scorediff]:
            if idx in d and idx+1 in d:
                d[idx], d[idx+1] = d[idx+1], d[idx]
        self.update_song_settings()
        self.song_listbox.selection_set(idx+1)

    def parse_courses_from_tja(self, path):
        try:
            with open(path, 'r', encoding='shift_jis', errors='ignore') as f:
                content = f.read()
            courses = set()
            for m in re.finditer(r"^\s*COURSE:\s*([^\s#;]+)", content, re.M | re.I):
                raw = m.group(1).strip()
                if raw in ["0", "1", "2", "3", "4"]:
                    course_name = ["Easy", "Normal", "Hard", "Oni", "Edit"][int(raw)]
                elif raw.lower() in ["easy", "normal", "hard", "oni", "edit", "ura"]:
                    course_name = raw.capitalize()
                    if course_name == "Ura":
                        course_name = "Edit"
                else:
                    course_name = raw.capitalize()
                courses.add(course_name)
            if not courses:
                return ["Oni"]
            order = ["Easy", "Normal", "Hard", "Oni", "Edit"]
            return sorted(courses, key=lambda x: order.index(x) if x in order else 999)
        except Exception:
            return ["Oni"]

    def extract_song_data(self, content, target_course):
        lines = content.splitlines()
        global_headers = {}
        course_headers = {}
        chart = []
        current_course = None
        in_chart = False
        chart_lines = []

        forbidden_starts = {"#START", "#P1START", "#P2START"}
        forbidden_ends = {"#END", "#P1END", "#P2END"}

        header_pattern = re.compile(r"^(\w+):\s*(.+)", re.IGNORECASE)
        course_pattern = re.compile(r"^COURSE:\s*(.+)", re.IGNORECASE)

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            # COURSE切り替え
            course_match = course_pattern.match(line)
            if course_match:
                course_name = course_match.group(1).strip()
                if course_name in ["0", "1", "2", "3", "4"]:
                    course_name = ["Easy", "Normal", "Hard", "Oni", "Edit"][int(course_name)]
                elif course_name.lower() in ["easy", "normal", "hard", "oni", "edit", "ura"]:
                    course_name = course_name.capitalize()
                    if course_name == "Ura":
                        course_name = "Edit"
                current_course = course_name
                continue

            # ヘッダー行
            header_match = header_pattern.match(line)
            if header_match:
                key = header_match.group(1).upper()
                value = header_match.group(2).strip()

                if key == "BALLOON":
                    # BALLOONだけは選んだコース優先（他のコースは無視）
                    if current_course == target_course:
                        balloons = [v.strip() for v in value.split(",") if v.strip().isdigit()]
                        course_headers["BALLOON"] = course_headers.get("BALLOON", []) + balloons
                    # 他のコースのBALLOONは完全無視（global_headersにも入れない！）
                else:
                    # その他のヘッダー（TITLE, SUBTITLE, WAVE, BPM, LEVELなど）は
                    # コース内でもグローバルでも両方保存 → あとでコース優先でマージ
                    target_dict = course_headers if current_course == target_course else global_headers
                    target_dict[key] = value
                continue

            # 譜面開始/終了（選んだコースのみ）
            if line.upper() in forbidden_starts:
                if current_course == target_course:
                    in_chart = True
                    chart_lines = [raw_line]
                continue
            elif line.upper() in forbidden_ends:
                if in_chart:
                    chart_lines.append(raw_line)
                    chart = chart_lines
                    in_chart = False
                    chart_lines = []
                continue

            if in_chart:
                chart_lines.append(raw_line)

        # BALLOONは選んだコースのものだけ使う（重複・順序そのまま）
        if "BALLOON" in course_headers:
            course_headers["BALLOON"] = ",".join(course_headers["BALLOON"])

        # その他のヘッダーはコース優先 + グローバル補完
        headers = {**global_headers, **course_headers}  # コースが上書き優先

        return headers, chart

    def get_exam_str_common(self, item):
        t = self.common_type_combos[item].get()
        c = self.common_comp_combos[item].get()
        n = self.common_normal_entries[item].get().strip()
        g = self.common_gold_entries[item].get().strip()
        if not n.isdigit() or not g.isdigit():
            raise ValueError("数値が不正です")
        return f"{self.exam_codes[t]},{n},{g},{self.comparisons[c]}"

    def get_exam_str_per(self, item, idx):
        tc, cc, ne, ge = self.per_song_widgets[item][idx]
        t = tc.get()
        c = cc.get()
        n = ne.get().strip()
        g = ge.get().strip()
        if not n.isdigit() or not g.isdigit():
            raise ValueError("数値が不正です")
        return f"{self.exam_codes[t]},{n},{g},{self.comparisons[c]}"
    
    def remove_all_comments(self, text):
        """
        行全体/行末コメントを削除するが、
        コメント以外の部分がある行は絶対に削除しない。
        """
        cleaned = []
        for line in text.splitlines():
    
            original = line  # 元の行を保持
            # 行末コメントを削除（// または ;）
            line = re.split(r"//|;", line)[0].rstrip()
    
            # コメントしかなかった行 → 空行として残す（削除しない）
            if line == "":
                cleaned.append("")
            else:
                cleaned.append(line)
    
        return "\n".join(cleaned) + "\n"

    def generate_dan_code(self):
        """段位道場TJAを生成し、指定パスにファイルとして保存する（エディタ内容は一切変更しない）"""
        if not self.song_paths:
            messagebox.showerror("エラー", "曲が1つも選択されていません", parent=self.dan_window)
            return

        # タイトル欄からファイル名候補を取得（空欄の場合はデフォルト）
        dan_title = self.dan_title_entry.get().strip()
        if not dan_title:
            dan_title = "段位道場"

        # Windows/macOS/Linux で安全なファイル名に変換（禁止文字をアンダースコアに置換）
        import re
        safe_filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', dan_title)
        default_filename = f"{safe_filename}.tja"

        # 保存ダイアログ（前回保存フォルダを優先）
        initial_dir = getattr(self, "last_folder", os.path.expanduser("~"))
        save_path = filedialog.asksaveasfilename(
            title="段位道場TJAを保存",
            defaultextension=".tja",
            filetypes=[("TJAファイル", "*.tja")],
            initialfile=default_filename,
            initialdir=initial_dir,
            parent=self.dan_window,
        )
        if not save_path:
            return  # キャンセル

        # 次回ダイアログの初期フォルダを更新
        self.last_folder = os.path.dirname(save_path)

        # TJA本文の生成（既存ロジックをほぼそのまま使用）
        code = []
        code.append(f"TITLE:{dan_title}\n")
        code.append("SUBTITLE:--\n")
        code.append("WAVE:\n")
        code.append("SCOREMODE:2\n")
        code.append("COURSE:Dan\n")
        dan_color = getattr(self, "dan_genre_var", tk.StringVar(value="金")).get()
        code.append(f"GENRE:段位-{dan_color}\n")

        # 共通合格条件
        for item in self.DAN_ITEMS:
            if not self.per_song_vars[item].get():
                try:
                    s = self.get_exam_str_common(item)
                    code.append(f"{item}:{s}\n")
                except ValueError as e:
                    messagebox.showerror("入力エラー", f"{item}: {e}", parent=self.dan_window)
                    return

        course_id_map = {"Easy": "0", "Normal": "1", "Hard": "2", "Oni": "3", "Edit": "4"}
        all_balloons = []
        song_data = []

        # 各曲のヘッダー・譜面抽出
        for i, path in enumerate(self.song_paths):
            selected_jp = self.song_courses_temp.get(i, "鬼")
            map_jp = {"かんたん": "Easy", "ふつう": "Normal", "むずかしい": "Hard", "鬼": "Oni", "裏鬼": "Edit"}
            target_course = map_jp.get(selected_jp, "Oni")

            try:
                with open(path, "r", encoding="shift_jis", errors="ignore") as f:
                    content = f.read()

                headers, chart = self.extract_song_data(content, target_course)

                # BALLOONは選択したコースのものだけ取得
                if headers.get("BALLOON"):
                    balloons = [b.strip() for b in headers["BALLOON"].split(",") if b.strip().isdigit()]
                    all_balloons.extend(balloons)

                # 手動設定の優先適用
                headers["GENRE"] = self.song_genres.get(i, headers.get("GENRE", "ナムコオリジナル")).strip()
                if self.song_scoreinit.get(i, "").strip():
                    headers["SCOREINIT"] = self.song_scoreinit[i].strip()
                if self.song_scorediff.get(i, "").strip():
                    headers["SCOREDIFF"] = self.song_scorediff[i].strip()

                level = self.song_levels.get(i, headers.get("LEVEL", "10")).strip()

                song_data.append({
                    "title": headers.get("TITLE", "無題").strip() or "無題",
                    "subtitle": headers.get("SUBTITLE", "").strip(),
                    "wave": headers.get("WAVE", "").strip(),
                    "genre": headers["GENRE"],
                    "scoreinit": headers.get("SCOREINIT", "").strip() or "-",
                    "scorediff": headers.get("SCOREDIFF", "").strip() or "-",
                    "chart": chart,
                    "course": target_course,
                    "level": level,
                    "bpm": headers.get("BPM", ""),
                    "offset": headers.get("OFFSET", "0"),
                })

            except Exception as e:
                messagebox.showerror("読み込み失敗", f"{os.path.basename(path)}\n{e}", parent=self.dan_window)
                return

        # BALLOON出力
        if all_balloons:
            code.append(f"BALLOON:{','.join(all_balloons)}\n")

        code.append("\n#START\n")

        # 各曲の出力
        for i, data in enumerate(song_data):
            parts = [
                data["title"],
                data["subtitle"] or "-",
                data["wave"] or "-",
                data["genre"],
                data["scoreinit"],
                data["scorediff"],
                course_id_map.get(data["course"], "3"),
                data["level"] or "10",
            ]
            code.append("#NEXTSONG " + ",".join(parts) + "\n")

            if data["bpm"]:
                code.append(f"#BPMCHANGE {data['bpm'].strip()}\n")
            try:
                offset = float(data["offset"])
                if offset < 0:
                    code.append(f"#DELAY {-offset}\n")
            except:
                pass

            # 個別合格条件
            for item in self.per_song_order:
                if i < len(self.per_song_widgets.get(item, [])):
                    try:
                        s = self.get_exam_str_per(item, i)
                        code.append(f"{item}:{s}\n")
                    except ValueError as e:
                        messagebox.showerror("入力エラー", f"曲{i+1} {item}: {e}", parent=self.dan_window)
                        return

            # 譜面本体（#START/#END系は除外）
            forbidden = {"#START", "#END", "#P1START", "#P1END", "#P2START", "#P2END"}
            for line in data["chart"]:
                if line.strip().upper() not in forbidden:
                    code.append(line.rstrip("\r\n") + "\n")
            code.append("\n")
            if i < len(song_data) - 1:
                code.append(",\n")

        code.append("#END\n")

        # ファイル書き込み＋#NEXTSONGの.ogg自動コピー
        try:
            # 1. TJA本体を保存
            # 生成されたTJAテキストを結合
            tja_text = "".join(code)
            
            # すべてのコメント（// と ;）を削除
            tja_text = self.remove_all_comments(tja_text)
            
            with open(save_path, "w", encoding="cp932", newline="\n") as f:
                f.write(tja_text)

            # 2. #NEXTSONGから音源名を取得してコピー
            copied_files = []
            dest_folder = os.path.dirname(save_path)

            for i, data in enumerate(song_data):
                ogg_name = data["wave"].strip()  # #NEXTSONGの3番目に入っているもの
                if not ogg_name:
                    continue
                if not ogg_name.lower().endswith(".ogg"):
                    continue

                # 元のTJAと同じフォルダにあるはずなので、そこから探す
                source_tja_folder = os.path.dirname(self.song_paths[i])
                source_ogg_path = os.path.join(source_tja_folder, ogg_name)

                if not os.path.exists(source_ogg_path):
                    # 絶対パスだったときの保険
                    if os.path.isabs(ogg_name) and os.path.exists(ogg_name):
                        source_ogg_path = ogg_name
                    else:
                        continue  # 見つからなかったら飛ばす

                dest_ogg_path = os.path.join(dest_folder, ogg_name)

                # すでに同じ場所にある場合はコピーしない
                if os.path.abspath(source_ogg_path) == os.path.abspath(dest_ogg_path):
                    copied_files.append(ogg_name)
                    continue

                try:
                    shutil.copy2(source_ogg_path, dest_ogg_path)
                    copied_files.append(ogg_name)
                except Exception as e:
                    messagebox.showwarning(
                        "コピー失敗",
                        f"{ogg_name} のコピーに失敗しました。\n{e}",
                        parent=self.dan_window,
                    )

            # 3. 完了メッセージ
            msg = f"段位道場TJAを保存しました！\n\n{os.path.basename(save_path)}"
            if copied_files:
                msg += f"\n\n以下の音源も自動でコピーしました♪\n" + "\n".join(f"・{f}" for f in copied_files)
            else:
                msg += "\n\n（.ogg音源は見つかりませんでした）"

            messagebox.showinfo("保存完了", msg, parent=self.dan_window)

            # 4. 保存先フォルダを開く（前回直した安全版）
            try:
                if os.name == "nt":
                    os.startfile(dest_folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", dest_folder])
                else:
                    subprocess.Popen(["xdg-open", dest_folder])
            except Exception as e:
                print(f"フォルダを開けませんでした: {e}")

        except Exception as e:
            messagebox.showerror("保存失敗", f"ファイルの書き込みに失敗しました。\n\n{e}", parent=self.dan_window)

    def on_closing(self):
        # グローバルバインディング解除
        try:
            self.root.unbind_all("<F3>")
            self.root.unbind_all("<Shift-F3>")
        except:
            pass
        
        # ← 構文チェックウィンドウを閉じる
        if hasattr(self, 'syntax_window') and self.syntax_window:
            try:
                self.syntax_window.destroy()
            except:
                pass
            self.syntax_window = None
        
        # 設定保存
        self.save_config()
        
        # 変更があるかチェック
        if self.text.edit_modified():
            response = messagebox.askyesnocancel(
                "変更を保存しますか?",
                "編集中の内容が保存されていません。\n\n"
                "「はい」 → 保存して終了\n"
                "「いいえ」 → 保存せずに終了\n"
                "「キャンセル」 → 編集に戻る",
                icon="warning"
            )
            if response is True:
                if self.current_file:
                    self.save_file()
                else:
                    self.save_as_file()
                self.root.destroy()
            elif response is False:
                self.root.destroy()
        else:
            if messagebox.askokcancel("終了", "TJA Editorを終了しますか?"):
                self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TJAEditor(root)
    root.mainloop()