import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, Toplevel, ttk
from tkinter import font as tkfont
from tkinter import Listbox, Scrollbar, Button, Entry, Label, Frame, LabelFrame, Checkbutton
import matplotlib as plt
plt.rcParams['font.family'] = 'Yu Gothic'
plt.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import re
import sys
import math
import subprocess
import os
import shutil
import json
import chardet
import datetime
import threading

class TJAEditor:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tja_editor_config.json")

    MAX_UNDO = 100
    MAX_RECENT = 10

    DAN_ITEMS = ["EXAM1", "EXAM2", "EXAM3", "EXAM4"]
    DAN_DEFAULTS = [
        ("魂ゲージ", "～以上", "100", "100"),
        ("可の数", "～未満", "0", "0"),
        ("不可の数", "～未満", "0", "0"),
        ("連打数", "～以上", "0", "0")
    ]

    def get_config_path(self):
           """exe化された環境でも正しくconfigファイルのパスを取得"""
           if getattr(sys, 'frozen', False):
               # exe化された場合
               base_path = os.path.dirname(sys.executable)
           else:
               # スクリプト実行の場合
               base_path = os.path.dirname(os.path.abspath(__file__))
           return os.path.join(base_path, "tja_editor_config.json")
       
    def get_icon_path(self):
        """exe化された環境でも正しくiconファイルのパスを取得"""
        if getattr(sys, 'frozen', False):
            # exe化された場合
            base_path = os.path.dirname(sys.executable)
        else:
            # スクリプト実行の場合
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 1. iconフォルダ内を優先的に探す
        icon_folder = os.path.join(base_path, "icon")
        
        # アイコンファイル名のリスト（優先順位付き）
        icon_names = [
            "taiko.ico",        # Windows用 .ico
            "taiko_256x256.ico", # 高解像度用
            "taiko.png",         # その他プラットフォーム用
            "taiko.gif",
            "taiko.jpg"
        ]
        
        # まずiconフォルダ内を探す
        if os.path.exists(icon_folder) and os.path.isdir(icon_folder):
            for icon_name in icon_names:
                icon_path = os.path.join(icon_folder, icon_name)
                if os.path.exists(icon_path):
                    return icon_path
        
        # 2. 次にルートディレクトリを探す（互換性のため）
        for icon_name in icon_names:
            icon_path = os.path.join(base_path, icon_name)
            if os.path.exists(icon_path):
                return icon_path
        
        # 3. どうしても見つからない場合、実行ファイル自体をアイコンとして使用（Windowsのみ）
        if getattr(sys, 'frozen', False) and sys.platform == "win32":
            return sys.executable
        
        return None
    
    def __init__(self, root):
        self.CONFIG_FILE = self.get_config_path()
        self.root = root
            # アイコンを設定
        try:
            # アイコンファイルのパスを取得
            icon_path = self.get_icon_path()
            if icon_path and os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            # アイコン設定に失敗してもアプリは続行
            print(f"アイコン設定エラー: {e}")
            
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
        self.preview_running = False
        self.preview_process = None
        self.taikojiro_path = None
        self._change_timer = None
        self._key_pressed = False
        self._unsaved_changes = False
        self._text_content_hash = None
        self.palette_visible = False
        
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
        self.root.after(1000, self.check_taikojiro_path_on_startup)
        self.popup = tk.Menu(self.text, tearoff=0)
    
        self.popup.add_command(label="元に戻す", command=lambda: self.text.event_generate("<<Undo>>"), accelerator="Ctrl+Z")
        self.popup.add_command(label="やり直す", command=lambda: self.text.event_generate("<<Redo>>"), accelerator="Ctrl+Y")
        self.popup.add_separator()
        self.popup.add_command(label="切り取り ", command=lambda: self.text.event_generate("<<Cut>>"), accelerator="Ctrl+X")
        self.popup.add_command(label="コピー", command=lambda: self.text.event_generate("<<Copy>>"), accelerator="Ctrl+C")
        self.popup.add_command(label="貼り付け", command=lambda: self.text.event_generate("<<Paste>>"), accelerator="Ctrl+V")
        self.popup.add_command(label="削除",    command=lambda: self.text.event_generate("<<Clear>>"), accelerator="Del")
        self.popup.add_separator()
        self.popup.add_command(label="すべて選択 ", command=lambda: self.text.tag_add("sel", "1.0", "end"), accelerator="Ctrl+A")
    
        def show_popup(event):
            try:
                self.popup.tk_popup(event.x_root, event.y_root)
            finally:
                self.popup.grab_release()
    
        self.text.bind("<Button-3>", show_popup)
        self.text.bind("<Control-Button-1>", show_popup)
        self.text.bind("<<Modified>>", self._on_text_modified_enhanced)

    def set_window_icon(self):
        """ウィンドウアイコンを設定"""
        icon_path = self.get_icon_path()
        
        if icon_path and os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"アイコン設定エラー: {e}")
                # アイコン設定に失敗した場合はデフォルトアイコンを試みる
                self.set_default_icon()
        else:
            # アイコンファイルが見つからない場合はデフォルトアイコンを設定
            self.set_default_icon()
    
    def set_default_icon(self):
        """デフォルトアイコンを設定（Tkのデフォルトアイコンを削除）"""
        try:
            # Tkのデフォルトアイコンを削除（Windows）
            if sys.platform == "win32":
                self.root.iconbitmap('')
        except:
            pass

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="新規作成", command=self.new_file, accelerator="Ctrl+N")
        filemenu.add_command(label="開く", command=self.open_file, accelerator="Ctrl+O")
        filemenu.add_separator()
        recent_menu = tk.Menu(filemenu, tearoff=0)
        filemenu.add_cascade(label="最近使ったファイル", menu=recent_menu)
        self.recent_menu = recent_menu
        self.update_recent_menu()
        filemenu.add_command(label="履歴から削除...", command=self.delete_recent_history_item)
        filemenu.add_command(label="上書き保存", command=self.save_file, accelerator="Ctrl+S")
        filemenu.add_command(label="名前を付けて保存", command=self.save_as_file, accelerator="Ctrl+Shift+S")
        filemenu.add_separator()
        filemenu.add_command(label="終了", command=self.on_closing)
        menubar.add_cascade(label="ファイル", menu=filemenu)
    
        editmenu = tk.Menu(menubar, tearoff=0)
        editmenu.add_command(label="検索", command=self.open_search, accelerator="Ctrl+F")
        menubar.add_cascade(label="編集", menu=editmenu)
    
        viewmenu = tk.Menu(menubar, tearoff=0)
        self.viewmenu = viewmenu
        viewmenu.add_command(label="ダークモードに切り替え", command=self.toggle_dark_mode, accelerator="Ctrl+D")
        self.palette_visible_var = tk.BooleanVar(value=self.palette_visible)
        viewmenu.add_checkbutton(label="パレットを表示", variable=self.palette_visible_var,command=self.toggle_palette_visibility,accelerator="Ctrl+P")
        menubar.add_cascade(label="表示", menu=viewmenu)
    
        headermenu = tk.Menu(menubar, tearoff=0)
        headermenu.add_command(label="TITLE:", command=lambda: self.insert_with_input("TITLE:", "曲名を入力"))
        headermenu.add_command(label="SUBTITLE:", command=lambda: self.insert_with_input("SUBTITLE:", "サブタイトルを入力"))
        headermenu.add_command(label="WAVE:", command=self.insert_wave)
        headermenu.add_command(label="BPM:", command=lambda: self.insert_with_input("BPM:", "BPMを入力","120"))
        headermenu.add_command(label="OFFSET:", command=lambda: self.insert_with_input("OFFSET:", "オフセット(秒)", "0"))
        headermenu.add_command(label="SONGVOL:", command=lambda: self.insert_with_input("SONGVOL:", "曲の音量","100"))
        headermenu.add_command(label="SEVOL:", command=lambda: self.insert_with_input("SEVOL:", "効果音量","100"))
        headermenu.add_command(label="DEMOSTART:", command=lambda: self.insert_with_input("DEMOSTART:", "デモスタート"))
        headermenu.add_command(label="SCOREMODE:", command=lambda: self.insert_with_input("SCOREMODE:", "スコアモード (1 or 2)", "2"))
        headermenu.add_separator()
        coursemenu = tk.Menu(headermenu, tearoff=0)
        for course in ["Easy", "Normal", "Hard", "Oni", "Edit"]:
            coursemenu.add_command(label=course, command=lambda c=course: self.insert_course_only(c))
        headermenu.add_cascade(label="COURSE:", menu=coursemenu)
        stylemenu = tk.Menu(headermenu, tearoff=0)
        for style in ["Single","Double"]:
            stylemenu.add_command(label=style,command=lambda s=style: self.insert_style_only(s))
        headermenu.add_cascade(label="STYLE:", menu=stylemenu)
        headermenu.add_command(label="LEVEL:", command=lambda: self.insert_with_input("LEVEL:", "レベル (1-10)", "7"))
        headermenu.add_command(label="BALLOON:", command=lambda: self.insert_with_input("BALLOON:", "風船音符"))
        headermenu.add_command(label="SCOREINIT:", command=lambda: self.insert_with_input("SCOREINIT:", "初期スコア", "1000"))
        headermenu.add_command(label="SCOREDIFF:", command=lambda: self.insert_with_input("SCOREDIFF:", "スコア差分", "100"))
        menubar.add_cascade(label="ヘッダー挿入", menu=headermenu)
    
        notemenu = tk.Menu(menubar, tearoff=0)
        measuremenu = tk.Menu(notemenu, tearoff=0)
        measuremenu.add_command(label="#START", command=lambda: self.insert_syntax("#START\n"))
        measuremenu.add_command(label="#START P1", command=lambda: self.insert_syntax("#START P1\n"))
        measuremenu.add_command(label="#START P2", command=lambda: self.insert_syntax("#START P2\n"))
        measuremenu.add_command(label="#END", command=lambda: self.insert_syntax("#END\n"))
        notemenu.add_cascade(label="小節・開始/終了", menu=measuremenu)
        speedmenu = tk.Menu(notemenu, tearoff=0)
        speedmenu.add_command(label="#BPMCHANGE", command=lambda: self.insert_with_input("#BPMCHANGE ", "新しいBPM", "120"))
        speedmenu.add_command(label="#SCROLL", command=lambda: self.insert_with_input("#SCROLL ", "スクロール速度", "1.0"))
        speedmenu.add_command(label="#HBSCROLL", command=lambda: self.insert_with_input("#HBSCROLL ", "HBSCROLL速度", "1.0"))
        speedmenu.add_command(label="#DELAY", command=lambda: self.insert_with_input("#DELAY ", "遅延時間(秒)", "1.0"))
        speedmenu.add_command(label="#MEASURE", command=lambda: self.insert_with_input("#MEASURE ", "拍子 (例: 4/4, 3/4, 6/8)", "4/4"))
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
        menubar.add_cascade(label="譜面コマンド", menu=notemenu)
    
        dojomenu = tk.Menu(menubar, tearoff=0)
        dojomenu.add_command(label="段位道場設定", command=self.open_dan_window)
        menubar.add_cascade(label="段位道場", menu=dojomenu)
        
        toolmenu = tk.Menu(menubar, tearoff=0)
        # 音源・タイミング調整
        toolmenu.add_command(label="BPMカウンター(タップテンポ)", command=self.open_bpm_counter)
        toolmenu.add_command(label="OFFSET一括調整", command=self.open_offset_adjuster)
        toolmenu.add_separator()
        
        # プレビュー・再生
        toolmenu.add_command(label="太鼓さん次郎でプレビュー再生", command=self.preview_play, accelerator="F5")
        toolmenu.add_command(label="太鼓さん次郎のパスを設定", command=self.setup_taikojiro_path)
        toolmenu.add_separator()
        # 譜面分析・検証
        toolmenu.add_command(label="簡易エラーチェック", command=self.check_errors_simple, accelerator="Ctrl+Shift+E")
        toolmenu.add_command(label="TODO管理", command=self.open_todo_manager, accelerator="Ctrl+T")
        toolmenu.add_separator()
        
        # ファイル管理・配布
        toolmenu.add_command(label="配布用ZIPを作成", command=self.create_distribution_zip,accelerator="Ctrl+E")
        toolmenu.add_separator()
        toolmenu.add_command(label="バックアップフォルダを開く", command=self.open_backup_folder)
        toolmenu.add_command(label="バックアップ履歴を表示・復元", command=self.show_backup_history)
        toolmenu.add_command(label="バックアップ比較", command=self.open_backup_compare)
        menubar.add_cascade(label="ツール", menu=toolmenu)
        
        self.root.config(menu=menubar)

    def _create_widgets(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
    
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
    
        self.linenumbers = tk.Canvas(text_container, width=80, bg="white", highlightthickness=0)
        self.linenumbers.pack(side=tk.LEFT, fill=tk.Y)
        
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
    
        # スクロールバーのコマンド設定
        vscroll.config(command=self.sync_scroll)  # 縦スクロールバーには行番号同期用の関数を設定
        hscroll.config(command=self.text.xview)   # 横スクロールバーには標準のxviewを設定
    
        # テキストの変更やサイズ変更で行番号更新
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        
        # ステータスバー（既存）
        self.statusbar = tk.Label(self.root, text="準備完了", relief=tk.SUNKEN, anchor="w", font=("MS Gothic", 10))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        # ================== ここからパレットを追加 ==================
        if self.dark_mode:
            p_bg = "#252526"
            p_btn_bg = "#2d2d2d"
            p_fg = "#e6e6e6"
        else:
            p_bg = "#f3f3f3"
            p_btn_bg = "#ffffff"
            p_fg = "black"
    
        self.palette_frame = tk.Frame(self.root, bg=p_bg, relief="raised", bd=1)
        self.palette_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
        btn_font = ("MS Gothic", 12, "bold")
        # ボタン群を左寄せで配置（0-9）
        btn_container = tk.Frame(self.palette_frame, bg=p_bg)
        btn_container.pack(side=tk.LEFT, padx=6, pady=4)
    
        for n in ["0","1","2","3","4","5","6","7","8","9"]:
            b = tk.Button(btn_container, text=n, width=3, height=1, font=btn_font,
                          bg=p_btn_bg, fg=p_fg, command=lambda ch=n: self.insert_palette_char(ch))
            b.pack(side=tk.LEFT, padx=2)
    
    
        comma_btn = tk.Button(btn_container, text=",", width=3, font=btn_font,
                              bg=p_btn_bg, fg=p_fg, command=lambda: self.insert_palette_char(","))
        comma_btn.pack(side=tk.LEFT, padx=4)
    
        newline_btn = tk.Button(btn_container, text="改行", width=6, font=btn_font,
                                bg=p_btn_bg, fg=p_fg, command=lambda: self.insert_palette_char("\n"))
        newline_btn.pack(side=tk.LEFT, padx=4)
    
        self.text.tag_configure("search", background="yellow", foreground="black")
    
        # 構文ハイライト設定（以降既存の設定をそのまま実行）
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
    
        # 音符数字の色設定（既存）
        self.text.tag_configure("note_1_3", foreground="#FF0000", font=(self.main_font[0], self.main_font[1], "bold"))
        self.text.tag_configure("note_2_4", foreground="#00FFFF", font=(self.main_font[0], self.main_font[1], "bold"))
        self.text.tag_configure("note_5_6_8", foreground="#FFFF00", font=(self.main_font[0], self.main_font[1], "bold"))
        self.text.tag_configure("note_7", foreground="#FFA500", font=(self.main_font[0], self.main_font[1], "bold"))
        self.text.tag_configure("note_9", foreground="#800080", font=(self.main_font[0], self.main_font[1], "bold"))
        self.text.tag_configure("note_0", foreground="#404040", font=(self.main_font[0], self.main_font[1], "bold"))
    
        # 検索ハイライト用のタグ（既存のものに追加）
        self.text.tag_configure("search", background="#FFD700", foreground="black")  # 明るい黄色
        self.text.tag_configure("search_current", background="#FFA500", foreground="white")  # オレンジ（現在の一致）
    
        # 置換ハイライト用のタグ
        self.text.tag_configure("replace", background="#90EE90", foreground="black")  # 薄緑色
    
        # 起動後に1回だけ行番号更新
        self.root.after(100, self.update_linenumbers)

    def _bind_events(self):
        self.root.bind("<F5>", lambda event: self.preview_play())
        self.root.bind_all("<Control-d>", lambda e: self.toggle_dark_mode())
        self.root.bind_all("<Control-e>", lambda e: self.create_distribution_zip())
        self.root.bind_all("<Control-f>", lambda e: self.open_search())
        self.root.bind_all("<Control-n>", lambda e: self.new_file())
        self.root.bind_all("<Control-o>", lambda e: self.open_file())
        self.root.bind_all("<Control-p>", lambda e: self.toggle_palette_visibility())
        self.root.bind_all("<Control-s>", lambda e: self.save_file())
        self.root.bind_all("<Control-t>", lambda e: self.open_todo_manager())
        self.root.bind_all("<Control-Shift-e>", lambda e: self.check_syntax_errors_simple())
        self.root.bind_all("<Control-Shift-s>", lambda e: self.save_as_file())

        # キー入力中もリアルタイムで行番号を更新
        self.text.bind("<Key>", self._on_key_press)
        self.text.bind("<KeyRelease>", self._on_key_release)
        
        self.text.bind("<ButtonRelease>", lambda e: self.root.after_idle(self.update_linenumbers))
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        
        # テキスト変更時のイベントハンドラ
        self.text.bind("<KeyRelease>", lambda e: self.root.after_idle(self.update_all))
        
        # Modifiedイベントのバインディング - 簡易版
        self.text.bind("<<Modified>>", self._on_modified)
        
        # ペーストイベントも監視
        self.text.bind("<<Paste>>", lambda e: self.root.after(50, self._check_for_changes))
        self.text.bind("<<Cut>>", lambda e: self.root.after(50, self._check_for_changes))
        self.text.bind("<<Undo>>", lambda e: self.root.after(50, self._check_for_changes))
        self.text.bind("<<Redo>>", lambda e: self.root.after(50, self._check_for_changes))
        
        # マウスホイール
        def on_mousewheel(e):
            self.text.yview_scroll(-int(e.delta/120), "units")
            self.root.after_idle(self.update_linenumbers)
            return "break"
        
        self.text.bind("<MouseWheel>", on_mousewheel)
        self.text.bind("<Shift-MouseWheel>", lambda e: self.text.xview_scroll(-int(e.delta/120), "units") or "break")
        
        self.statusbar.config(text="準備完了")
    
    def _on_key_press(self, event=None):
        self._key_pressed = True
        self._schedule_check()

    def _on_key_release(self, event=None):
        self._key_pressed = False
        self._schedule_check()

    def _schedule_check(self):
        # 既存のタイマーをキャンセルして、新しいのをセット（デバウンス）
        if self._change_timer:
            self.root.after_cancel(self._change_timer)
        self._change_timer = self.root.after(100, self._perform_check)

    def _perform_check(self):
        self._change_timer = None
        if not self._key_pressed:
            self._check_for_changes()
    
    def _on_modified(self, event=None):
        """Modifiedイベントハンドラ"""
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._unsaved_changes = True
            self.update_title()

    def _check_for_changes(self, event=None):
        """テキストの変更を検出して状態を更新"""
        try:
            # 現在の内容を取得
            current_content = self.text.get("1.0", "end-1c")
            
            # 初回または前回の内容がない場合
            if self._text_content_hash is None:
                # 現在の内容のハッシュを保存
                import hashlib
                self._text_content_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()
                self._unsaved_changes = False
            else:
                # ハッシュを計算して比較
                import hashlib
                current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()
                
                if current_hash != self._text_content_hash:
                    self._unsaved_changes = True
                    self._text_content_hash = current_hash
                    self.update_title()
                    # print(f"[DEBUG] Content changed, unsaved_changes={self._unsaved_changes}")  # デバッグ用
        except Exception as e:
            # エラーが発生してもクラッシュしないように
            print(f"[WARNING] Error in _check_for_changes: {e}")

    def load_config(self):
        """起動時に設定を読み込む（なければデフォルト生成）"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                config = {}
        else:
            config = {}
        
        # デフォルト適用
        self.recent_files = config.get("recent_files", [])
        self.last_folder = config.get("last_folder", os.path.expanduser("~"))
        self.dark_mode = config.get("dark_mode", False)
        self.syntax_theme_name = config.get("syntax_theme", None)
        self.taikojiro_path = config.get("taikojiro_path", None)
        self.first_launch_completed = config.get("first_launch_completed", False)
        self.palette_visible = config.get("palette_visible", False)
        
        self.root.after(100, self.update_recent_menu)
        self.root.after(150, self.apply_dark_mode)
        
        # ★ ファイルが無かった場合のみ生成
        if not os.path.exists(self.CONFIG_FILE):
            self.save_config()
    
    def save_config(self):
        """設定変更時に設定を保存"""
        config = {
            "recent_files": self.recent_files,
            "dark_mode": self.dark_mode,
            "last_folder": self.last_folder,
            "taikojiro_path": self.taikojiro_path,
            "first_launch_completed": True,
            "palette_visible": self.palette_visible
        }
        
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            # 設定保存失敗ではアプリを止めない
            pass
    
    def check_taikojiro_path_on_startup(self):
        """初回起動時にのみ太鼓さん次郎のパスを確認"""
        # first_launch_completedフラグをチェック
        if hasattr(self, 'first_launch_completed') and self.first_launch_completed:
            return  # 初回起動済みの場合は表示しない
        
        path = self.get_taikojiro_path()
        
        if not path or not os.path.isfile(path):
            # 非同期でメッセージを表示（メインウィンドウが表示された後）
            self.root.after(1500, lambda: messagebox.showinfo(
                "パス設定をおすすめします",
                "太鼓さん次郎のパスが設定されていません。\n\n"
                "「ツール」→「太鼓さん次郎のパスを設定...」から設定すると、\n"
                "F5キーで簡単にプレビュー再生できます。"
            ))
        
        # 初回起動フラグを保存
        self.first_launch_completed = True
        self.save_config()

    def apply_dark_mode(self):
        """ダークモードとパレット表示状態を強制的に適用（起動時用）"""
        if self.dark_mode:
            self.toggle_dark_mode(force=True)
        else:
            self.toggle_dark_mode(force=False)
        
        # パレット表示状態を適用
        if hasattr(self, 'palette_frame'):
            if self.palette_visible:
                # パレットを表示
                self.palette_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.statusbar)
                # ダークモードの色を適用
                self._update_main_palette_colors()
            else:
                # パレットを非表示
                self.palette_frame.pack_forget()
        
        # メニューのチェック状態を更新
        if hasattr(self, 'palette_visible_var'):
            self.palette_visible_var.set(self.palette_visible)  
    
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
        
    def _on_text_modified_enhanced(self, event=None):
        """テキスト変更を確実に追跡するイベントハンドラ（カーソル復元を削除）"""
        if self.text.edit_modified():
            # 変更があったことを記録
            self._unsaved_changes = True
            self.text.edit_modified(False)  # フラグをリセット
            self.update_title()  # タイトルに変更マークを表示

            # 他の更新処理だけ行う（カーソル復元はしない！）
            self.root.after_idle(self.on_text_change)
            self.root.after_idle(self.update_linenumbers)
            # 構文ハイライトも更新
            self.root.after_idle(self.apply_syntax_highlighting)
            
    def on_text_change(self, event=None):
        """テキスト変更時に構文ハイライトを更新"""
        self.root.after_idle(self.apply_syntax_highlighting)
            
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

    def bayes_bpm_estimate_article(self, tap_times, sigma=0.03):
        """
        yuinore.net の Bayes BPM Counter 2 の数式を実装（小数点第3位まで高精度版）
        """
        if len(tap_times) < 2:
            return 0.0
    
        # タップ間隔
        intervals = []
        for i in range(1, len(tap_times)):
            dt = tap_times[i] - tap_times[i - 1]
            if dt > 0:
                intervals.append(dt)
    
        if not intervals:
            return 0.0
    
        # 平均間隔から初期BPMを計算（小数点第3位まで）
        avg_interval = sum(intervals) / len(intervals)
        initial_bpm = 60.0 / avg_interval if avg_interval > 0 else 120.0
        
        # 探索範囲を動的に設定（初期値の±30%）
        bpm_min = max(40.0, initial_bpm * 0.7)  # 最小40BPM
        bpm_max = min(initial_bpm * 1.3, 600.0)  # 最大600BPM
        
        # さらに、最小間隔から計算した最大BPMも考慮
        min_interval = min(intervals)
        if min_interval > 0:
            max_from_interval = 60.0 / min_interval
            bpm_max = max(bpm_max, min(max_from_interval * 1.1, 1000.0))  # 最大1000BPMまで
    
        # 小数点第3位まで探索するためのステップ
        step = 0.001  # 0.001BPM刻み
        
        best_bpm = 0.0
        best_log_prob = -float("inf")
    
        # 高精度なBPM候補探索（小数点第3位まで）
        # 探索範囲を制限して計算量を抑える
        bpm_range = bpm_max - bpm_min
        num_steps = int(bpm_range / step)
        
        # 計算量が大きくなりすぎないように調整
        if num_steps > 5000:  # 5000ステップ以上になる場合は粗くしてから細かく
            # 最初は0.1刻みで粗く探索
            coarse_step = 0.1
            for bpm in range(int(bpm_min / coarse_step), int(bpm_max / coarse_step) + 1):
                bpm_val = bpm * coarse_step
                expected_dt = 60.0 / bpm_val
    
                # log尤度
                log_p = 0.0
                for dt in intervals:
                    log_p += -((dt - expected_dt) ** 2) / (2 * sigma * sigma)
    
                if log_p > best_log_prob:
                    best_log_prob = log_p
                    best_bpm = bpm_val
            
            # 見つかった最適値の周辺を詳細に探索
            refine_range = 0.5  # ±0.5BPMの範囲
            refine_min = max(bpm_min, best_bpm - refine_range)
            refine_max = min(bpm_max, best_bpm + refine_range)
            
            for bpm in range(int(refine_min / step), int(refine_max / step) + 1):
                bpm_val = bpm * step
                expected_dt = 60.0 / bpm_val
    
                log_p = 0.0
                for dt in intervals:
                    log_p += -((dt - expected_dt) ** 2) / (2 * sigma * sigma)
    
                if log_p > best_log_prob:
                    best_log_prob = log_p
                    best_bpm = bpm_val
        else:
            # 直接詳細探索
            for bpm in range(int(bpm_min / step), int(bpm_max / step) + 1):
                bpm_val = bpm * step
                expected_dt = 60.0 / bpm_val
    
                log_p = 0.0
                for dt in intervals:
                    log_p += -((dt - expected_dt) ** 2) / (2 * sigma * sigma)
    
                if log_p > best_log_prob:
                    best_log_prob = log_p
                    best_bpm = bpm_val
    
        # 小数点第3位で丸める
        return round(best_bpm, 3)

    def bpm_sigma_from_taps(self,tap_times):
        """
        タップ間隔からBPMの標準偏差 σ を求める
        """
        if len(tap_times) < 3:
            return None
    
        bpms = []
        for i in range(1, len(tap_times)):
            dt = tap_times[i] - tap_times[i - 1]
            if dt > 0:
                bpms.append(60.0 / dt)
    
        if len(bpms) < 2:
            return None
    
        mean = sum(bpms) / len(bpms)
        var = sum((b - mean) ** 2 for b in bpms) / len(bpms)
        return math.sqrt(var)

    def open_bpm_counter(self):
        """コンパクトなBPMカウンター(タップテンポ) - グラフ表示付き"""
        # 既存のウィンドウを確実にチェック
        if hasattr(self, 'bpm_window'):
            try:
                if self.bpm_window and self.bpm_window.winfo_exists():
                    self.bpm_window.lift()
                    self.bpm_window.focus_set()
                    return
                else:
                    # ウィンドウが破棄されている場合はクリーンアップ
                    self.bpm_window = None
            except:
                self.bpm_window = None
        
        self.bpm_window = Toplevel(self.root)
        self.bpm_window.title("BPMカウンター - グラフ表示付き")
        self.bpm_window.geometry("1000x750")  # サイズを大きくしてグラフ用スペースを確保
        self.bpm_window.resizable(False, False)  # サイズ変更可能に
        self.bpm_window.transient(self.root)
        
        # 閉じる時の処理
        def on_bpm_window_close():
            if hasattr(self, 'bpm_window') and self.bpm_window:
                try:
                    # キーバインディング解除
                    self.bpm_window.unbind("<space>")
                    self.bpm_window.unbind("<Escape>")
                    self.bpm_window.unbind("<Delete>")
                    self.bpm_window.unbind("<Return>")
                    
                    # ルートウィンドウからのバインディングも解除
                    self.root.unbind("<space>")
                    
                    # グラフ用のクリーンアップ
                    if hasattr(self, 'bpm_graph'):
                        self.bpm_graph = None
                    
                    # ウィンドウ破棄
                    self.bpm_window.destroy()
                except:
                    pass
                finally:
                    self.bpm_window = None
                    
                    # 変数クリーンアップ
                    if hasattr(self, 'tap_times'):
                        self.tap_times = []
                    if hasattr(self, 'bpm_history'):
                        self.bpm_history = []
                    if hasattr(self, 'bpm_result'):
                        self.bpm_result = 0
                    if hasattr(self, 'intervals'):
                        self.intervals = []
        
        self.bpm_window.protocol("WM_DELETE_WINDOW", on_bpm_window_close)
        
        # タップ記録用（確実に初期化）
        self.tap_times = []
        self.bpm_history = []
        self.bpm_result = 0
        self.intervals = []  # タップ間隔を保存するリストを追加
        
        # メインフレーム(横分割レイアウト)
        main_frame = tk.Frame(self.bpm_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # === 左側フレーム: コントロールと情報表示 ===
        left_frame = tk.Frame(main_frame, width=350)
        left_frame.pack(side="left", fill="both", padx=(0, 10))
        left_frame.pack_propagate(False)  # 固定幅を維持
        
        # === 上部: タイトルと表示 ===
        top_frame = tk.Frame(left_frame)
        top_frame.pack(fill="x", pady=(0, 10))
        
        # タイトル
        tk.Label(top_frame, text="BPMカウンター", 
                 font=("メイリオ", 13, "bold")).pack()
        tk.Label(top_frame, text="曲に合わせてスペースキーをタップ", 
                 font=("メイリオ", 9), fg="#666666").pack()
        
        # BPM大表示
        display_frame = tk.Frame(left_frame)
        display_frame.pack(fill="x", pady=10)
        
        self.bpm_display = tk.Label(display_frame, text="0.0", 
                                    font=("Arial", 56, "bold"), fg="#0066cc")
        self.bpm_display.pack()
        
        tk.Label(display_frame, text="BPM", 
                 font=("メイリオ", 13)).pack()
        
        # === 情報表示フレーム ===
        info_frame = tk.LabelFrame(left_frame, text="計測情報", padx=10, pady=10)
        info_frame.pack(fill="x", pady=8)
        
        # 情報表示(グリッドレイアウト)
        self.tap_count_label = tk.Label(info_frame, text="タップ回数: 0", 
                                        font=("メイリオ", 10))
        self.tap_count_label.grid(row=0, column=0, sticky="w", pady=2)
        
        self.avg_bpm_label = tk.Label(info_frame, text="平均BPM: 0.0", 
                                      font=("メイリオ", 10))
        self.avg_bpm_label.grid(row=1, column=0, sticky="w", pady=2)
        
        self.stability_label = tk.Label(info_frame, text="安定度: ---", 
                                        font=("メイリオ", 10))
        self.stability_label.grid(row=2, column=0, sticky="w", pady=2)
        
        self.interval_label = tk.Label(info_frame, text="前回間隔: ---", 
                                       font=("メイリオ", 10))
        self.interval_label.grid(row=3, column=0, sticky="w", pady=2)
        
        # 右側の列（BPM範囲など）
        self.min_bpm_label = tk.Label(info_frame, text="最小BPM: 0.0", 
                                      font=("メイリオ", 9), fg="#666666")
        self.min_bpm_label.grid(row=0, column=1, sticky="w", padx=(20, 0))
        
        self.max_bpm_label = tk.Label(info_frame, text="最大BPM: 0.0", 
                                      font=("メイリオ", 9), fg="#666666")
        self.max_bpm_label.grid(row=1, column=1, sticky="w", padx=(20, 0))
        
        self.std_dev_label = tk.Label(info_frame, text="標準偏差: ---", 
                                      font=("メイリオ", 9), fg="#666666")
        self.std_dev_label.grid(row=2, column=1, sticky="w", padx=(20, 0))
        
        # === タップボタン ===
        tap_frame = tk.Frame(left_frame)
        tap_frame.pack(fill="x", pady=12)
        
        self.tap_button = tk.Button(tap_frame, text="T A P (スペースキー)", 
                                   command=self.on_tap_with_feedback,
                                   font=("メイリオ", 16, "bold"),
                                   bg="#4CAF50", fg="white",
                                   height=2,
                                   relief="raised", borderwidth=2)
        self.tap_button.pack(fill="x", expand=True)
        
        # === 履歴表示 ===
        history_frame = tk.LabelFrame(left_frame, text="計測履歴", padx=10, pady=10)
        history_frame.pack(fill="both", expand=True, pady=(8, 0))
        
        history_container = tk.Frame(history_frame)
        history_container.pack(fill="both", expand=True)
        
        self.history_listbox = tk.Listbox(history_container, 
                                          height=8,
                                          font=("MS Gothic", 9),
                                          relief="flat",
                                          selectbackground="#e0e0e0")
        self.history_listbox.pack(fill="both", expand=True, padx=2, pady=2)
        self.history_listbox.insert(0, "タップして計測開始")
        self.history_listbox.insert(1, "スペースキーを押すか")
        self.history_listbox.insert(2, "TAPボタンをクリック")
        
        # === ボタンフレーム ===
        button_frame = tk.Frame(left_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        # ボタンを横並びに等間隔で配置
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        
        # リセットボタン
        reset_btn = tk.Button(button_frame, text="リセット", 
                             command=self.reset_bpm,
                             width=11, font=("メイリオ", 9),
                             bg="#f44336", fg="white")
        reset_btn.grid(row=0, column=0, padx=2, pady=3)
        
        # TJA挿入ボタン
        insert_btn = tk.Button(button_frame, text="TJAに挿入", 
                              command=self.insert_bpm_to_tja,
                              width=11, font=("メイリオ", 9),
                              bg="#2196F3", fg="white")
        insert_btn.grid(row=0, column=1, padx=2, pady=3)
        
        # 閉じるボタン
        close_btn = tk.Button(button_frame, text="閉じる", 
                             command=on_bpm_window_close,
                             width=11, font=("メイリオ", 9))
        close_btn.grid(row=0, column=2, padx=2, pady=3)
        
        # === 右側フレーム: グラフ表示 ===
        right_frame = tk.LabelFrame(main_frame, text="BPM推移グラフ", padx=10, pady=10)
        right_frame.pack(side="right", fill="both", expand=True)
        
        # matplotlibが利用可能であることを前提
        self.matplotlib_available = True
        
        # グラフ用のフレーム
        graph_container = tk.Frame(right_frame)
        graph_container.pack(fill="both", expand=True)
        
        # 図の作成
        fig = Figure(figsize=(6, 4), dpi=100)
        self.bpm_ax = fig.add_subplot(111)
        self.bpm_ax.set_title('BPM推移グラフ')
        self.bpm_ax.set_xlabel('タップ番号')
        self.bpm_ax.set_ylabel('BPM')
        self.bpm_ax.grid(True, alpha=0.3)
        
        # 初期化: 空のグラフ
        self.bpm_line, = self.bpm_ax.plot([], [], 'b-o', linewidth=2, markersize=6, label='BPM')
        self.avg_line, = self.bpm_ax.plot([], [], 'r--', linewidth=1.5, label='平均BPM')
        self.bpm_ax.legend()
        
        # 初期範囲設定（広めの範囲）
        self.bpm_ax.set_ylim(0, 300)  # 上限なし対応のため初期範囲を広く
        self.bpm_ax.set_xlim(0.5, 10.5)
        
        # Tkinterキャンバスの作成
        self.canvas = FigureCanvasTkAgg(fig, master=graph_container)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        # ツールバーの追加（オプション）
        toolbar_frame = tk.Frame(right_frame)
        toolbar_frame.pack(fill="x")
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()
        
        # グラフ制御ボタン
        graph_controls = tk.Frame(right_frame)
        graph_controls.pack(fill="x", pady=(5, 0))
                        
        tk.Button(graph_controls, text="間隔グラフ", 
                  command=self.show_interval_graph,
                  width=12, font=("メイリオ", 8)).pack(side="left", padx=2)
        
        # グラフ関連の変数を保存
        self.bpm_fig = fig
        self.bpm_canvas = self.canvas
        
        # キーバインド
        self.bpm_window.bind("<space>", lambda e: self.on_tap_with_feedback())
        
        # フォーカス設定
        self.bpm_window.focus_set()
        self.tap_button.focus_set()
        
        # 定期的な更新処理を開始
        self.start_bpm_refresh_timer()
    
    def update_bpm_graph(self):
        """BPMグラフを更新（常にY軸が現在のBPM値に追従、上限なし）"""
        # 履歴データがない場合は何もしない
        if not hasattr(self, 'bpm_history') or not self.bpm_history:
            return
        
        # 最新20個のデータを表示
        recent_history = self.bpm_history[-20:] if len(self.bpm_history) > 20 else self.bpm_history
        x_data = list(range(1, len(recent_history) + 1))
        
        # データをグラフに設定
        self.bpm_line.set_data(x_data, recent_history)
        
        # 平均値の線を描画
        if recent_history:
            avg = sum(recent_history) / len(recent_history)
            self.avg_line.set_data([x_data[0], x_data[-1]], [avg, avg])
        
        # Y軸の範囲を自動調整 - 常に現在のBPM値に追従（上限なし）
        if recent_history:
            current_bpm = recent_history[-1]  # 最新のBPM値
            
            # 履歴全体の最小値と最大値を取得
            history_min = min(recent_history)
            history_max = max(recent_history)
            
            # 現在値を中心に表示範囲を計算
            # 1. 現在値±15%の範囲（最低±10BPM）
            range_percent = 0.15  # 15%
            range_by_percent = current_bpm * range_percent
            
            # 2. 履歴の変動幅の半分（最低±5BPM）
            range_by_history = (history_max - history_min) / 2
            
            # 表示範囲の半径を決定（大きい方を採用、ただし最低±10BPM）
            range_radius = max(range_by_percent, range_by_history, 10.0)
            
            # 表示範囲の計算
            center = current_bpm
            min_bpm = center - range_radius
            max_bpm = center + range_radius
            
            # 下限が0未満にならないように調整（上限はそのまま）
            if min_bpm < 0:
                min_bpm = 0
                # 上限を調整して中心を維持
                if center * 2 > max_bpm:
                    max_bpm = center * 2
                else:
                    # 現在値が上限より中心に近くなるように調整
                    max_bpm = max(max_bpm, center * 1.5)
            
            # BPMが非常に低い場合（30以下）の特別処理
            if current_bpm < 30:
                min_bpm = 0
                max_bpm = max(60, current_bpm * 3)  # 少なくとも60BPMまで表示
            
            # BPMが非常に高い場合（300以上）の特別処理
            elif current_bpm > 300:
                # 高いBPMでも下方向に十分な余裕を持つ
                min_bpm = max(0, current_bpm * 0.7)
                # 上限は現在値の1.3倍か、履歴最大値の1.1倍の大きい方
                max_bpm = max(current_bpm * 1.3, history_max * 1.1)
            
            # Y軸の範囲を設定
            self.bpm_ax.set_ylim(min_bpm, max_bpm)
            
            # X軸の範囲を調整（常に最新のデータが右端に表示されるように）
            if len(x_data) > 10:
                # 最新10個を表示
                display_start = max(0, len(x_data) - 10)
                self.bpm_ax.set_xlim(x_data[display_start] - 0.5, x_data[-1] + 0.5)
            else:
                # データが少ない場合は全て表示
                self.bpm_ax.set_xlim(x_data[0] - 0.5, x_data[-1] + 0.5)
        
        # グラフの更新
        self.bpm_ax.relim()
        self.bpm_ax.autoscale_view(scaley=False)  # scaley=FalseでY軸の自動調整を無効化
        self.bpm_canvas.draw()
    
    def show_interval_graph(self):
        """タップ間隔グラフを表示"""
        if not self.matplotlib_available or not hasattr(self, 'intervals'):
            return
        
        if not self.intervals:
            messagebox.showinfo("データなし", "タップ間隔のデータがありません", parent=self.bpm_window)
            return
        
        # 新しいウィンドウを作成
        interval_window = Toplevel(self.bpm_window)
        interval_window.title("タップ間隔グラフ")
        interval_window.geometry("600x500")
            
        fig = Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        
        # 間隔データをプロット（ミリ秒単位で表示）
        intervals_ms = [interval * 1000 for interval in self.intervals]
        x_data = list(range(1, len(intervals_ms) + 1))
        
        ax.plot(x_data, intervals_ms, 'g-s', linewidth=2, markersize=8, label='タップ間隔')
        ax.axhline(y=sum(intervals_ms)/len(intervals_ms), color='r', linestyle='--', label='平均間隔')
        
        ax.set_title('タップ間隔推移 (ミリ秒)')
        ax.set_xlabel('間隔番号')
        ax.set_ylabel('間隔 (ms)')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # 統計情報を追加
        if len(intervals_ms) >= 2:
            avg_ms = sum(intervals_ms) / len(intervals_ms)
            min_ms = min(intervals_ms)
            max_ms = max(intervals_ms)
            std_ms = (sum((x - avg_ms) ** 2 for x in intervals_ms) / len(intervals_ms)) ** 0.5
            
            stats_text = f"平均: {avg_ms:.1f}ms\n最小: {min_ms:.1f}ms\n最大: {max_ms:.1f}ms\n標準偏差: {std_ms:.1f}ms"
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                    verticalalignment='top', fontsize=10,
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # キャンバスの作成
        canvas = FigureCanvasTkAgg(fig, master=interval_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        # 閉じるボタン
        tk.Button(interval_window, text="閉じる", 
                  command=interval_window.destroy,
                  font=("メイリオ", 10)).pack(pady=10)
    
    def show_bpm_graph(self):
        """BPMグラフをメインウィンドウに表示（既に表示されている）"""
        # すでに表示されているので何もしない
        pass
    
    def clear_bpm_graph(self):
        """グラフをクリア（初期範囲にリセット）"""
        if not self.matplotlib_available:
            return
        
        # グラフデータをクリア
        self.bpm_line.set_data([], [])
        self.avg_line.set_data([], [])
        
        # 初期範囲にリセット（上限なしの広めの範囲）
        self.bpm_ax.set_ylim(0, 300)  # 初期は0-300BPM
        self.bpm_ax.set_xlim(0.5, 10.5)
        
        # グラフを再描画
        self.bpm_canvas.draw()
    
    def save_bpm_graph(self):
        """グラフを画像として保存"""
        if not self.matplotlib_available:
            messagebox.showwarning("保存不可", "グラフが表示されていません", parent=self.bpm_window)
            return
        
        # 保存先を選択
        from tkinter import filedialog
        import datetime
        
        default_filename = f"bpm_graph_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = filedialog.asksaveasfilename(
            title="グラフを保存",
            defaultextension=".png",
            filetypes=[("PNG画像", "*.png"), ("JPEG画像", "*.jpg"), ("すべてのファイル", "*.*")],
            initialfile=default_filename
        )
        
        if filepath:
            try:
                self.bpm_fig.savefig(filepath, dpi=300, bbox_inches='tight')
                messagebox.showinfo("保存成功", f"グラフを保存しました:\n{filepath}", parent=self.bpm_window)
            except Exception as e:
                messagebox.showerror("保存失敗", f"グラフの保存に失敗しました:\n{e}", parent=self.bpm_window)
    
    def on_tap(self):
        """タップ時の処理（グラフ更新付き）"""
        if not hasattr(self, 'bpm_window') or not self.bpm_window or not self.bpm_window.winfo_exists():
            return
        
        import time
        current_time = time.time()
        
        # タップ時間を確実に記録
        if not hasattr(self, 'tap_times'):
            self.tap_times = []
        if not hasattr(self, 'intervals'):
            self.intervals = []
        
        # 最初のタップ
        if not self.tap_times:
            self.tap_times.append(current_time)
            self.tap_count_label.config(text="タップ: 1")
            self.bpm_display.config(text="--.--")
            self.interval_label.config(text="前回間隔: ---")
            return
        
        # 直前のタップとの間隔を計算
        last_time = self.tap_times[-1]
        interval = current_time - last_time
        
        # 間隔を保存
        self.intervals.append(interval)
        
        # 間隔ラベルを更新
        self.interval_label.config(text=f"前回間隔: {interval:.3f}秒")
        
        # 修正: BPM制限を緩和（600BPMまで許容）
        if interval < 0.1:  # 600BPM以上は無視（0.1秒未満）
            return
        if interval > 3.0:  # 20BPM以下はリセット
            self.reset_bpm()
            self.tap_times.append(current_time)
            self.tap_count_label.config(text="タップ: 1")
            return
        
        # タップを記録
        self.tap_times.append(current_time)
        
        # 保持するタップ数を制限（最新15回）
        if len(self.tap_times) > 15:
            self.tap_times.pop(0)
        
        # 間隔リストも調整
        if len(self.intervals) > 14:
            self.intervals.pop(0)
        
        tap_count = len(self.tap_times)
        self.tap_count_label.config(text=f"タップ: {tap_count}")
        
        # 2回以上タップがあればBPM計算
        if tap_count >= 2:
            time_span = self.tap_times[-1] - self.tap_times[0]
            
            if time_span > 0:
                # ★ 上限なし版のBayes BPM計算を使用 ★
                current_bpm = self.bayes_bpm_estimate_article(self.tap_times)
                
                # 結果を保存
                self.bpm_result = current_bpm
                
                # 表示更新
                self.bpm_display.config(text=f"{current_bpm:.1f}")
                
                # BPM履歴
                if not hasattr(self, 'bpm_history'):
                    self.bpm_history = []
                
                self.bpm_history.append(current_bpm)
                if len(self.bpm_history) > 20:
                    self.bpm_history.pop(0)
                
                # 平均BPM
                if self.bpm_history:
                    avg_bpm = sum(self.bpm_history) / len(self.bpm_history)
                    self.avg_bpm_label.config(text=f"平均: {avg_bpm:.1f}")
                    
                    # 最小・最大BPM
                    if len(self.bpm_history) >= 2:
                        min_bpm = min(self.bpm_history)
                        max_bpm = max(self.bpm_history)
                        self.min_bpm_label.config(text=f"最小BPM: {min_bpm:.1f}")
                        self.max_bpm_label.config(text=f"最大BPM: {max_bpm:.1f}")
                        
                        # 標準偏差
                        if len(self.bpm_history) >= 2:
                            variance = sum((b - avg_bpm) ** 2 for b in self.bpm_history) / len(self.bpm_history)
                            std_dev = variance ** 0.5
                            self.std_dev_label.config(text=f"標準偏差: {std_dev:.2f}")
                
                # 履歴表示更新
                self.update_history_listbox_wide()
                
                # 安定度表示
                sigma = self.bpm_sigma_from_taps(self.tap_times)
                
                if sigma is not None:
                    avg_bpm = self.bpm_result if self.bpm_result > 0 else 1
                    sigma_percent = sigma / avg_bpm * 100
                    
                    self.stability_label.config(
                        text=f"安定度 σ = {sigma:.2f} BPM ({sigma_percent:.2f}%)",
                        fg="#333333"
                    )
                else:
                    self.stability_label.config(
                        text="安定度 σ = ---",
                        fg="#666666"
                    )
                
                # グラフを更新
                if hasattr(self, 'matplotlib_available') and self.matplotlib_available:
                    self.update_bpm_graph()
    
    def reset_bpm(self):
        """BPMカウンターを完全にリセット"""
        # 変数のリセット
        if hasattr(self, 'tap_times'):
            self.tap_times = []
        if hasattr(self, 'bpm_history'):
            self.bpm_history = []
        if hasattr(self, 'bpm_result'):
            self.bpm_result = 0
        if hasattr(self, 'intervals'):
            self.intervals = []
        
        # 表示のリセット
        if hasattr(self, 'bpm_display') and self.bpm_display:
            self.bpm_display.config(text="0.0")
        if hasattr(self, 'tap_count_label') and self.tap_count_label:
            self.tap_count_label.config(text="タップ: 0")
        if hasattr(self, 'avg_bpm_label') and self.avg_bpm_label:
            self.avg_bpm_label.config(text="平均: 0.0")
        if hasattr(self, 'stability_label') and self.stability_label:
            self.stability_label.config(text="安定度: ---", fg="black")
        if hasattr(self, 'interval_label') and self.interval_label:
            self.interval_label.config(text="前回間隔: ---")
        if hasattr(self, 'min_bpm_label') and self.min_bpm_label:
            self.min_bpm_label.config(text="最小BPM: 0.0")
        if hasattr(self, 'max_bpm_label') and self.max_bpm_label:
            self.max_bpm_label.config(text="最大BPM: 0.0")
        if hasattr(self, 'std_dev_label') and self.std_dev_label:
            self.std_dev_label.config(text="標準偏差: ---")
        
        # 履歴表示のリセット
        if hasattr(self, 'history_listbox') and self.history_listbox:
            self.history_listbox.delete(0, tk.END)
            self.history_listbox.insert(0, "リセットされました")
            self.history_listbox.insert(1, "タップして再計測してください")
        
        # グラフのリセット
        if hasattr(self, 'clear_bpm_graph'):
            self.clear_bpm_graph()
    
    def update_history_listbox_wide(self):
        """履歴リストボックスを更新"""
        if not hasattr(self, 'history_listbox') or not self.history_listbox:
            return
        
        self.history_listbox.delete(0, tk.END)
        
        if hasattr(self, 'bpm_history') and self.bpm_history:
            recent = self.bpm_history[-20:]
            
            for i, bpm in enumerate(recent, 1):
                # 安定度インジケーター
                if i > 2 and len(recent) >= 3:
                    prev_avg = sum(recent[max(0, i-3):i-1]) / min(3, i-1)
                    diff = abs(bpm - prev_avg)
                    diff_percent = (diff / prev_avg * 100) if prev_avg > 0 else 0
                    
                    if diff_percent < 2:
                        indicator = "✓"
                    elif diff_percent < 5:
                        indicator = "~"
                    else:
                        indicator = "!"
                    
                    self.history_listbox.insert(tk.END, f"{i:2d}. {bpm:6.1f} BPM {indicator}")
                else:
                    self.history_listbox.insert(tk.END, f"{i:2d}. {bpm:6.1f} BPM")
        else:
            self.history_listbox.insert(0, "タップして計測開始")
            self.history_listbox.insert(1, "スペースキーを押すか")
            self.history_listbox.insert(2, "TAPボタンをクリック")
        
        # 最新項目を選択状態に
        if self.history_listbox.size() > 0:
            self.history_listbox.selection_set(tk.END)
            self.history_listbox.see(tk.END)

    def start_bpm_refresh_timer(self):
        """定期的な更新タイマーを開始"""
        if hasattr(self, 'bpm_refresh_id'):
            # 既存のタイマーがあればキャンセル
            self.bpm_window.after_cancel(self.bpm_refresh_id)
        
        def refresh_bpm_data():
            if hasattr(self, 'bpm_window') and self.bpm_window and self.bpm_window.winfo_exists():
                try:
                    # 古すぎるタップデータをクリーンアップ（30秒以上前）
                    import time
                    current_time = time.time()
                    if hasattr(self, 'tap_times') and self.tap_times:
                        # 30秒以上経過したタップを削除
                        self.tap_times = [t for t in self.tap_times if current_time - t < 30.0]
                        
                        # タップが少なくなったら表示を更新
                        if len(self.tap_times) < 2:
                            if hasattr(self, 'bpm_display') and self.bpm_display:
                                self.bpm_display.config(text="0.0")
                            if hasattr(self, 'avg_bpm_label') and self.avg_bpm_label:
                                self.avg_bpm_label.config(text="平均: 0.0")
                            
                            # 履歴も更新
                            if hasattr(self, 'history_listbox') and self.history_listbox:
                                self.history_listbox.delete(0, tk.END)
                                self.history_listbox.insert(0, "計測がタイムアウトしました")
                                self.history_listbox.insert(1, "再度タップしてください")
                except Exception as e:
                    print(f"BPM更新エラー: {e}")
                
                # 5秒後に再度実行
                if hasattr(self, 'bpm_window') and self.bpm_window and self.bpm_window.winfo_exists():
                    self.bpm_refresh_id = self.bpm_window.after(5000, refresh_bpm_data)
        
        # 5秒後に初回実行
        self.bpm_refresh_id = self.bpm_window.after(5000, refresh_bpm_data)
            
    def on_tap_with_feedback(self):
        """タップ時の処理（視覚的フィードバック付き）"""
        # ボタンの視覚的フィードバック
        if hasattr(self, 'tap_button') and self.tap_button:
            original_bg = self.tap_button.cget("bg")
            self.tap_button.config(bg="#45a049", relief="sunken")
            self.bpm_window.after(80, lambda: self.tap_button.config(bg=original_bg, relief="raised") if hasattr(self, 'tap_button') and self.tap_button else None)
        
        # 実際のタップ処理
        self.on_tap() 
        
    def insert_bpm_to_tja(self):
        """計算したBPMをTJAに挿入"""
        if not hasattr(self, 'bpm_history') or not self.bpm_history:
            messagebox.showwarning("BPM未計測", 
                                  "先にタップしてBPMを計測してください。\n（最低2回以上のタップが必要）", 
                                  parent=self.bpm_window if hasattr(self, 'bpm_window') and self.bpm_window else None)
            return
        
        # 平均BPMを使用
        avg_bpm = sum(self.bpm_history) / len(self.bpm_history)
        
        # 小数点以下を適切に丸める
        if avg_bpm < 100:
            rounded_bpm = round(avg_bpm, 1)  # 低速曲は小数点1桁
        else:
            rounded_bpm = round(avg_bpm)     # 高速曲は整数
        
        # 安定度メッセージ
        stability_msg = ""
        if len(self.bpm_history) >= 3:
            recent = self.bpm_history[-3:]
            max_bpm = max(recent)
            min_bpm = min(recent)
            variation = (max_bpm - min_bpm) / avg_bpm * 100 if avg_bpm > 0 else 100
            stability = max(0, 100 - variation)
            
            if stability > 90:
                stability_msg = "（非常に安定）"
            elif stability > 75:
                stability_msg = "（安定）"
            else:
                stability_msg = "（不安定 - 再計測推奨）"
        
        response = messagebox.askyesno(
            "BPM挿入確認",
            f"計測結果:\n"
            f"最終: {self.bpm_result:.1f} BPM\n"
            f"平均: {avg_bpm:.1f} BPM {stability_msg}\n\n"
            f"以下の値をTJAに挿入しますか？\n"
            f"BPM:{rounded_bpm}",
            parent=self.bpm_window if hasattr(self, 'bpm_window') and self.bpm_window else None
        )
        
        if response:
            self.text.insert(tk.INSERT, f"BPM:{rounded_bpm}\n")
            self.text.see(tk.INSERT)
            # 構文ハイライトを更新
            self.root.after(10, self.apply_syntax_highlighting)
            messagebox.showinfo("挿入完了", 
                              f"BPM:{rounded_bpm} を挿入しました！\nF5でプレビューして確認してください。")
    
    def play_tap_sound(self):
        """タップ音を再生（オプション機能）"""
        try:
            import winsound
            winsound.Beep(800, 50)  # Windows用
        except:
            try:
                import os
                # macOS/Linux用（オプション）
                os.system('echo -e "\\a"')
            except:
                pass

    def create_distribution_zip(self):
        """ツール → 配布用ZIPを作成（readmeなし・画像も自動収集）"""
        if not self.current_file:
            messagebox.showwarning("未保存", "先にTJAファイルを保存してください。")
            return

        tja_path = self.current_file
        tja_dir = os.path.dirname(tja_path)
        tja_name = os.path.basename(tja_path)
        song_title = os.path.splitext(tja_name)[0]

        # WAVEファイルを探す（拡張子に関係なく、見つからなくても続行）
        missing_files = []
        wave_path = None
        wave_name = None
        
        # TJA内のWAVE:行から音声ファイル名を取得
        content = self.text.get("1.0", tk.END)
        match = re.search(r"^WAVE:\s*([^\r\n#;\"']+)", content, re.MULTILINE | re.IGNORECASE)
        if match:
            wave_value = match.group(1).strip().strip('"\'')
            wave_path = self.resolve_wave_file_path(wave_value, tja_dir)
            if wave_path and os.path.exists(wave_path):
                wave_name = os.path.basename(wave_path)
            else:
                # WAVEファイルが見つからない場合、警告リストに追加
                missing_files.append(wave_value)
                wave_path = None

        # 画像ファイルを自動収集（png/jpg/jpeg/gif/bmp）
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        extra_files = []
        for f in os.listdir(tja_dir):
            if f.lower().endswith(image_exts):
                full_path = os.path.join(tja_dir, f)
                if os.path.isfile(full_path):
                    # WAVEファイルと同名でない場合のみ追加
                    if wave_name and f.lower() == wave_name.lower():
                        continue
                    if f.lower() != tja_name.lower():
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
                # TJAファイルは必ず追加
                zf.write(tja_path, arcname=tja_name)
                
                # WAVEファイルがあれば追加
                if wave_path and os.path.exists(wave_path):
                    zf.write(wave_path, arcname=wave_name)
                
                # 画像ファイルを追加
                for img_path in extra_files:
                    zf.write(img_path, arcname=os.path.basename(img_path))

            # 完了メッセージを作成
            file_list = f"・{tja_name}"
            if wave_path and os.path.exists(wave_path):
                file_list += f"\n・{wave_name}"
            if extra_files:
                file_list += "\n・" + "\n・".join(os.path.basename(p) for p in extra_files)
            else:
                file_list += "\n（画像ファイルは検出されませんでした）"

            success_msg = (
                f"以下のファイルを含むZIPを作成しました。\n\n"
                f"{os.path.basename(zip_path)}\n\n"
                f"{file_list}\n\n"
                f"このままアップロード可能です。"
            )
            
            # 見つからなかったファイルがある場合、警告を追加
            if missing_files:
                success_msg += "\n\n" + "⚠ 以下の音声ファイルが見つかりませんでした:\n"
                success_msg += "\n".join(f"・{f}" for f in missing_files)
                messagebox.showwarning("配布用ZIP作成完了（警告あり）", success_msg)
            else:
                messagebox.showinfo("配布用ZIP作成完了", success_msg)

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
        
        # Use the shared helper method
        return self.resolve_wave_file_path(wave_name, os.path.dirname(self.current_file) if self.current_file else None)
    
    def resolve_wave_file_path(self, wave_value, base_dir):
        """
        共通のWAVEファイルパス解決メソッド
        Args:
            wave_value: TJAのWAVE:行から取得した値
            base_dir: 基準ディレクトリ（TJAファイルのディレクトリなど）
        Returns:
            解決されたファイルパス、見つからない場合はNone
        """
        if not wave_value:
            return None
        
        wave_name = wave_value.strip().strip('"\'')
        if not wave_name:
            return None
        
        # 1. 基準ディレクトリ（TJAと同じフォルダ）にあるか
        if base_dir:
            candidate = os.path.join(base_dir, wave_name)
            if os.path.exists(candidate):
                return candidate
        
        # 2. 絶対パスならそのまま
        if os.path.isabs(wave_name) and os.path.exists(wave_name):
            return wave_name
        
        # 3. カレントフォルダ
        candidate = os.path.join(os.getcwd(), wave_name)
        if os.path.exists(candidate):
            return candidate
        
        # 見つからない場合はNone
        return None
    
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
        self.text.insert("1.0", "\n".join(new_lines))
        self.root.after(10, self.apply_syntax_highlighting)
        messagebox.showinfo("完了", f"OFFSET を {offset_value} に設定しました！\nF5で確認してください")
        
    def smart_comma_on_enter(self, event=None,Nopreview=None):
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

            # 2. 現在の行が譜面行か判定(0~8のどれかを含むか)
            stripped = current_line_text.rstrip()
            if not any(c in "012345678" for c in stripped):
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
            return Nopreview
    
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
            self.save_config()
            messagebox.showinfo("完了", "最近使ったファイルの履歴をクリアしました")

    def delete_recent_history_item(self):
        """
        最近使ったファイルの履歴から選択した項目を削除するダイアログ（ファイル本体は削除しない）。
        メニューに追加する例:
          self.recent_menu.add_command(label="履歴から削除...", command=self.delete_recent_history_item)
        """
        if not self.recent_files:
            messagebox.showinfo("履歴なし", "最近使ったファイルの履歴は空です。")
            return
    
        # 単一ウィンドウ化
        if hasattr(self, "_delete_recent_win") and getattr(self, "_delete_recent_win"):
            try:
                if self._delete_recent_win.winfo_exists():
                    self._delete_recent_win.lift()
                    return
            except:
                pass
    
        win = Toplevel(self.root)
        self._delete_recent_win = win
        win.title("最近使ったファイル - 履歴から削除")
        win.geometry("640x320")
        win.transient(self.root)
        win.grab_set()
    
        Label(win, text="履歴から削除するファイルを選択してください", font=("メイリオ", 11, "bold")).pack(pady=8)
    
        frame = Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    
        scrollbar = Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
    
        lb = Listbox(frame, yscrollcommand=scrollbar.set, font=("MS Gothic", 10), selectmode="single")
        for p in self.recent_files:
            display = p
            if len(display) > 80:
                display = "…" + display[-77:]
            lb.insert("end", display)
        lb.pack(fill="both", expand=True)
        scrollbar.config(command=lb.yview)
    
        btn_frame = Frame(win)
        btn_frame.pack(pady=8)

        def _remove_selected():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("未選択", "削除する項目を選択してください。", parent=win)
                return
            idx = sel[0]
            path = self.recent_files[idx]
    
            if not messagebox.askyesno("確認", f"以下の履歴項目を削除しますか？\n\n{path}", parent=win):
                return
    
            try:
                if path in self.recent_files:
                    self.recent_files.remove(path)
                # メニュー更新と設定保存
                self.update_recent_menu()
                self.save_config()
            except Exception as e:
                messagebox.showerror("エラー", f"履歴の更新に失敗しました:\n{e}", parent=win)
                return
    
            messagebox.showinfo("完了", "履歴から削除しました。", parent=win)
            win.destroy()
    
        Button(btn_frame, text="履歴から削除", width=18, command=_remove_selected).pack(side="left", padx=6)
        Button(btn_frame, text="キャンセル", width=12, command=lambda: win.destroy()).pack(side="left", padx=6)

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
        # スクロール完了後に行番号を更新
        self.root.after_idle(self.update_linenumbers)

    def toggle_dark_mode(self, force=None, save=True):
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
            
            # スクロールバーカラー（ダークモード）
            scroll_bg = "#3c3c3c"
            scroll_trough = "#1e1e1e"
            scroll_arrow = "#d4d4d4"
            
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
            
            # スクロールバーカラー（ライトモード）
            scroll_bg = "#c0c0c0"
            scroll_trough = "#f0f0f0"
            scroll_arrow = "black"
        
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
        
        # ====== 5. スクロールバースタイル（常にclamテーマを使用）=====
        style = ttk.Style()
        style.theme_use('clam')  # 常にclamテーマを使用
        
        # 縦スクロールバーの設定
        style.configure("Vertical.TScrollbar", 
                        background=scroll_bg, 
                        troughcolor=scroll_trough,
                        arrowcolor=scroll_arrow,
                        bordercolor=scroll_trough,
                        gripcount=0,
                        darkcolor=scroll_bg,
                        lightcolor=scroll_bg)
        
        # 横スクロールバーの設定
        style.configure("Horizontal.TScrollbar", 
                        background=scroll_bg, 
                        troughcolor=scroll_trough,
                        arrowcolor=scroll_arrow,
                        bordercolor=scroll_trough,
                        gripcount=0,
                        darkcolor=scroll_bg,
                        lightcolor=scroll_bg)
        
        # アクティブなスクロールバーの色も設定
        if self.dark_mode:
            style.map("Vertical.TScrollbar",
                     background=[('active', '#4c4c4c'), ('!active', scroll_bg)],
                     arrowcolor=[('active', '#ffffff'), ('!active', scroll_arrow)])
            style.map("Horizontal.TScrollbar",
                     background=[('active', '#4c4c4c'), ('!active', scroll_bg)],
                     arrowcolor=[('active', '#ffffff'), ('!active', scroll_arrow)])
        else:
            style.map("Vertical.TScrollbar",
                     background=[('active', '#a0a0a0'), ('!active', scroll_bg)],
                     arrowcolor=[('active', '#000000'), ('!active', scroll_arrow)])
            style.map("Horizontal.TScrollbar",
                     background=[('active', '#a0a0a0'), ('!active', scroll_bg)],
                     arrowcolor=[('active', '#000000'), ('!active', scroll_arrow)])
        
        # ====== 6. 構文ハイライト色の更新 ======
        self.text.tag_configure("header", foreground=header_fg)
        self.text.tag_configure("comment", foreground=comment_fg)
        self.text.tag_configure("command", foreground=command_fg)
        self.text.tag_configure("error", foreground=error_fg)
        self.text.tag_configure("todo", background=todo_bg)
        self.text.tag_configure("number", foreground=number_fg)
        
        
        # ====== 7. 行番号とステータスバーの更新 ======
        self.update_linenumbers()
        self.update_statusbar()
        
        # ====== 8. ポップアップメニューの色 ======
        if hasattr(self, 'popup'):
            if self.dark_mode:
                self.popup.config(bg="#2d2d30", fg="#d4d4d4", 
                                activebackground="#3e3e42", 
                                activeforeground="#ffffff")
            else:
                self.popup.config(bg="SystemMenu", fg="SystemMenuText",
                                activebackground="SystemHighlight",
                                activeforeground="SystemHighlightText")
        
        # ====== 9. 設定保存 ======
        if save:
            self.save_config()
        
    
        # ====== 10. メニュー表示を更新 ======
        if hasattr(self, 'viewmenu'):
            label = "ライトモードに切り替え" if self.dark_mode else "ダークモードに切り替え"
            try:
                self.viewmenu.entryconfig(0, label=label)
            except:
                pass
        
    
        self._update_main_palette_colors()
    
        # ====== 11. 開いているサブウィンドウにも適用 ======
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
        self.update_title()

    def update_statusbar(self):
        """ステータスバーにブレッドクラム情報と基本情報を表示"""
        try:
            # プレビュー中かどうかをチェック
            if hasattr(self, 'preview_running') and self.preview_running:
                # プレビュー中の場合は特別な表示
                if hasattr(self, 'preview_process') and self.preview_process:
                    # プロセスがまだ生きているか確認
                    try:
                        return_code = self.preview_process.poll()
                        if return_code is not None:
                            # プロセスが終了している
                            self.preview_running = False
                            self.preview_process = None
                        else:
                            # プレビュー中
                            filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
                            self.statusbar.config(
                                text=f"[プレビュー再生中] {filename} - 太鼓さん次郎で再生中..."
                            )
                            # 定期的に更新を続ける
                            self.root.after(200, self.update_statusbar)
                            return
                    except:
                        # エラーが発生した場合
                        self.preview_running = False
                        self.preview_process = None
    
            # 通常のステータスバー表示処理
            line, col = self.text.index(tk.INSERT).split('.')
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
    
            # COURSE 検出は正規表現で行い、前のブロックがあれば先に追加する（名前ずれを防止）
            for i, line_text in enumerate(lines):
                m = re.match(r'^\s*COURSE\s*:\s*(\S+)', line_text, re.I)
                if m:
                    # 既にブロック開始位置がある場合は前ブロックを確定
                    if current_block_start is not None:
                        course_blocks.append((current_block_start, i, current_course_name))
                    # 今回のブロック開始位置とコース名（大文字）を設定
                    current_block_start = i
                    current_course_name = m.group(1).strip().upper()
            # 最後のブロックを追加
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
                    breadcrumb = [filename, "ヘッダー部分", "空行"]
                elif current_line.startswith("#"):
                    # #で始まる命令文の場合は命令文を表示（#START/#END系以外）
                    current_line_upper = current_line.upper()
                    # 先頭トークンで正確に判定（#GOGOEND 等の誤判定を防ぐ）
                    first_tok = current_line_upper.split()[0] if current_line_upper else ""
                    if first_tok in ("#START", "#START P1", "#START P2"):
                        breadcrumb = [filename, "ヘッダー部分", "譜面開始"]
                    elif first_tok == "#END":
                        breadcrumb = [filename, "ヘッダー部分", "譜面終了"]
                    else:
                        command_name = current_line.split()[0] if " " in current_line else current_line
                        breadcrumb = [filename, "ヘッダー部分", command_name]
                else:
                    breadcrumb = [filename, "ヘッダー部分"]
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
                    first_tok = u.split()[0] if u else ""
    
                    # 段位道場の条件行(EXAM1:..EXAM4:)は小節カウントの対象外にする
                    if re.match(r'^\s*EXAM[1-4]\s*:', line_text, re.I):
                        # 何もしない（小節カウントに含めない）
                        continue
    
                    if first_tok in ("#START", "#START P1", "#START P2"):
                        in_chart = True
                        after_end = False
                        measure_count = 0
                        current_measure_started = False
                        continue
    
                    if first_tok == "#END":
                        in_chart = False
                        after_end = True
                        continue
    
                    if in_chart:
                        # コメント行や空行は無視
                        if u.startswith("//") or u.startswith(";") or not u:
                            continue
                        # #で始まる命令文も無視（小節カウントに影響しない）
                        if first_tok.startswith("#") and first_tok not in ("#START", "#END"):
                            continue
                        # ここで小節カウント（, がある行は小節の終端）
                        if "," in line_text:
                            measure_count += 1
                            current_measure_started = False
                        else:
                            current_measure_started = True
    
                # ====== 現在行の状態 ======
                current_line = lines[line_num - 1].strip() if line_num - 1 < len(lines) else ""
                current_line_upper = current_line.upper()
                first_curr = current_line_upper.split()[0] if current_line_upper else ""
                is_start_line = first_curr in ("#START", "#START P1", "#START P2")
                is_end_line = first_curr == "#END"
    
                current_line_in_measure = False
                if in_chart and line_num - 1 < end_line:
                    if current_line and not current_line.startswith("#") and not current_line.startswith("//") and not current_line.startswith(";"):
                        # 現在行が EXAM1..4 の条件行なら小節としてカウントしない
                        if re.match(r'^\s*EXAM[1-4]\s*:', current_line, re.I):
                            current_line_in_measure = False
                        else:
                            current_line_in_measure = True
                            if "," not in current_line:
                                measure_count += 1
    
                # 現在行が空行かチェック
                if not current_line:
                    # 空行の場合
                    breadcrumb = [filename, f"[{current_course}]", "空行"]
                elif current_line.startswith("#"):
                    # #で始まる行の場合
                    if is_start_line:
                        breadcrumb = [filename, f"[{current_course}]", "譜面開始"]
                    elif is_end_line:
                        breadcrumb = [filename, f"[{current_course}]", "譜面終了"]
                    else:
                        command_name = current_line.split()[0] if " " in current_line else current_line
                        breadcrumb = [filename, f"[{current_course}]", command_name]
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
    
            # ブレッドクラム部分を結合
            breadcrumb_text = " > ".join(breadcrumb)
    
            # 基本情報を追加（行番号はここで1回だけ表示）
            status_text = f"{breadcrumb_text} │ 行:{line} 列:{int(col)+1} │ {mode}モード │ F5: 太鼓さん次郎でプレビュー再生"
    
            self.statusbar.config(text=status_text)
    
        except Exception as e:
            print(f"ステータスバー更新エラー: {e}")  # デバッグ用
            # エラー時は簡易表示
            try:
                line, col = self.text.index(tk.INSERT).split('.')
                filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
                mode = "ダーク" if self.dark_mode else "ライト"
                self.statusbar.config(
                    text=f"{filename} │ 行:{line} 列:{int(col)+1} │ {mode}モード"
                )
            except:
                self.statusbar.config(text="準備完了")
    
        # 定期的に更新
        self.root.after(200, self.update_statusbar)

    def get_taikojiro_path(self):
        """設定ファイルから太鼓さん次郎の実行ファイルパスを取得"""
        # 設定ファイルが存在する場合
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    path = config.get("taikojiro_path")
                    
                    # パスが文字列で、ファイルが存在するか確認
                    if path and isinstance(path, str) and os.path.isfile(path):
                        return path
                    else:
                        return None  # 明示的に None を返す
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                return None
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
        """太鼓さん次郎のパスを設定して保存"""
        self.taikojiro_path = path
        self.save_config()


    def setup_taikojiro_path(self):
        """太鼓さん次郎のパスを設定（ファイル保存不要）"""
        # 現在のパスを取得
        current_path = self.get_taikojiro_path()
        
        # ダイアログメッセージの作成
        if current_path and os.path.isfile(current_path):
            message = (
                f"現在の設定パス:\n{current_path}\n\n"
                f"新しいパスを選択しますか？\n"
                f"（キャンセルすると現在の設定を維持します）"
            )
        else:
            message = (
                "太鼓さん次郎の実行ファイル（Taikojiro.exe）を選択してください。\n\n"
                "F5キーでプレビュー再生するために必要です。"
            )
        
        # ファイル選択ダイアログ
        path = filedialog.askopenfilename(
            title="太鼓さん次郎の実行ファイルを選択",
            filetypes=[
                ("実行ファイル", "Taikojiro.exe"),
                ("実行ファイル", "*.exe"),
                ("すべてのファイル", "*.*")
            ],
            initialdir=os.path.dirname(current_path) if current_path and os.path.dirname(current_path) else os.path.expanduser("~")
        )
        
        if path:
            # パスを設定
            self.set_taikojiro_path(path)
            
            # 初回起動フラグを設定（初回セットアップ完了とみなす）
            self.first_launch_completed = True
            self.save_config()
            
            # 確認メッセージ
            filename = os.path.basename(path)
            if filename.lower() == "taikojiro.exe":
                messagebox.showinfo(
                    "設定完了",
                    f"太鼓さん次郎のパスを設定しました！\n\n"
                    f"ファイル: {filename}\n"
                    f"F5キーでプレビュー再生できます。"
                )
            else:
                # ファイル名が違う場合の警告
                if messagebox.askyesno(
                    "確認",
                    f"選択したファイル名は「{filename}」です。\n"
                    f"太鼓さん次郎の実行ファイルは通常「Taikojiro.exe」です。\n\n"
                    f"このパスで設定しますか？"
                ):
                    messagebox.showinfo(
                        "設定完了",
                        f"パスを設定しました。\n"
                        f"プレビュー再生できない場合は正しい実行ファイルを選択してください。"
                    )
                else:
                    # 再設定を促す
                    self.setup_taikojiro_path()
                    return
            
            # 設定を保存
            self.save_config()
            
        else:
            if not current_path:
                # キャンセルしたがパスが未設定の場合
                messagebox.showinfo(
                    "設定が必要",
                    "太鼓さん次郎のパスが設定されていません。\n"
                    "「ツール」→「太鼓さん次郎のパスを設定...」から設定してください。"
                )

    def get_available_courses(self):
        content = self.text.get("1.0", tk.END)
        courses = []
        for line in content.splitlines():
            if line.strip().upper().startswith("COURSE:"):
                courses.append(line.split(":", 1)[1].strip())
        return courses
    
    def select_preview_course(self):
        courses = self.get_available_courses()
        if not courses:
            return None
    
        # カーソル位置のCOURSEを優先
        cursor_course = self.get_course_at_cursor()
        if cursor_course in courses:
            return cursor_course
    
        # 1つしかなければそれ
        if len(courses) == 1:
            return courses[0]
    
        # 複数ある場合だけ選択ダイアログ
        return simpledialog.askstring(
            "プレビューコース選択",
            "再生するコースを入力してください:\n" + " / ".join(courses),
            initialvalue=courses[-1]
        )

    def create_preview_tja(self, course_name):
        lines = self.text.get("1.0", tk.END).splitlines()
        
        header_lines = []
        course_lines = []
        
        in_target = False
        current_course = None
        header_done = False
        
        # ===== STYLE 判定（全体から1回だけ）=====
        is_double = False
        for line in lines:
            u = line.strip().upper()
            if u.startswith("STYLE:"):
                v = u.split(":", 1)[1].strip()
                is_double = v in ("DOUBLE", "2")
                break
        
        in_chart = False
        style_written = False
        
        for line in lines:
            stripped = line.strip()
        
            # ===== コメント完全除外 =====
            if stripped.startswith("//") or stripped.startswith(";"):
                continue
        
            upper = stripped.upper()
        
            # ===== COURSE 検出 =====
            if upper.startswith("COURSE:"):
                current_course = stripped.split(":", 1)[1].strip()
                in_target = (current_course.lower() == course_name.lower())
                header_done = True
                in_chart = False
        
                if in_target:
                    course_lines.append(line)
                continue
        
            # ===== ヘッダー =====
            if not header_done:
                if upper.startswith((
                    "TITLE:",
                    "SUBTITLE:",
                    "WAVE:",
                    "BPM:",
                    "OFFSET:",
                    "SONGVOL:",
                    "SEVOL:",
                    "DEMOSTART:",
                    "SCOREMODE:"
                )):
                    header_lines.append(line)
                continue
        
            # ===== 選択中 COURSE =====
            if in_target:
        
                # COURSE内 STYLE は必ず保持
                if upper.startswith("STYLE:"):
                    course_lines.append(line)
                    style_written = True
                    continue
        
                # ===== Double =====
                if is_double:
                    if upper == "#START P1":
                        # STYLE が無ければ自動補完
                        if not style_written:
                            course_lines.append("STYLE:Double")
                            style_written = True
        
                        in_chart = True
                        course_lines.append(line)
                        continue
        
                    if not in_chart:
                        continue
        
                    course_lines.append(line)
        
                    if upper == "#END":
                        break
        
                # ===== Single =====
                else:
                    # 行内コメント除去
                    clean = line
                    for c in ("//", ";"):
                        if c in clean:
                            clean = clean.split(c, 1)[0].rstrip()
                    if clean:
                        course_lines.append(clean)
        
        if not course_lines:
            raise ValueError(f"COURSE '{course_name}' が見つかりません")
        
        # 元のファイル名から拡張子を取り除く
        base_name = os.path.splitext(os.path.basename(self.current_file))[0] if self.current_file else "preview"
        
        # 難易度を安全なファイル名に変換
        # 日本語の難易度を英数字に変換
        course_mapping = {
            "かんたん": "Easy",
            "ふつう": "Normal", 
            "むずかしい": "Hard",
            "鬼": "Oni",
            "裏鬼": "Edit",
            "0": "Easy",
            "1": "Normal",
            "2": "Hard",
            "3": "Oni",
            "4": "Edit"
        }
        
        # コース名を英数字に変換
        course_safe = course_mapping.get(course_name, course_name)
        
        # ファイル名に使えない文字を除去
        course_safe = re.sub(r'[\\/*?:"<>|]', '_', course_safe)
        
        # 新しいファイル名を生成
        preview_filename = f"{base_name}_{course_safe}.tja"
        preview_path = os.path.join(
            os.path.dirname(self.current_file),
            preview_filename
        )
        
        with open(preview_path, "w", encoding="cp932", errors="replace") as f:
            f.write("\n".join(header_lines + [""] + course_lines))
        
        return preview_path

    def get_course_at_cursor(self):
        content = self.text.get("1.0", tk.END).splitlines()
        cursor_line = int(self.text.index(tk.INSERT).split(".")[0]) - 1
    
        for i in range(cursor_line, -1, -1):
            line = content[i].strip()
            if line.upper().startswith("COURSE:"):
                return line.split(":", 1)[1].strip()
    
        return None

    def is_double_style(self, lines):
        """
        STYLE:Double または STYLE:2 かどうか判定
        """
        for line in lines:
            u = line.strip().upper()
            if u.startswith("STYLE:"):
                value = u[6:].strip()
                return value in ("DOUBLE", "2")
        return False

    def preview_play(self, event=None):
        """F5キー：通常譜面用プレビュー（段位道場は非対応）"""
        
        # === 多重起動防止 ===
        if self.preview_running:
            messagebox.showinfo(
                "プレビュー中",
                "すでにプレビューが起動中です。"
            )
            return
        
        # === ファイル未保存チェック ===
        if not self.current_file:
            messagebox.showwarning(
                "ファイル未保存",
                "プレビュー再生するには、まずファイルを保存してください。"
            )
            return
        
        # === 未保存変更の自動保存 ===
        if self.text.edit_modified():
            if not messagebox.askyesno(
                "自動保存",
                "変更が保存されていません。\n自動で上書き保存しますか？"
            ):
                return
            self.save_file()
        
        # === コース選択（カーソル位置自動） ===
        course = self.select_preview_course()
        if not course:
            return
        
        # === プレビュー用TJA作成 ===
        try:
            preview_tja = self.create_preview_tja(course)
        except Exception as e:
            messagebox.showerror(
                "プレビュー生成失敗",
                str(e)
            )
            return
        
        # === 太鼓さん次郎のパス取得 ===
        tj_path = self.get_taikojiro_path()
        if not tj_path:
            path = filedialog.askopenfilename(
                title="太鼓さん次郎の実行ファイルを選択してください",
                filetypes=[("実行ファイル", "Taikojiro.exe"), ("すべてのファイル", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            if not path:
                return
            self.set_taikojiro_path(path)
            tj_path = path
        
        # === 起動 ===        
        try:
            proc = subprocess.Popen(
                [tj_path, preview_tja],
                cwd=os.path.dirname(tj_path)
            )
        except Exception as e:
            messagebox.showerror(
                "起動失敗",
                f"太鼓さん次郎を起動できませんでした。\n\n{e}"
            )
            return
        
        self.preview_running = True
        self.preview_process = proc
        
        self.statusbar.config(
            text=f"プレビュー起動: {course}"
        )
        
        # === 終了監視＆クリーンアップ ===
        def cleanup_preview():
            try:
                proc.wait()
                
                # 一時TJA削除
                if os.path.exists(preview_tja):
                    os.remove(preview_tja)
                
                # 対応する dat 削除（新しいファイル名形式に対応）
                base = os.path.splitext(preview_tja)[0]
                dirpath = os.path.dirname(preview_tja)
                
                # パターンに一致するすべてのファイルを削除
                import glob
                pattern = os.path.join(dirpath, os.path.basename(base) + "*.dat")
                for dat_file in glob.glob(pattern):
                    try:
                        os.remove(dat_file)
                    except Exception:
                        pass
                
            finally:
                self.preview_running = False
                self.preview_process = None
        
        threading.Thread(
            target=cleanup_preview,
            daemon=True
        ).start()

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
                # dlineinfoを使用(横スクロールに影響されない)
                dline = self.text.dlineinfo(index)
                if dline is None:
                    continue
                
                x, y, width, height, baseline = dline
                
                # 画面内に少しでも表示されている行は描画
                # 修正: より緩い条件で、少しでも見えていれば描画
                if y + height < 0 or y > visible_height:
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
        """OFFSET一括調整ウィンドウを開く（コンパクト固定レイアウト版）"""
        if hasattr(self, 'offset_window') and self.offset_window and self.offset_window.winfo_exists():
            self.offset_window.lift()
            return
        
        # 現在のOFFSET値を取得
        content = self.text.get("1.0", tk.END)
        current_offset = self.get_current_offset(content)
        
        self.offset_window = Toplevel(self.root)
        self.offset_window.title("OFFSET一括調整")
        self.offset_window.geometry("500x400")  # コンパクトサイズ
        self.offset_window.resizable(False, False)
        self.offset_window.transient(self.root)
        
        # グリッド設定（5行1列）
        for i in range(5):
            # 中央の行（2行目）に重み付け
            self.offset_window.grid_rowconfigure(i, weight=1 if i == 2 else 0)
        self.offset_window.grid_columnconfigure(0, weight=1)
        
        # 1行目: タイトルと現在値
        header_frame = tk.Frame(self.offset_window)
        header_frame.grid(row=0, column=0, pady=(10, 5), sticky="n")
        
        tk.Label(header_frame, text="OFFSET一括調整", 
                 font=("メイリオ", 12, "bold")).pack()
        tk.Label(header_frame, text="範囲: -5.0〜+5.0秒", 
                 font=("メイリオ", 8), fg="#666666").pack()
        
        # 現在値表示
        current_frame = tk.Frame(header_frame)
        current_frame.pack(pady=5)
        
        tk.Label(current_frame, text="現在値:", 
                 font=("メイリオ", 9)).pack(side="left", padx=2)
        current_offset_label = tk.Label(current_frame, 
                                        text=f"{current_offset:.3f}" if current_offset is not None else "未設定", 
                                        font=("メイリオ", 9, "bold"), fg="#0066cc")
        current_offset_label.pack(side="left", padx=2)
        
        # 2行目: 調整値表示とスライダー
        slider_frame = tk.Frame(self.offset_window)
        slider_frame.grid(row=1, column=0, pady=10, padx=20, sticky="nsew")
        
        # 調整値表示
        value_display = tk.Frame(slider_frame)
        value_display.pack(pady=(0, 5))
        
        tk.Label(value_display, text="調整値:", font=("メイリオ", 10)).pack(side="left", padx=(0, 5))
        self.offset_value_label = tk.Label(value_display, text="0.000", 
                                            font=("Arial", 24, "bold"), fg="#009688")
        self.offset_value_label.pack(side="left")
        
        # スライダー
        self.offset_slider = tk.Scale(slider_frame, from_=-5.0, to=5.0, resolution=0.001,
                                      orient=tk.HORIZONTAL, length=450,
                                      command=self.on_offset_change,
                                      showvalue=0)
        self.offset_slider.set(0)
        self.offset_slider.pack(pady=5)
        
        # 範囲ラベル（コンパクトに）
        range_frame = tk.Frame(slider_frame)
        range_frame.pack(fill="x")
        tk.Label(range_frame, text="-5.0", font=("メイリオ", 8)).pack(side="left")
        tk.Label(range_frame, text="+5.0", font=("メイリオ", 8)).pack(side="right")
        
        # 3行目: 微調整ボタン（コンパクトに）
        fine_frame = tk.Frame(self.offset_window)
        fine_frame.grid(row=2, column=0, pady=10, sticky="n")
        
        tk.Label(fine_frame, text="微調整:", font=("メイリオ", 9)).pack()
        
        # 微調整ボタン（2段構成）
        btn_row1 = tk.Frame(fine_frame)
        btn_row1.pack(pady=3)
        
        # マイナス調整ボタン
        tk.Button(btn_row1, text=" -0.1 ", command=lambda: self.adjust_offset(-0.1),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        tk.Button(btn_row1, text="-0.01", command=lambda: self.adjust_offset(-0.01),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        tk.Button(btn_row1, text="-0.001", command=lambda: self.adjust_offset(-0.001),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        
        # リセットボタン
        reset_btn = tk.Button(btn_row1, text="リセット", command=lambda: self.offset_slider.set(0),
                   width=7, font=("メイリオ", 8))
        reset_btn.pack(side="left", padx=5)
        
        # プラス調整ボタン
        tk.Button(btn_row1, text="+0.001", command=lambda: self.adjust_offset(0.001),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        tk.Button(btn_row1, text="+0.01", command=lambda: self.adjust_offset(0.01),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        tk.Button(btn_row1, text=" +0.1 ", command=lambda: self.adjust_offset(0.1),
                  width=6, font=("メイリオ", 8)).pack(side="left", padx=1)
        
        # 4行目: 適用ボタン（下端に固定）
        apply_frame = tk.Frame(self.offset_window)
        apply_frame.grid(row=3, column=0, pady=(10, 15), sticky="s")
        
        # 適用ボタン
        apply_btn = tk.Button(apply_frame, text="適用してTJAに挿入", command=self.apply_offset,
                   width=18, font=("メイリオ", 10, "bold"),
                   bg="#4CAF50", fg="white")
        apply_btn.pack(side="left", padx=5)
        
        # 閉じるボタン
        close_btn = tk.Button(apply_frame, text="閉じる", command=self.offset_window.destroy,
                   width=10, font=("メイリオ", 9))
        close_btn.pack(side="left", padx=5)
        
        # 保存用変数
        self.original_offset = current_offset
    
    def get_current_offset(self, content):
        """現在のOFFSET値を取得"""
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
        current = self.offset_slider.get()
        new_value = current + delta
        # スライダーの min/max を取得してそれに合わせる
        minv = float(self.offset_slider.cget("from"))
        maxv = float(self.offset_slider.cget("to"))
        new_value = max(min(new_value, maxv), minv)
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
            m = re.match(r"^\s*course:\s*([^\s#;]+)", line, re.I)
            if m:
                c = m.group(1).strip().lower()
                current = map_course.get(c, c.capitalize())
                current_level = "?"
                # If we were inside a chart, finalize previous
                # (some TJA's may omit #END; ensure separate charts are recorded)
                in_chart = False
                don = katsu = 0
                continue
    
            # LEVEL 取得
            lm = re.match(r"^\s*level:\s*(\d+)", line, re.I)
            if lm:
                current_level = lm.group(1)
    
            # 譜面開始
            stripped_up = line.strip().upper()
            first_tok = stripped_up.split()[0] if stripped_up else ""
            if first_tok in ("#START", "#START P1", "#START P2"):
                # 新しい譜面開始
                in_chart = True
                don = katsu = 0
                continue
    
            # 譜面終了
            if first_tok == "#END":
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
            filename = os.path.basename(self.current_file)
            base += f" - {filename}"
        else:
            base += " - 新規ファイル"
        
        # 未保存の変更がある場合のみマークを表示
        if self._unsaved_changes:
            base += " ●"
        
        self.root.title(base)

    def open_todo_manager(self):
        """TODO/FIXME管理ウィンドウを開く（改良版）"""
        if hasattr(self, 'todo_window') and self.todo_window and self.todo_window.winfo_exists():
            self.todo_window.lift()
            return
        
        # TODO/FIXMEコメントを検索
        todos = self.find_todos()
        
        self.todo_window = Toplevel(self.root)
        self.todo_window.title(f"TODO/FIXME管理 - {len(todos)}件")
        self.todo_window.geometry("700x500")
        self.todo_window.transient(self.root)
        
        # 上部フレーム：挿入ボタン
        insert_frame = Frame(self.todo_window, pady=10)
        insert_frame.pack(fill="x", padx=10)
        
        Label(insert_frame, text="カーソル位置に挿入:", 
              font=("メイリオ", 10, "bold")).pack(side="left", padx=(0, 10))
        
        # TODO挿入ボタン
        todo_btn = Button(insert_frame, text="TODOを挿入", 
                         command=lambda: self.insert_todo_fixme("TODO"),
                         width=12, font=("メイリオ", 10),
                         bg="#FFD700", fg="black")
        todo_btn.pack(side="left", padx=5)
        
        # FIXME挿入ボタン
        fixme_btn = Button(insert_frame, text="FIXMEを挿入", 
                          command=lambda: self.insert_todo_fixme("FIXME"),
                          width=12, font=("メイリオ", 10),
                          bg="#FF6B6B", fg="white")
        fixme_btn.pack(side="left", padx=5)
        
        # 説明ラベル
        Label(self.todo_window, text="例: ; TODO: ここの密度を下げる  または  // FIXME: ゴーゴー位置修正", 
              font=("メイリオ", 9), fg="gray").pack(pady=(0, 10))
        
        # リストフレーム
        list_frame = Frame(self.todo_window)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.todo_listbox = Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                    font=("MS Gothic", 10), selectmode="single")
        
        if todos:
            for line_num, todo_type, message in todos:
                # タイプに応じて色分け表示
                if todo_type == "TODO":
                    display = f"行{line_num}: [TODO] {message}"
                else:  # FIXME
                    display = f"行{line_num}: [FIXME] {message}"
                self.todo_listbox.insert("end", display)
        else:
            self.todo_listbox.insert("end", "(TODO/FIXMEコメントはありません)")
        
        self.todo_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.todo_listbox.yview)
        
        # TODOデータを保存（ジャンプ用）
        self.current_todos = todos
        
        # ダブルクリックでジャンプ
        self.todo_listbox.bind("<Double-Button-1>", lambda e: self.jump_to_todo())
        
        # 下部ボタンフレーム
        btn_frame = Frame(self.todo_window)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="選択した行にジャンプ", command=self.jump_to_todo, 
               width=18, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="リストを更新", command=self.refresh_todos, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
        Button(btn_frame, text="閉じる", command=self.todo_window.destroy, 
               width=12, font=("メイリオ", 10)).pack(side="left", padx=5)
    
    def insert_todo_fixme(self, todo_type):
        """カーソル位置にTODOまたはFIXMEコメントを挿入（// 記号統一版）"""
        default_text = ""
        if todo_type == "TODO":
            default_text = "ここを修正する"
            prompt = "TODOコメントの内容を入力してください:"
        else:  # FIXME
            default_text = "バグを修正する"
            prompt = "FIXMEコメントの内容を入力してください:"
        
        todo_text = simpledialog.askstring(
            f"{todo_type}挿入",
            prompt,
            initialvalue=default_text,
            parent=self.todo_window if hasattr(self, 'todo_window') and self.todo_window.winfo_exists() else self.root
        )
        
        if todo_text:
            # // 記号に統一
            comment = f"// {todo_type}: {todo_text}\n"
            self.text.insert(tk.INSERT, comment)
            self.text.see(tk.INSERT)
            # 即時にハイライトを適用
            self.root.after(10, self.apply_syntax_highlighting)
            
            # TODOリストを更新
            if hasattr(self, 'todo_window') and self.todo_window.winfo_exists():
                self.refresh_todos()
    
    def find_todos(self):
        """譜面内のTODO/FIXMEコメントを検索"""
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        todos = []
        
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

    def apply_syntax_highlighting(self):
        """構文ハイライトを適用（カーソル位置を保持する版）"""
        # 現在のカーソル位置を正確に保存
        current_cursor = self.text.index(tk.INSERT)
    
        # 既存のタグを削除（音符の色タグも含む）
        for tag in ["header", "comment", "command", "error", "todo", "number",
                    "note_1_3", "note_2_4", "note_5_6_8", "note_7", "note_9", "note_0"]:
            try:
                self.text.tag_remove(tag, "1.0", "end")
            except:
                pass
    
        content = self.text.get("1.0", "end-1c")
        lines = content.split("\n")
    
        # 譜面内かどうかを追跟するフラグ
        in_chart = False
    
        for i, line in enumerate(lines, 1):
            line_start = f"{i}.0"
            line_end = f"{i}.end"
            stripped = line.strip()
            upper = stripped.upper()
    
            # 1. 譜面開始/終了の検出
            if upper in ["#START", "#START P1", "#START P2"]:
                in_chart = True
            elif upper == "#END":
                in_chart = False
    
            # 2. コメント行（// または ;）
            if stripped.startswith("//") or stripped.startswith(";"):
                if "TODO:" in upper or "FIXME:" in upper:
                    self.text.tag_add("todo", line_start, line_end)
                else:
                    self.text.tag_add("comment", line_start, line_end)
                continue
    
            # 3. コマンド行（#で始まる）
            elif stripped.startswith("#"):
                self.text.tag_add("command", line_start, line_end)
                continue
    
            # 4. ヘッダー行（TITLE:, BPM: など）および EXAM1-EXAM4 をヘッダーとして扱う
            elif ":" in line:
                headers = [
                    "TITLE", "SUBTITLE", "BPM", "WAVE", "OFFSET", "DEMOSTART",
                    "GENRE", "SCOREMODE", "SCOREINIT", "SCOREDIFF", "COURSE",
                    "LEVEL", "BALLOON", "SONGVOL", "SEVOL", "MAKER", "STYLE"
                ]
    
                first_word = stripped.split(":")[0].upper()
                # EXAM1..EXAM4 をヘッダー扱いにする
                is_exam_header = re.match(r'^EXAM[1-4]$', first_word) is not None
    
                if first_word in headers or is_exam_header:
                    try:
                        colon_pos = line.index(":")
                    except ValueError:
                        colon_pos = None
    
                    if colon_pos is not None:
                        header_end = f"{i}.{colon_pos}"
                        # ヘッダー名部分に header タグ
                        self.text.tag_add("header", line_start, header_end)
    
                        # コロン以降の生テキスト（スペース含む）
                        post = line[colon_pos + 1:]
    
                        # 数字（整数・小数）を number タグでハイライト（EXAMの条件部分も含む）
                        for m in re.finditer(r'\d+(\.\d+)?', post):
                            start_idx = colon_pos + 1 + m.start()
                            end_idx = colon_pos + 1 + m.end()
                            value_start = f"{i}.{start_idx}"
                            value_end = f"{i}.{end_idx}"
                            try:
                                self.text.tag_add("number", value_start, value_end)
                            except:
                                pass
    
                        # さらに、カンマ区切り全体が数列であれば範囲としてハイライトする既存ロジックと併用
                        value_part = post.strip()
                        is_single_num = re.fullmatch(r"[0-9.\-]+", value_part)
                        is_multi_num = re.fullmatch(r"[0-9.\-]+(,[0-9.\-]+)+", value_part)
                        if value_part and (is_single_num or is_multi_num):
                            idx = post.find(value_part)
                            if idx != -1:
                                vstart = f"{i}.{colon_pos + 1 + idx}"
                                vend = f"{i}.{colon_pos + 1 + idx + len(value_part)}"
                                try:
                                    self.text.tag_add("number", vstart, vend)
                                except:
                                    pass
                    else:
                        # コロンが見つからない場合は行全体をヘッダーとして扱う
                        self.text.tag_add("header", line_start, line_end)
                continue
    
            # 5. 譜面行の音符に色を付ける（譜面内かつ数字を含む行）
            if in_chart and any(c in "0123456789" for c in stripped):
                comment_pos = None
                for sep in ["//", ";"]:
                    if sep in line:
                        comment_pos = line.index(sep)
                        break
    
                line_length = len(line)
                if comment_pos is not None:
                    line_length = comment_pos
    
                for col in range(line_length):
                    char = line[col]
                    char_pos = f"{i}.{col}"
    
                    if char in "13":
                        self.text.tag_add("note_1_3", char_pos, f"{i}.{col+1}")
                    elif char in "24":
                        self.text.tag_add("note_2_4", char_pos, f"{i}.{col+1}")
                    elif char in "568":
                        self.text.tag_add("note_5_6_8", char_pos, f"{i}.{col+1}")
                    elif char == "7":
                        self.text.tag_add("note_7", char_pos, f"{i}.{col+1}")
                    elif char == "9":
                        self.text.tag_add("note_9", char_pos, f"{i}.{col+1}")
                    elif char == "0":
                        self.text.tag_add("note_0", char_pos, f"{i}.{col+1}")
    
            # 6. 行内コメントの処理（譜面行の後ろのコメント）
            if "//" in line or ";" in line:
                for sep in ["//", ";"]:
                    if sep in line:
                        comment_start_pos = line.index(sep)
                        comment_start = f"{i}.{comment_start_pos}"
                        comment_part = line[comment_start_pos:].upper()
                        if "TODO:" in comment_part or "FIXME:" in comment_part:
                            self.text.tag_add("todo", comment_start, line_end)
                        else:
                            self.text.tag_add("comment", comment_start, line_end)
                        break
    
        # カーソル位置に戻す（確実に）
        if current_cursor:
            try:
                self.text.mark_set(tk.INSERT, current_cursor)
                self.text.see(tk.INSERT)
            except Exception:
                pass

    def insert_palette_char(self, ch):
        """メインパレットから文字を挿入（構文ハイライト等を更新）"""
        try:
            self.text.insert(tk.INSERT, ch)
            # 挿入後に構文ハイライト等を更新
            self.root.after(10, self.apply_syntax_highlighting)
            self.root.after_idle(self.update_all)
            # 変更検出
            self._check_for_changes()
        except Exception as e:
            print(f"[Palette] insert error: {e}")

    def toggle_palette_visibility(self, event=None):
        """パレットの表示/非表示を切り替える"""
        self.palette_visible = not self.palette_visible
        
        if hasattr(self, 'palette_frame'):
            if self.palette_visible:
                # パレットを表示
                self.palette_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.statusbar)
                # ダークモードの色を適用
                self._update_main_palette_colors()
            else:
                # パレットを非表示
                self.palette_frame.pack_forget()
        
        # メニューのチェック状態を更新
        if hasattr(self, 'palette_visible_var'):
            self.palette_visible_var.set(self.palette_visible)
        
        # 設定を保存
        self.save_config()
        
        # レイアウトを強制的に更新してから行番号を再描画
        self.root.update_idletasks()
        
        # 行番号とその他のUI要素を更新
        # 少し遅延させることで、レイアウトの変更が完全に反映されてから更新
        self.root.after(10, self.update_linenumbers)
        self.root.after(15, self.update_all)

    def _update_main_palette_colors(self):
        """
        メインウィンドウに常駐している palette_frame の色を
        現在の self.dark_mode に合わせて更新します。
        （palette_frame とその子ウィジェットを深さ優先で走査して色を設定）
        """
        try:
            if not hasattr(self, 'palette_frame') or not self.palette_frame:
                return
    
            # 配色定義（_create_widgets で使っているものと一致させる）
            if self.dark_mode:
                p_bg = "#252526"
                p_btn_bg = "#2d2d2d"
                p_fg = "#e6e6e6"
            else:
                p_bg = "#f3f3f3"
                p_btn_bg = "#ffffff"
                p_fg = "black"
    
            # フレーム本体
            try:
                self.palette_frame.config(bg=p_bg)
            except Exception:
                pass
    
            # 子ウィジェットを再帰的に更新
            def _apply(widget):
                try:
                    # フレーム類
                    if isinstance(widget, (tk.Frame, tk.LabelFrame, tk.Canvas)):
                        widget.config(bg=p_bg)
                    # ラベル・チェックボックス
                    if isinstance(widget, (tk.Label, tk.Checkbutton)):
                        try:
                            widget.config(bg=p_bg, fg=p_fg)
                        except:
                            pass
                    # Button（tk.Button）に対しては背景を設定
                    if isinstance(widget, tk.Button):
                        try:
                            widget.config(bg=p_btn_bg, fg=p_fg, activebackground=p_btn_bg)
                        except:
                            pass
                    # Entry / Text / Listbox などは背景を変えない（既に toggle_dark_mode が担当）
                except Exception:
                    pass
    
                # 子要素へ再帰
                try:
                    for ch in widget.winfo_children():
                        _apply(ch)
                except Exception:
                    pass
    
            _apply(self.palette_frame)
    
        except Exception as e:
            # 万が一のエラーは無視（アプリを止めない）
            print(f"[DEBUG] _update_main_palette_colors error: {e}")
                 
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
        self.save_config()
    
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
            
            # 変更状態をリセット
            self._unsaved_changes = False
            self.current_file = path
            self.current_encoding = encoding
            
            # ハッシュを初期化
            import hashlib
            self._text_content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
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
                
                # 変更状態をリセット
                self._unsaved_changes = False
                
                # ハッシュを更新
                import hashlib
                self._text_content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                
                self.update_title()
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
    
        if not file_path:
            return
    
        # 保存前に既存ファイルの有無を判定（これが is_new_file）
        is_new_file = not os.path.exists(file_path)
    
        # 更新 last_folder と設定保存（ユーザーの利便性のため）
        self.last_folder = os.path.dirname(file_path)
        self.save_config()
    
        try:
            content = self.text.get("1.0", tk.END)
    
            # ★ 常にバックアップフォルダを作成しておく（新規保存時も含む）
            backup_dir = os.path.join(os.path.dirname(file_path), ".backup")
            os.makedirs(backup_dir, exist_ok=True)
    
            # ★ タイムスタンプ付き自動バックアップ（既存ファイルがある場合のみ）
            if os.path.exists(file_path):
                try:
                    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    backup_name = f"{ts}_{os.path.basename(file_path)}"
                    backup_path = os.path.join(backup_dir, backup_name)
                    shutil.copy2(file_path, backup_path)
                    # 従来の ~ バックアップも残す（任意）
                    try:
                        shutil.copy2(file_path, file_path + "~")
                    except Exception:
                        # ~ バックアップは失敗しても致命的ではない
                        pass
                except Exception as backup_error:
                    # バックアップ作成失敗は警告ログに留め、保存処理は継続
                    print(f"[DEBUG] バックアップ作成失敗: {backup_error}")
    
            # メインの保存処理（読み込んだエンコーディングで保存）
            with open(file_path, 'w', encoding=self.current_encoding, newline='\n') as f:
                f.write(content.rstrip() + "\n")
    
            # 保存成功後の状態更新
            prev_current_file = self.current_file
            self.current_file = file_path
            self.text.edit_modified(False)
    
            # 変更状態をリセット
            self._unsaved_changes = False
    
            # ハッシュを更新（UTF-8でハッシュ化）
            import hashlib
            self._text_content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    
            # UI更新
            self.update_all()
    
            # 成功メッセージ（is_new_file の判定は保存前に評価済み）
            filename = os.path.basename(file_path)
            if is_new_file:
                message_text = f"新規保存しました！\nファイル名: {filename}"
            else:
                message_text = f"名前を付けて保存しました！\nファイル名: {filename}"
                if os.path.exists(file_path):
                    message_text += "\n（既存ファイルは自動バックアップされました）"
    
            messagebox.showinfo("保存完了", message_text)
    
            # 最近ファイル追加（重複排除・先頭へ）
            if file_path in self.recent_files:
                self.recent_files.remove(file_path)
            self.recent_files.insert(0, file_path)
            self.recent_files = self.recent_files[:self.MAX_RECENT]
            self.update_recent_menu()
            self.save_config()
    
        except Exception as e:
            messagebox.showerror("保存エラー", f"保存に失敗しました…\n{e}")

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
        """プロフェッショナルな検索・置換ウィンドウを開く"""
        # 既存のウィンドウがあれば最前面に
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
            self.search_window = None
        
        # 新規ウィンドウ作成
        self.search_window = Toplevel(self.root)
        self.search_window.title("検索と置換")
        self.search_window.geometry("680x520")
        self.search_window.resizable(True, True)
        self.search_window.transient(self.root)
        self.search_window.protocol("WM_DELETE_WINDOW", self.close_search)
        
        # 全体レイアウト - タブ形式
        notebook = ttk.Notebook(self.search_window)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # タブ1: 検索
        search_tab = ttk.Frame(notebook)
        notebook.add(search_tab, text="検索")
        
        # タブ2: 置換
        replace_tab = ttk.Frame(notebook)
        notebook.add(replace_tab, text="置換")
        
        # ========== 検索タブの内容 ==========
        search_frame = ttk.LabelFrame(search_tab, text="検索オプション", padding=15)
        search_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 検索文字列入力
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(search_input_frame, text="検索文字列:", font=("メイリオ", 10)).pack(side="left", padx=(0, 10))
        self.search_entry = ttk.Entry(search_input_frame, font=("メイリオ", 11), width=40)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.focus_set()
        
        # オプションフレーム
        options_frame = ttk.Frame(search_frame)
        options_frame.pack(fill="x", pady=(0, 20))
        
        # 大文字小文字の区別
        self.case_sensitive_var = tk.BooleanVar(value=False)
        case_check = ttk.Checkbutton(options_frame, text="大文字小文字を区別", 
                                     variable=self.case_sensitive_var)
        case_check.pack(side="left", padx=(0, 20))
        
        # 単語単位で検索
        self.whole_word_var = tk.BooleanVar(value=False)
        word_check = ttk.Checkbutton(options_frame, text="単語単位で検索", 
                                    variable=self.whole_word_var)
        word_check.pack(side="left", padx=(0, 20))
        
        # 正規表現
        self.regex_var = tk.BooleanVar(value=False)
        regex_check = ttk.Checkbutton(options_frame, text="正規表現を使用", 
                                      variable=self.regex_var)
        regex_check.pack(side="left")
        
        # 結果表示エリア
        results_frame = ttk.LabelFrame(search_frame, text="検索結果", padding=10)
        results_frame.pack(fill="both", expand=True)
        
        # 結果ヘッダー
        header_frame = ttk.Frame(results_frame)
        header_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(header_frame, text="行", width=5, font=("メイリオ", 9, "bold")).pack(side="left", padx=2)
        ttk.Label(header_frame, text="内容", font=("メイリオ", 9, "bold")).pack(side="left", padx=2)
        
        # 結果リスト（ツリービュー）
        columns = ("line", "content")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=8)
        
        self.results_tree.heading("line", text="行", anchor="w")
        self.results_tree.heading("content", text="内容", anchor="w")
        
        self.results_tree.column("line", width=80, minwidth=60)
        self.results_tree.column("content", width=400, minwidth=200)
        
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # ダブルクリックでジャンプ
        self.results_tree.bind("<Double-1>", lambda e: self.jump_to_search_result())
        
        # 検索ボタンフレーム
        search_btn_frame = ttk.Frame(search_frame)
        search_btn_frame.pack(fill="x", pady=(15, 0))
        
        ttk.Button(search_btn_frame, text="全て検索", width=12,
                   command=self.find_all).pack(side="left", padx=5)
        ttk.Button(search_btn_frame, text="次を検索", width=12,
                   command=self.find_next).pack(side="left", padx=5)
        ttk.Button(search_btn_frame, text="前を検索", width=12,
                   command=self.find_prev).pack(side="left", padx=5)
        ttk.Button(search_btn_frame, text="クリア", width=12,
                   command=self.clear_search_results).pack(side="right", padx=5)
        
        # ========== 置換タブの内容 ==========
        replace_frame = ttk.LabelFrame(replace_tab, text="置換オプション", padding=15)
        replace_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 検索文字列入力
        replace_search_frame = ttk.Frame(replace_frame)
        replace_search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(replace_search_frame, text="検索文字列:", 
                 font=("メイリオ", 10)).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.replace_search_entry = ttk.Entry(replace_search_frame, font=("メイリオ", 11), width=30)
        self.replace_search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 20))
        
        # 置換文字列入力
        ttk.Label(replace_search_frame, text="置換文字列:", 
                 font=("メイリオ", 10)).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        self.replace_with_entry = ttk.Entry(replace_search_frame, font=("メイリオ", 11), width=30)
        self.replace_with_entry.grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=(10, 0))
        
        replace_search_frame.columnconfigure(1, weight=1)
        
        # 置換オプション
        replace_options_frame = ttk.Frame(replace_frame)
        replace_options_frame.pack(fill="x", pady=(0, 20))
        
        self.replace_case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(replace_options_frame, text="大文字小文字を区別", 
                       variable=self.replace_case_var).pack(side="left", padx=(0, 20))
        
        self.replace_regex_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(replace_options_frame, text="正規表現を使用", 
                       variable=self.replace_regex_var).pack(side="left")
        
        # 置換ボタンフレーム
        replace_btn_frame = ttk.Frame(replace_frame)
        replace_btn_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(replace_btn_frame, text="置換して次へ", width=14,
                   command=self.replace_next).pack(side="left", padx=5)
        ttk.Button(replace_btn_frame, text="現在を置換", width=12,
                   command=self.replace_current).pack(side="left", padx=5)
        ttk.Button(replace_btn_frame, text="すべて置換", width=12,
                   command=self.replace_all).pack(side="left", padx=5)
        
        # 統計情報ラベル
        self.replace_stats_label = ttk.Label(replace_frame, text="", font=("メイリオ", 9))
        self.replace_stats_label.pack(pady=(15, 0))
        
        # キーバインディング
        self.search_entry.bind("<Return>", lambda e: self.find_next())
        self.search_entry.bind("<Shift-Return>", lambda e: self.find_prev())
        self.replace_search_entry.bind("<Return>", lambda e: self.find_next())
        
        self.root.bind_all("<F3>", lambda e: self.find_next() if self.search_window else None)
        self.root.bind_all("<Shift-F3>", lambda e: self.find_prev() if self.search_window else None)
        self.root.bind_all("<Control-h>", lambda e: self.open_search() if not hasattr(self, 'search_window') or not self.search_window else None)
        
        # 変数初期化
        self.search_positions = []
        self.current_match = -1
        self.search_results = []
        
        # 最近の検索履歴
        self.search_history = []
        self.replace_history = []
    
    def find_all(self):
        """すべての一致を検索し、結果を表示"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        # ツリービューをクリア
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # ハイライトをクリア
        self.clear_search_highlight()
        
        content = self.text.get("1.0", tk.END)
        lines = content.splitlines()
        
        self.search_positions = []
        self.search_results = []
        
        # 検索オプションを取得
        case_sensitive = self.case_sensitive_var.get()
        whole_word = self.whole_word_var.get()
        use_regex = self.regex_var.get()
        
        # 正規表現のコンパイル
        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(query, flags)
            except re.error as e:
                messagebox.showerror("正規表現エラー", f"正規表現が無効です:\n{e}", 
                                   parent=self.search_window)
                return
        else:
            # 通常の検索用パターン
            if whole_word:
                pattern = re.compile(r'\b' + re.escape(query) + r'\b', 
                                   0 if case_sensitive else re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(query), 
                                   0 if case_sensitive else re.IGNORECASE)
        
        # 行ごとに検索
        for line_num, line_text in enumerate(lines, 1):
            if use_regex or whole_word:
                matches = list(pattern.finditer(line_text))
            else:
                # 単純な文字列検索
                search_text = line_text if case_sensitive else line_text.lower()
                query_lower = query if case_sensitive else query.lower()
                matches = []
                start = 0
                while True:
                    pos = search_text.find(query_lower, start)
                    if pos == -1:
                        break

                    matches.append((pos, pos + len(query_lower), pos, pos + len(query)))
                    start = pos + 1
            
            for match in matches:
                # マッチの種類によって処理を分ける
                if use_regex or whole_word:
                    # re.Matchオブジェクトの場合
                    start_pos = match.start()
                    end_pos = match.end()
                else:
                    # タプルの場合（単純な文字列検索）
                    # タプルの内容: (pos_in_search_text, end_in_search_text, pos_in_original, end_in_original)
                    _, _, start_pos, end_pos = match
                
                # 位置情報を保存
                start_index = f"{line_num}.{start_pos}"
                end_index = f"{line_num}.{end_pos}"
                self.search_positions.append((start_index, end_index))
                
                # ハイライトを追加
                self.text.tag_add("search", start_index, end_index)
                
                # 結果をツリービューに追加
                line_content = line_text[:80] + "..." if len(line_text) > 80 else line_text
                # マッチ部分を強調表示
                highlighted = (line_content[:start_pos] + 
                             "【" + line_content[start_pos:end_pos] + "】" + 
                             line_content[end_pos:])
                
                self.results_tree.insert("", "end", values=(line_num, highlighted))
                self.search_results.append((line_num, line_content, start_pos, end_pos))
        
        # 結果数を表示
        count = len(self.search_positions)
        if count == 0:
            self.results_tree.insert("", "end", values=("", "一致する結果が見つかりませんでした"))
        else:
            # 選択されたタブのタイトルを更新
            notebook = self.search_window.winfo_children()[0]
            tab_text = notebook.tab(0, "text")
            notebook.tab(0, text=f"検索 ({count}件)")
        
        # 最初の結果を選択
        if self.search_positions:
            self.current_match = 0
            self.select_search_result(0)
    
    def select_search_result(self, index):
        """検索結果を選択してハイライト"""
        if 0 <= index < len(self.search_positions):
            self.current_match = index
            start_pos, end_pos = self.search_positions[index]
            
            # テキストエリアで選択
            self.text.tag_remove(tk.SEL, "1.0", tk.END)
            self.text.tag_add(tk.SEL, start_pos, end_pos)
            self.text.mark_set(tk.INSERT, end_pos)
            self.text.see(start_pos)
            
            # ツリービューで選択
            self.results_tree.selection_set(self.results_tree.get_children()[index])
            self.results_tree.see(self.results_tree.get_children()[index])
    
    def jump_to_search_result(self):
        """選択された検索結果にジャンプ"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        # 選択されたアイテムのインデックスを取得
        items = self.results_tree.get_children()
        index = items.index(selection[0])
        
        if 0 <= index < len(self.search_positions):
            self.select_search_result(index)
    
    def clear_search_results(self):
        """検索結果をクリア"""
        # ハイライトをクリア
        self.clear_search_highlight()
        
        # ツリービューをクリア
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # 変数をリセット
        self.search_positions = []
        self.search_results = []
        self.current_match = -1
        
        # タブタイトルをリセット
        notebook = self.search_window.winfo_children()[0]
        notebook.tab(0, text="検索")

    def clear_search_highlight(self):
        """検索ハイライトをクリア"""
        if hasattr(self, 'text'):
            # searchタグを削除
            self.text.tag_remove("search", "1.0", tk.END)
            self.text.tag_remove("search_current", "1.0", tk.END)
            self.text.tag_remove(tk.SEL, "1.0", tk.END)
            
            # 置換ハイライトもクリア（もしあれば）
            if hasattr(self, 'text') and self.text:
                try:
                    self.text.tag_remove("replace", "1.0", tk.END)
                except:
                    pass
            
    def find_next(self):
        """次の一致を検索"""
        if not self.search_positions:
            self.find_all()
            return
        
        if self.current_match >= len(self.search_positions) - 1:
            self.current_match = 0  # ループ
        else:
            self.current_match += 1
        
        self.select_search_result(self.current_match)
    
    def find_prev(self):
        """前の一致を検索"""
        if not self.search_positions:
            self.find_all()
            return
        
        if self.current_match <= 0:
            self.current_match = len(self.search_positions) - 1  # ループ
        else:
            self.current_match -= 1
        
        self.select_search_result(self.current_match)
    
    # ========== 置換機能 ==========
    def replace_current(self):
        """現在選択されているテキストを置換"""
        if not hasattr(self, 'replace_search_entry'):
            return
        
        search_text = self.replace_search_entry.get().strip()
        replace_text = self.replace_with_entry.get()
        
        if not search_text:
            messagebox.showwarning("入力エラー", "検索文字列を入力してください", 
                                 parent=self.search_window)
            return
        
        # 現在選択されているテキストを取得
        try:
            sel_start = self.text.index(tk.SEL_FIRST)
            sel_end = self.text.index(tk.SEL_LAST)
            selected = self.text.get(sel_start, sel_end)
        except tk.TclError:
            # 何も選択されていない
            self.find_next()
            return
        
        # 検索条件に一致するか確認
        case_sensitive = self.replace_case_var.get()
        use_regex = self.replace_regex_var.get()
        
        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(search_text, flags)
                match = pattern.fullmatch(selected)
            except re.error as e:
                messagebox.showerror("正規表現エラー", f"正規表現が無効です:\n{e}", 
                                   parent=self.search_window)
                return
        else:
            if case_sensitive:
                match = selected == search_text
            else:
                match = selected.lower() == search_text.lower()
        
        if match:
            # 置換実行
            if use_regex:
                replaced = pattern.sub(replace_text, selected)
            else:
                replaced = replace_text
            
            self.text.delete(sel_start, sel_end)
            self.text.insert(sel_start, replaced)
            
            # 置換後に次の一致を検索
            self.find_next()
            
            # 統計を更新
            self.update_replace_stats(1)
    
    def replace_next(self):
        """次の一致を検索して置換"""
        # まず次を検索
        self.find_next()
        
        # 現在の一致を置換
        self.replace_current()
    
    def replace_all(self):
        """すべての一致を置換"""
        search_text = self.replace_search_entry.get().strip()
        replace_text = self.replace_with_entry.get()
        
        if not search_text:
            messagebox.showwarning("入力エラー", "検索文字列を入力してください", 
                                 parent=self.search_window)
            return
        
        # 確認ダイアログ
        if not messagebox.askyesno("すべて置換", 
                                  "すべての一致を置換しますか？\nこの操作は元に戻せません。",
                                  parent=self.search_window):
            return
        
        content = self.text.get("1.0", tk.END)
        
        # 検索オプション
        case_sensitive = self.replace_case_var.get()
        use_regex = self.replace_regex_var.get()
        
        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(search_text, flags)
                new_content = pattern.sub(replace_text, content)
            except re.error as e:
                messagebox.showerror("正規表現エラー", f"正規表現が無効です:\n{e}", 
                                   parent=self.search_window)
                return
        else:
            if case_sensitive:
                new_content = content.replace(search_text, replace_text)
            else:
                # 大文字小文字を区別しない置換
                pattern = re.compile(re.escape(search_text), re.IGNORECASE)
                new_content = pattern.sub(lambda m: replace_text, content)
        
        # 置換を適用
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", new_content.rstrip())
        
        # 統計を計算
        count = len(list(re.finditer(re.escape(search_text) if not use_regex else search_text, 
                                    content, 
                                    0 if case_sensitive else re.IGNORECASE)))
        
        # 統計を更新
        self.update_replace_stats(count)
        
        # 検索結果をクリア（内容が変わったため）
        self.clear_search_results()
    
    def update_replace_stats(self, count):
        """置換統計を更新"""
        if count > 0:
            self.replace_stats_label.config(
                text=f"{count} 箇所を置換しました",
                foreground="green"
            )
        else:
            self.replace_stats_label.config(
                text="置換対象が見つかりませんでした",
                foreground="red"
            )
        
        # 5秒後にメッセージを消す
        if hasattr(self, 'search_window') and self.search_window:
            self.search_window.after(5000, 
                                   lambda: self.replace_stats_label.config(text=""))
    
    def close_search(self):
        """検索ウィンドウを閉じる"""
        if hasattr(self, 'search_window') and self.search_window:
            # ハイライトをクリア
            self.clear_search_highlight()
            
            # キーバインディング解除
            try:
                self.root.unbind_all("<F3>")
                self.root.unbind_all("<Shift-F3>")
                self.root.unbind_all("<Control-h>")
            except:
                pass
            
            # ウィンドウを閉じる
            self.search_window.destroy()
            self.search_window = None
            
            # テキストエリアにフォーカスを戻す
            self.text.focus_set()
        
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

    def check_errors_simple(self):
        """簡易版エラーチェック（致命的なエラーのみ）"""
        content = self.text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("エラーチェック", "譜面が空です。")
            return
    
        lines = content.splitlines()
        errors = []
    
        # 1. #START/#END の対応チェック（基本）
        start_count = 0
        end_count = 0
        in_chart = False
    
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            upper = stripped.upper()
    
            # 先頭トークンで厳密判定する（部分一致を避ける）
            first_tok = upper.split()[0] if upper else ""
    
            if first_tok in ("#START", "#START P1", "#START P2"):
                if in_chart:
                    errors.append((i, "エラー", "#START が閉じられていません（二重開始）"))
                start_count += 1
                in_chart = True
            elif first_tok == "#END":
                if not in_chart:
                    errors.append((i, "エラー", "#END に対応する #START がありません"))
                end_count += 1
                in_chart = False
    
        # START/ENDの数の一致チェック
        if start_count != end_count:
            errors.append((0, "エラー", f"#START({start_count}個) と #END({end_count}個) の数が一致しません"))
    
        # 2. 必須ヘッダーのチェック
        has_course = False
        has_level = False
        has_bpm = False
        has_wave = False
    
        for i, line in enumerate(lines, 1):
            stripped = line.strip().upper()
    
            if stripped.startswith("COURSE:"):
                has_course = True
            elif stripped.startswith("LEVEL:"):
                has_level = True
            elif stripped.startswith("BPM:"):
                has_bpm = True
            elif stripped.startswith("WAVE:"):
                has_wave = True
    
        if not has_course:
            errors.append((0, "警告", "COURSE: が定義されていません"))
        if not has_level:
            errors.append((0, "警告", "LEVEL: が定義されていません"))
        if not has_bpm:
            errors.append((0, "警告", "BPM: が定義されていません"))
        if not has_wave:
            errors.append((0, "警告", "WAVE: が定義されていません"))
    
        # 3. 全角数字チェック（譜面行のみ）
        in_chart = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            upper = stripped.upper()
            first_tok = upper.split()[0] if upper else ""
    
            if first_tok in ("#START", "#START P1", "#START P2"):
                in_chart = True
            elif first_tok == "#END":
                in_chart = False
    
            if in_chart and not stripped.startswith("#") and not stripped.startswith("//") and not stripped.startswith(";"):
                # 全角数字チェック
                if any(c in "０１２３４５６７８９" for c in stripped):
                    errors.append((i, "エラー", "全角数字が含まれています（半角に修正してください）"))
    
        # 4. カンマの連続チェック（空小節）
        for i, line in enumerate(lines, 1):
            if ",," in line:
                errors.append((i, "警告", "カンマが連続しています（空の小節）"))
    
        # 結果表示
        if not errors:
            messagebox.showinfo("エラーチェック", "致命的なエラーは見つかりませんでした！\n譜面は基本的に問題ありません。")
            return
    
        # エラーウィンドウを表示（簡易版）
        self.show_simple_error_window(errors)
    
    def show_simple_error_window(self, errors):
        """簡易版エラー表示ウィンドウ"""
        win = Toplevel(self.root)
        win.title(f"エラーチェック結果 - {len(errors)}件")
        win.geometry("600x400")
        win.transient(self.root)
        
        # 重要度でソート（エラー→警告）
        errors.sort(key=lambda x: 0 if x[1] == "エラー" else 1)
        
        Label(win, text=f"検出された問題: {len(errors)}件", 
              font=("メイリオ", 12, "bold")).pack(pady=10)
        
        # 統計表示
        error_count = sum(1 for e in errors if e[1] == "エラー")
        warning_count = len(errors) - error_count
        
        stats_frame = Frame(win)
        stats_frame.pack(pady=5)
        
        Label(stats_frame, text=f"エラー: {error_count}件", 
              fg="red", font=("メイリオ", 10, "bold")).pack(side="left", padx=10)
        Label(stats_frame, text=f"警告: {warning_count}件", 
              fg="orange", font=("メイリオ", 10)).pack(side="left", padx=10)
        
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
            
            # 色分け挿入（エラーは赤、警告は黒）
            listbox.insert("end", display)
            if error_type == "エラー":
                listbox.itemconfig("end", fg="red")
        
        listbox.pack(fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        def jump_to_error():
            sel = listbox.curselection()
            if not sel:
                return
            index = sel[0]
            line_num, error_type, message = errors[index]
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

    def insert_syntax(self, syntax):
        """構文を挿入（ハイライト更新付き）"""
        self.text.insert(tk.INSERT, syntax)
        self.text.see(tk.INSERT)
        # 即時にハイライトを適用
        self.root.after(10, self.apply_syntax_highlighting)
        self.root.after_idle(self.update_all)

    def insert_with_input(self, prefix, prompt, default=""):
        """入力付き挿入（ハイライト更新付き）"""
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

    def insert_style_only(self, style):
        self.insert_syntax(f"STYLE:{style}\n")
        
    def insert_wave(self):
        """WAVE:を挿入（拡張子.oggを自動で追加）"""
        wave_file = simpledialog.askstring(
            "WAVE入力", 
            "音源ファイル名を入力（例: song）\n.ogg以外の拡張子を使用する場合は\n拡張子も含めて入力してください",
            initialvalue="song"
        )
        
        if wave_file is not None:
            # 拡張子がなければ.oggを追加
            wave_file = wave_file.strip()
            if wave_file:  # 空文字でないことを確認
                # 既に拡張子があるかチェック
                if not wave_file.lower().endswith(('.ogg', '.mp3', '.wav', '.flac', '.m4a', '.oga')):
                    wave_file += '.ogg'
                
                self.insert_syntax(f"WAVE:{wave_file}\n")

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
                                   values=["外伝","黄", "青", "赤", "銀", "金"],
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
        
        # 保存しておく（他メソッドからも更新できるように属性にセット）
        self.cond_canvas = cond_canvas
        self.cond_inner_frame = cond_inner_frame

        # スクロール領域を更新するハンドラ
        def update_cond_scrollregion(event=None):
            try:
                # bbox が None になる可能性があるので例外吸収
                bbox = cond_canvas.bbox("all")
                if bbox:
                    cond_canvas.configure(scrollregion=bbox)
            except Exception:
                pass

        cond_inner_frame.bind("<Configure>", update_cond_scrollregion)

        # マウスホイール処理 - オーバースクロールを防止
        def _cond_on_mousewheel(event):
            try:
                # Windows: event.delta は 120 の倍数。 macOS 等は異なるがここでは一般的処理のみ実装。
                delta = int(event.delta)
                # 現在の表示範囲 (start, end) をチェック
                start, end = cond_canvas.yview()
                # 上へスクロール（ホイールを前に転がす等、event.delta>0）
                if delta > 0:
                    if start <= 0.0:
                        return "break"  # これ以上上へはスクロールさせない
                else:  # 下へスクロール
                    if end >= 1.0:
                        return "break"  # これ以上下へはスクロールさせない

                # 実際のスクロール
                cond_canvas.yview_scroll(int(-1 * (delta / 120)), "units")
                return "break"
            except Exception:
                # フォールバック: 通常スクロール
                try:
                    cond_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
                except:
                    return None

        # マウスが canvas 内に入った時だけグローバルにホイールをバインド（子ウィジェット上でもまとめて拾えるようにする）
        def _bind_cond_mousewheel(_event=None):
            try:
                # bind_all を使うが、Enter/Leave で切り替えることで影響範囲を限定する
                cond_canvas.bind_all("<MouseWheel>", _cond_on_mousewheel)
            except:
                pass

        def _unbind_cond_mousewheel(_event=None):
            try:
                cond_canvas.unbind_all("<MouseWheel>")
            except:
                pass

        cond_canvas.bind("<Enter>", _bind_cond_mousewheel)
        cond_canvas.bind("<Leave>", _unbind_cond_mousewheel)
        cond_inner_frame.bind("<Enter>", _bind_cond_mousewheel)
        cond_inner_frame.bind("<Leave>", _unbind_cond_mousewheel)

        # ウィンドウが閉じられる時にイベントをアンバインド
        def cleanup_mousewheel():
            try:
                cond_canvas.unbind_all("<MouseWheel>")
                cond_canvas.unbind("<Enter>")
                cond_canvas.unbind("<Leave>")
                cond_inner_frame.unbind("<Enter>")
                cond_inner_frame.unbind("<Leave>")
            except:
                pass
        
        # === 共通合格条件セクション ===
        # 共通条件を中央に配置するための外側コンテナ
        common_outer_frame = Frame(cond_inner_frame, bg="#f0f0f0")
        common_outer_frame.pack(fill="both", expand=True, pady=20)  # 上下に余白
        
        # 垂直方向の中央配置用フレーム
        vertical_center_frame = Frame(common_outer_frame, bg="#f0f0f0")
        vertical_center_frame.pack(fill="both", expand=True)
        
        # 水平方向の中央配置用フレーム
        horizontal_center_frame = Frame(vertical_center_frame, bg="#f0f0f0")
        horizontal_center_frame.pack(expand=True)
        
        # 共通条件フレーム本体
        common_frame = LabelFrame(horizontal_center_frame, 
                                 text="共通合格条件 (全ての曲に適用)",
                                 font=("メイリオ", 11, "bold"),
                                 padx=20,
                                 pady=15,
                                 bg="#f8f8f8",
                                 relief="groove")
        common_frame.pack()
        
        # 説明ラベル（中央揃え）
        Label(common_frame, 
              text="以下の条件は全ての曲に共通で適用されます。",
              font=("メイリオ", 9),
              fg="#666666",
              bg="#f8f8f8").pack(pady=(0, 2))
        
        Label(common_frame, 
              text="特定の曲だけ異なる条件を設定したい場合は「曲ごとに設定」にチェックを入れてください。",
              font=("メイリオ", 9),
              fg="#666666",
              bg="#f8f8f8").pack(pady=(0, 15))
        
        # 共通条件の各項目の幅設定
        column_widths = {
            'label': 6,    # 項目ラベル
            'type': 14,    # 条件タイプ
            'comp': 8,     # 比較方法
            'normal': 8,   # 通常条件
            'gold': 8,     # 金条件
            'checkbox': 12 # チェックボックス
        }
        
        # 共通条件を配置するためのメインフレーム
        common_items_frame = Frame(common_frame, bg="#f8f8f8")
        common_items_frame.pack()
        
        self.common_type_combos = {}
        self.common_comp_combos = {}
        self.common_normal_entries = {}
        self.common_gold_entries = {}
        self.per_song_vars = {}
        self.per_song_frames = {}
        self.per_song_widgets = {}
        self.per_song_order = []
        
        for idx, (typ, comp, n, g) in enumerate(self.DAN_DEFAULTS):
            # EXAM1~4を「条件1~4」に変更
            condition_number = idx + 1
            display_item = f"条件{condition_number}"
            internal_item = self.DAN_ITEMS[idx]  # 内部識別子はEXAM1~4のまま
            
            # 各条件のフレーム
            item_frame = Frame(common_items_frame, bg="#f8f8f8")
            item_frame.pack(fill="x", pady=5, padx=10)
            
            # 項目ラベル
            label_frame = Frame(item_frame, bg="#f8f8f8")
            label_frame.pack(side="left", padx=(0, 10))
            Label(label_frame, text=f"{display_item}:",
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
            checkbox_frame.pack(side="right", padx=(20, 0))
            
            # 曲ごと設定チェックボックス
            var = tk.IntVar(value=0)
            cb = Checkbutton(checkbox_frame, 
                             text="曲ごとに設定",
                             variable=var,
                             command=lambda i=internal_item: self.toggle_per_song(i),
                             font=("メイリオ", 9),
                             bg="#f8f8f8")
            cb.pack()
            
            # ウィジェットを保存
            self.common_type_combos[internal_item] = tc
            self.common_comp_combos[internal_item] = cc
            self.common_normal_entries[internal_item] = ne
            self.common_gold_entries[internal_item] = ge
            self.per_song_vars[internal_item] = var
            
            # 個別設定フレーム（初期非表示） - cond_inner_frame内に配置
            pf = Frame(cond_inner_frame, padx=10, pady=10, bg="#f0f8ff", relief="ridge", bd=1)
            pf.pack_forget()
            self.per_song_frames[internal_item] = pf
            self.per_song_widgets[internal_item] = []
            
            self.update_common_state(internal_item)
        
        # 余白を追加してより中央に見えるように
        spacer_frame = Frame(cond_inner_frame, height=20, bg="#f0f0f0")
        spacer_frame.pack(fill="x")
        
       # スクロール領域更新
        cond_inner_frame.bind("<Configure>", 
                             lambda e: cond_canvas.configure(scrollregion=cond_canvas.bbox("all")))
        
        # マウスホイールでスクロール可能にする
        def on_mousewheel(event):
            cond_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Canvasとその子要素にマウスホイールイベントをバインド
        cond_canvas.bind_all("<MouseWheel>", on_mousewheel)
        cond_inner_frame.bind_all("<MouseWheel>", on_mousewheel)
        
        # ウィンドウが閉じられる時にイベントをアンバインド
        def cleanup_mousewheel():
            try:
                cond_canvas.unbind_all("<MouseWheel>")
                cond_inner_frame.unbind_all("<MouseWheel>")
            except:
                pass
        
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
        self.dan_window.minsize(1040, 700)
        self.dan_window.maxsize(1040, 700)
        
        # 初回表示
        self.update_song_settings()

    def on_course_changed(self, song_idx, combobox):
        """
        曲のCOURSEが変更されたときの共通処理（重複定義を統合）
        - 選択値を一時保存
        - レベル等をファイルから再取得
        - UI を更新
        """
        selected = combobox.get()
        self.song_courses_temp[song_idx] = selected
    
        # 現在 UI や内部で保持している値を退避（手動入力を維持したい場合に復元）
        current_genre = self.song_genres.get(song_idx, None)
        current_scoreinit = self.song_scoreinit.get(song_idx, "")
        current_scorediff = self.song_scorediff.get(song_idx, "")
    
        # コース変更に伴うレベルやファイル由来の情報を再取得
        self.update_level_and_genre(song_idx)
    
        # 既にユーザが手動で設定していた値があれば優先して保持
        if current_genre is not None:
            self.song_genres[song_idx] = current_genre
        if current_scoreinit:
            self.song_scoreinit[song_idx] = current_scoreinit
        if current_scorediff:
            self.song_scorediff[song_idx] = current_scorediff
    
        # UI を更新して反映
        self.update_song_settings()
    
    def update_level_and_genre(self, song_idx):
        if song_idx >= len(self.song_paths):
            return
        path = self.song_paths[song_idx]
        selected_jp = self.song_courses_temp.get(song_idx, "鬼")
        course_map = {"かんたん":"Easy","ふつう":"Normal","むずかしい":"Hard","鬼":"Oni","裏鬼":"Edit"}
        target = course_map.get(selected_jp, "Oni")
        level = "?"
        
        # ★ ファイルからSCOREINITとSCOREDIFFを取得
        scoreinit = ""
        scorediff = ""
        
        try:
            # 文字エンコーディングの自動判定（BOM付きUTF-8対応）
            with open(path, "rb") as f:
                raw = f.read()
                
            import chardet
            encoding_info = chardet.detect(raw)
            detected_encoding = encoding_info["encoding"] or "shift_jis"
            
            if detected_encoding.lower().startswith("utf") and raw.startswith(b"\xef\xbb\xbf"):
                encoding = "utf-8-sig"
            else:
                encoding = detected_encoding
            
            content = raw.decode(encoding, errors="replace")
            
            lines = content.splitlines()
            current_course = None
            in_target_course = False
            
            for line in lines:
                s = line.strip()
                
                # COURSE検出
                m = re.match(r"COURSE:\s*([^\s#;]+)", s, re.I)
                if m:
                    c = m.group(1).strip()
                    if c in ["0","1","2","3","4"]:
                        c = ["Easy","Normal","Hard","Oni","Edit"][int(c)]
                    current_course = c.capitalize()
                    in_target_course = (current_course == target)
                    continue
                
                # 選択されたCOURSE内でのみ値を取得
                if in_target_course:
                    # LEVEL取得
                    lm = re.match(r"LEVEL:\s*(\d+)", s, re.I)
                    if lm: 
                        level = lm.group(1)
                    
                    # SCOREINIT取得（COURSE内）
                    si_match = re.match(r"SCOREINIT:\s*(\d+)", s, re.I)
                    if si_match:
                        scoreinit = si_match.group(1)
                    
                    # SCOREDIFF取得（COURSE内）
                    sd_match = re.match(r"SCOREDIFF:\s*(\d+)", s, re.I)
                    if sd_match:
                        scorediff = sd_match.group(1)
                
                # グローバル領域の検索（COURSEブロック外）
                elif current_course is None:  # COURSEブロックに入る前
                    # SCOREINIT取得（グローバル）- 既に見つかっていない場合のみ
                    if not scoreinit:
                        si_match = re.match(r"SCOREINIT:\s*(\d+)", s, re.I)
                        if si_match:
                            scoreinit = si_match.group(1)
                    
                    # SCOREDIFF取得（グローバル）- 既に見つかっていない場合のみ
                    if not scorediff:
                        sd_match = re.match(r"SCOREDIFF:\s*(\d+)", s, re.I)
                        if sd_match:
                            scorediff = sd_match.group(1)
                        
        except Exception as e:
            print(f"ファイル読み込みエラー: {e}")
        
        # ★ シンプルに更新（常にファイルの値を使用）
        self.song_levels[song_idx] = level
        self.song_scoreinit[song_idx] = scoreinit
        self.song_scorediff[song_idx] = scorediff
        
        # GENREは変更されていない場合のみ設定
        if song_idx not in self.song_genres:
            self.song_genres[song_idx] = "ナムコオリジナル"
        
        # UIを更新
        self.update_song_settings()
    
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
        if not hasattr(self, 'song_settings_frame') or not self.song_settings_frame.winfo_exists():
            container = self.dan_window.winfo_children()[0].winfo_children()[0]
            self.song_settings_frame = LabelFrame(container, text="■ 各曲の設定 ■", 
                                                font=("メイリオ", 11, "bold"), padx=8, pady=8)
            self.song_settings_frame.pack(fill=tk.X, pady=(8, 0), before=self.gen_btn)
        
        for w in self.song_settings_frame.winfo_children():
            w.destroy()
        
        course_names = ["Easy", "Normal", "Hard", "Oni", "Edit"]
        course_jp   = ["かんたん", "ふつう", "むずかしい", "鬼", "裏鬼"]
        genres = ["ポップス","キッズ","アニメ","ボーカロイド","ゲームミュージック","バラエティ","クラシック","ナムコオリジナル"]
        
        # 譜面非表示のデフォルト値を保存する辞書を初期化
        if not hasattr(self, 'song_hidden'):
            self.song_hidden = {}
        
        for i in range(max(len(self.song_paths), 1)):
            # メインの行フレーム（1行目）
            row1 = Frame(self.song_settings_frame)
            row1.pack(fill=tk.X, pady=2)
        
            if i < len(self.song_paths):
                path = self.song_paths[i]
                fname = os.path.basename(path)
                # ファイル名表示を短く
                disp = fname if len(fname) <= 20 else fname[:17] + "..."
        
                # 1行目: 基本情報
                # 曲番号 (列0)
                Label(row1, text=f"曲{i+1}", font=("MS Gothic", 10, "bold"), 
                      width=4, anchor="w").grid(row=0, column=0, padx=(2,2), sticky="w")
        
                # ファイル名 (列1)
                Label(row1, text=disp, font=("MS Gothic", 9), fg="#333399", 
                      anchor="w", width=24).grid(row=0, column=1, padx=(0,10), sticky="w")
        
                # 難易度選択 (列2)
                avail = self.song_course_values.get(i, [])
                avail_jp = [course_jp[course_names.index(c)] for c in avail if c in course_names]
                cur = self.song_courses_temp.get(i, avail_jp[0] if avail_jp else "鬼")
                cbox = ttk.Combobox(row1, values=avail_jp, width=10, 
                                   font=("MS Gothic", 9), state="readonly")
                cbox.set(cur)
                cbox.grid(row=0, column=2, padx=(0,10), sticky="w")
                cbox.bind("<<ComboboxSelected>>", lambda e, idx=i, cb=cbox: self.on_course_changed(idx, cb))
        
                # LEVEL表示 (列3)
                lv = self.song_levels.get(i, "?")
                Label(row1, text=f"★{lv}", font=("MS Gothic", 10), fg="#0066cc", 
                      width=4, anchor="w").grid(row=0, column=3, padx=(0,10), sticky="w")
                
                # 譜面非表示チェックボックス (列4)
                hidden_var = tk.BooleanVar(value=self.song_hidden.get(i, False))
                hidden_cb = Checkbutton(row1, text="曲名を非表示", 
                                       variable=hidden_var,
                                       font=("MS Gothic", 9),
                                       bg=self.song_settings_frame.cget("bg"))
                hidden_cb.grid(row=0, column=4, padx=(0,2), sticky="w")
                
                # チェックボックスの値を保存する関数
                def make_hidden_callback(idx, var):
                    def callback(*args):
                        self.song_hidden[idx] = var.get()
                    return callback
                
                # traceで値の変更を監視
                hidden_var.trace("w", make_hidden_callback(i, hidden_var))
                
                # 2行目: 詳細設定
                row2 = Frame(self.song_settings_frame)
                row2.pack(fill=tk.X, pady=(0,5), padx=(40,0))
                
                # GENRE選択 (列0-1)
                Label(row2, text="GENRE:", font=("MS Gothic", 9, "bold"), fg="#008800",
                      width=6, anchor="w").grid(row=0, column=0, padx=(0,1), sticky="w")
                
                gbox = ttk.Combobox(row2, values=genres, width=18, 
                                   font=("MS Gothic", 8), state="readonly")
                gbox.set(self.song_genres.get(i, "ナムコオリジナル"))
                gbox.grid(row=0, column=1, padx=(0,15), sticky="w")
                gbox.bind("<<ComboboxSelected>>", lambda e, idx=i, gb=gbox: self.song_genres.__setitem__(idx, gb.get()))
        
               # SCOREINITエントリー (列2-3)
                Label(row2, text="INIT:", font=("MS Gothic", 9, "bold"), fg="#0000aa",
                      width=5, anchor="w").grid(row=0, column=2, padx=(0,1), sticky="w")
                
                init_e = Entry(row2, width=7, font=("MS Gothic", 9), 
                              justify="center", bg="#f0f8ff")
                init_e.insert(0, self.song_scoreinit.get(i, ""))
                init_e.grid(row=0, column=3, padx=(0,15), sticky="w")
                
                # リアルタイムで値を保存する関数を作成
                def make_init_callback(idx, entry):
                    def callback(*args):
                        self.song_scoreinit[idx] = entry.get().strip()
                    return callback
                
                init_e.bind("<KeyRelease>", make_init_callback(i, init_e))
        
                # SCOREDIFFエントリー (列4-5)
                Label(row2, text="DIFF:", font=("MS Gothic", 9, "bold"), fg="#cc4400",
                      width=5, anchor="w").grid(row=0, column=4, padx=(0,1), sticky="w")
                
                diff_e = Entry(row2, width=7, font=("MS Gothic", 9), 
                              justify="center", bg="#fff0f0")
                diff_e.insert(0, self.song_scorediff.get(i, ""))
                diff_e.grid(row=0, column=5, padx=(0,5), sticky="w")
                
                # リアルタイムで値を保存する関数を作成
                def make_diff_callback(idx, entry):
                    def callback(*args):
                        self.song_scorediff[idx] = entry.get().strip()
                    return callback
                
                diff_e.bind("<KeyRelease>", make_diff_callback(i, diff_e))
        
            else:
                Label(row1, text="曲を追加すると設定がここに表示されます", 
                      font=("MS Gothic", 9), fg="#999999")\
                    .grid(row=0, column=0, columnspan=5, pady=6)
        
            # 重量設定
            row1.grid_columnconfigure(1, weight=1)
        
        # サイズを変更しない - 固定サイズのまま
        # ウィンドウのレイアウトを更新するだけ
        if hasattr(self, 'dan_window') and self.dan_window:
            self.dan_window.update_idletasks()
    
    def on_genre_changed(self, song_idx, combobox):
        """GENREが変更されたときの処理"""
        selected_genre = combobox.get()
        self.song_genres[song_idx] = selected_genre
    
    def on_scoreinit_changed(self, song_idx, entry):
        """SCOREINITが変更されたときの処理"""
        value = entry.get().strip()
        self.song_scoreinit[song_idx] = value
    
    def on_scorediff_changed(self, song_idx, entry):
        """
        SCOREDIFF が変更されたときに呼ばれるハンドラ（ネスト定義を除去）
        単純に内部状態を更新するだけにしておく（UI から直接 bind して使用）
        """
        try:
            value = entry.get().strip()
            self.song_scorediff[song_idx] = value
        except Exception:
            # 安全に無視（UI が消えている等のケースに備える）
            pass

    def _close_dan_window(self):
        """
        段位道場ウィンドウを閉じる（クリーンアップ）
        - マウスホイールバインド解除
        - per_song_widgets の破棄
        - ウィンドウ破棄
        - 内部辞書の整理と UI 更新
        """
        # マウスホイールバインディング解除（存在すれば）
        try:
            if hasattr(self, 'dan_window') and self.dan_window:
                self.dan_window.unbind_all("<MouseWheel>")
        except:
            pass
    
        # per_song_widgets を安全に破棄
        try:
            if hasattr(self, 'per_song_widgets'):
                for item in list(self.per_song_widgets.keys()):
                    for widget_tuple in list(self.per_song_widgets[item]):
                        for w in widget_tuple:
                            try:
                                if getattr(w, "winfo_exists", lambda: False)():
                                    w.destroy()
                            except:
                                pass
                # self.per_song_widgets = {}
        except:
            pass
    
        # ウィンドウ破棄
        try:
            if hasattr(self, 'dan_window') and self.dan_window:
                self.dan_window.destroy()
        except:
            pass
        self.dan_window = None
    
        # song_courses_temp 等を現行の曲数に合わせて整理
        try:
            if hasattr(self, 'song_courses_temp'):
                self.song_courses_temp = {
                    i: self.song_courses_temp[i]
                    for i in range(len(self.song_paths))
                    if i in self.song_courses_temp
                }
        except:
            pass
    
        # song_settings_frame を更新（存在すれば）
        try:
            if hasattr(self, 'song_settings_frame') and self.song_settings_frame:
                self.update_song_settings()
        except:
            pass

    def toggle_per_song(self, item):
        var = self.per_song_vars[item]
        is_per_song = var.get()  # True=曲ごと、False=共通
    
        frame = self.per_song_frames[item]
    
        if is_per_song:
            # チェックON → フレーム表示
            # 条件1〜4の順番で管理
            if item not in self.per_song_order:
                # 正しい順序で追加
                item_order = {
                    "EXAM1": 1,
                    "EXAM2": 2,
                    "EXAM3": 3,
                    "EXAM4": 4
                }
                current_order = item_order.get(item, 5)
                
                # 挿入位置を探す
                insert_index = 0
                for i, existing_item in enumerate(self.per_song_order):
                    existing_order = item_order.get(existing_item, 6)
                    if current_order < existing_order:
                        break
                    insert_index = i + 1
                
                self.per_song_order.insert(insert_index, item)
            
            # ウィジェットを作成
            if item not in self.per_song_widgets or len(self.per_song_widgets[item]) == 0:
                self.create_per_song_widgets(item)
            
            # すべてのフレームを正しい順序で再配置
            self.rearrange_per_song_frames()
        else:
            # チェックOFF → フレーム非表示
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
            
            # 残りのフレームを再配置
            self.rearrange_per_song_frames()
    
        # 共通設定の有効/無効切り替え
        self.update_common_state(item)
    
    def rearrange_per_song_frames(self):
        """曲ごと設定フレームを条件1〜4の順番で再配置"""
        # 現在表示中のフレームをすべて非表示にする
        for item in self.DAN_ITEMS:
            if item in self.per_song_frames:
                self.per_song_frames[item].pack_forget()
        
        # 順番通りに表示する（条件1→条件2→条件3→条件4）
        for item in self.per_song_order:
            if item in self.per_song_frames and self.per_song_vars[item].get():
                self.per_song_frames[item].pack(pady=15, fill=tk.X)

        # --- 重要: per_song_frames の変更後に scrollregion を再計算 ---
        try:
            if hasattr(self, 'cond_canvas') and self.cond_canvas:
                bbox = self.cond_canvas.bbox("all")
                if bbox:
                    self.cond_canvas.configure(scrollregion=bbox)
                    # さらに、トップオーバースクロールが残っている場合は上端へ戻す
                    if self.cond_canvas.yview()[0] < 0.0:
                        self.cond_canvas.yview_moveto(0.0)
        except Exception:
            pass

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
        
        # EXAM1~4を条件1~4に変換するマッピング
        exam_to_condition = {
            "EXAM1": "条件1",
            "EXAM2": "条件2", 
            "EXAM3": "条件3",
            "EXAM4": "条件4"
        }
        
        # 表示用の条件名を取得
        condition_name = exam_to_condition.get(item, item)
        
        # タイトルフレーム
        title_frame = Frame(frame, bg="#f0f8ff")
        title_frame.pack(fill="x", pady=(0, 5))
        Label(title_frame, text=f"【{condition_name}】",  # ← ここを修正
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
            
            # ★ 選択されたCOURSE（デフォルト）からSCOREINITとSCOREDIFFを取得
            scoreinit = ""
            scorediff = ""
            
            try:
                # 文字エンコーディングの自動判定（BOM付きUTF-8対応）
                with open(path, "rb") as f:
                    raw = f.read()
                
                import chardet
                encoding_info = chardet.detect(raw)
                detected_encoding = encoding_info["encoding"] or "shift_jis"
                
                if detected_encoding.lower().startswith("utf") and raw.startswith(b"\xef\xbb\xbf"):
                    encoding = "utf-8-sig"
                else:
                    encoding = detected_encoding
                
                content = raw.decode(encoding, errors="replace")
                
                # デフォルトCOURSEを英語名に変換
                course_map = {"かんたん":"Easy","ふつう":"Normal","むずかしい":"Hard","鬼":"Oni","裏鬼":"Edit"}
                target_course = course_map.get(default_jp, "Oni")
                
                # 選択されたCOURSEから値を取得
                lines = content.splitlines()
                current_course = None
                in_target_course = False
                
                for line in lines:
                    s = line.strip()
                    
                    # COURSE検出
                    m = re.match(r"COURSE:\s*([^\s#;]+)", s, re.I)
                    if m:
                        c = m.group(1).strip()
                        if c in ["0","1","2","3","4"]:
                            c = ["Easy","Normal","Hard","Oni","Edit"][int(c)]
                        current_course = c.capitalize()
                        in_target_course = (current_course == target_course)
                        continue
                    
                    # 選択されたCOURSE内でのみ値を取得
                    if in_target_course:
                        si_match = re.match(r"SCOREINIT:\s*(\d+)", s, re.I)
                        if si_match:
                            scoreinit = si_match.group(1)
                        
                        sd_match = re.match(r"SCOREDIFF:\s*(\d+)", s, re.I)
                        if sd_match:
                            scorediff = sd_match.group(1)
                    
                    # グローバル領域の検索
                    elif current_course is None:
                        if not scoreinit:
                            si_match = re.match(r"SCOREINIT:\s*(\d+)", s, re.I)
                            if si_match:
                                scoreinit = si_match.group(1)
                        
                        if not scorediff:
                            sd_match = re.match(r"SCOREDIFF:\s*(\d+)", s, re.I)
                            if sd_match:
                                scorediff = sd_match.group(1)
                            
            except Exception as e:
                print(f"ファイル読み込みエラー: {e}")
            
            # GENREはデフォルト値、SCOREINITとSCOREDIFFは取得した値
            self.song_genres[idx] = "ナムコオリジナル"
            self.song_scoreinit[idx] = scoreinit
            self.song_scorediff[idx] = scorediff
            
            self.update_song_settings()
            self.update_add_button()
            # LEVEL取得を実行（念のため）
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
        """TJAファイルからCOURSE一覧を取得（BOM付きUTF-8対応）"""
        try:
            # エンコーディング自動判定
            with open(path, "rb") as f:
                raw = f.read()
            
            import chardet
            encoding_info = chardet.detect(raw)
            detected_encoding = encoding_info["encoding"] or "shift_jis"
            
            if detected_encoding.lower().startswith("utf") and raw.startswith(b"\xef\xbb\xbf"):
                encoding = "utf-8-sig"
            else:
                encoding = detected_encoding
            
            content = raw.decode(encoding, errors="ignore")
            
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
        
        except Exception as e:
            print(f"COURSE解析エラー ({path}): {e}")
            return ["Oni"]

    def extract_song_data(self, content, target_course):
        """曲データを抽出 - エンコーディングは呼び出し元で処理済み"""
        lines = content.splitlines()
        global_headers = {}
        course_headers = {}
        chart = []
        current_course = None
        in_chart = False
        chart_lines = []
        in_target_course = False
        measure_info = None  # 追加: #MEASURE情報を保存
    
        forbidden_starts = {"#START", "#START P1", "#START P2"}
        # forbidden_ends を set にし、厳密に先頭トークンで比較するようにする
        forbidden_ends = {"#END"}
    
        header_pattern = re.compile(r"^(\w+):\s*(.+)", re.IGNORECASE)
        course_pattern = re.compile(r"^COURSE:\s*(.+)", re.IGNORECASE)
        measure_pattern = re.compile(r"^#MEASURE\s+(\S+)", re.IGNORECASE)  # 追加: #MEASUREパターン
    
        for raw_line in lines:
            # 先頭/末尾の空白は除去するが、元の行は chart にそのまま保持するため raw_line を使用
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith(";"):
                # コメントだけの行はスキップ（chart には追加しない）
                continue
    
            upper = line.upper()
            first_tok = upper.split()[0] if upper else ""
    
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
                in_target_course = (current_course == target_course)
                # reset chart state when entering a new course block
                in_chart = False
                chart_lines = []
                continue
    
            # #MEASURE検出（選んだコース内のみ）
            measure_match = measure_pattern.match(line)
            if measure_match and in_target_course:
                measure_info = measure_match.group(1).strip()
                if measure_info in ["44", "4/4"]:
                    measure_info = "4/4"
                # do not `continue` here; MEASURE can be part of headers or chart handling
    
            # ヘッダー行
            header_match = header_pattern.match(line)
            if header_match:
                key = header_match.group(1).upper()
                value = header_match.group(2).strip()
    
                # SUBTITLEの特別処理: 空白または(--)の場合は空白のまま
                if key == "SUBTITLE":
                    if not value or value.isspace():
                        value = ""
                    elif value.startswith("--"):
                        remaining = value[2:].strip()
                        value = remaining if remaining else ""
                    elif value == "--":
                        value = ""
    
                # ★ 選択されたCOURSE内でのみSCOREINITとSCOREDIFFを取得
                if in_target_course and key in ("SCOREINIT", "SCOREDIFF"):
                    course_headers[key] = value
                    continue
    
                # GENREは完全除外（手動設定のみ使用）
                if key == "GENRE":
                    continue
    
                if key == "BALLOON":
                    # BALLOONだけは選んだコース優先(他のコースは無視)
                    if in_target_course:
                        balloons = [v.strip() for v in value.split(",") if v.strip().isdigit()]
                        course_headers["BALLOON"] = course_headers.get("BALLOON", []) + balloons
                else:
                    # その他のヘッダーは選択されたCOURSE内でのみ保存
                    if in_target_course:
                        course_headers[key] = value
                    elif key not in course_headers:  # グローバル値は補完用（ただし既にコース値がない場合）
                        global_headers[key] = value
                continue
    
            # 譜面開始/終了(選んだコースのみ) - 先頭トークンで厳密判定
            if first_tok in forbidden_starts:
                if in_target_course:
                    in_chart = True
                    chart_lines = [raw_line]
                continue
            elif first_tok in forbidden_ends:
                if in_chart:
                    chart_lines.append(raw_line)
                    chart = chart_lines
                    in_chart = False
                    chart_lines = []
                continue
    
            if in_chart:
                chart_lines.append(raw_line)
    
        # BALLOONは選んだコースのものだけ使う
        if "BALLOON" in course_headers:
            course_headers["BALLOON"] = ",".join(course_headers["BALLOON"])
    
        # ヘッダーは選択されたCOURSE優先 + グローバル補完
        headers = {**global_headers, **course_headers}
    
        return headers, chart, measure_info  # measure_infoも返すように変更

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
        
        # ヘッダー部分を指定された順序で出力
        code.append(f"TITLE:{dan_title}\n")
        
        # SUBTITLE: 空白の場合は空白のまま（"--" を挿入しない）
        # 段位道場のヘッダーとしてSUBTITLEは空白で良い
        code.append("SUBTITLE:\n")  # 空白を挿入（"--"ではなく空のまま）
        
        # BPMとWAVEは1曲目から取得（BOM付UTF-8対応）
        first_song_bpm = ""
        first_song_wave = ""
        if self.song_paths:
            try:
                # BOM付UTF-8対応のファイル読み込み
                with open(self.song_paths[0], "rb") as f:
                    raw_data = f.read()
                
                # BOM検出と適切なエンコーディングの選択
                if raw_data.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
                    content = raw_data.decode('utf-8-sig')
                elif raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):  # UTF-16 BOM
                    # UTF-16はあまり使われないが、一応対応
                    try:
                        content = raw_data.decode('utf-16')
                    except:
                        content = raw_data.decode('shift_jis', errors='ignore')
                else:
                    # BOMなしの場合はSHIFT-JISまたはUTF-8を試す
                    try:
                        content = raw_data.decode('shift_jis')
                    except:
                        content = raw_data.decode('utf-8', errors='ignore')
                
                # BPMを検索
                bpm_match = re.search(r'^BPM:\s*(.+)', content, re.MULTILINE | re.IGNORECASE)
                if bpm_match:
                    first_song_bpm = bpm_match.group(1).strip()
                # WAVEを検索
                wave_match = re.search(r'^WAVE:\s*(.+)', content, re.MULTILINE | re.IGNORECASE)
                if wave_match:
                    first_song_wave = wave_match.group(1).strip()
            except Exception as e:
                print(f"BPM/WAVE取得エラー: {e}")
    
        code.append(f"BPM:{first_song_bpm}\n")
        code.append(f"WAVE:{first_song_wave}\n")
        
        # SCOREMODEは段位道場なので2固定
        code.append("SCOREMODE:2\n")
        
        # COURSEはDan固定
        code.append("COURSE:Dan\n")
        
        # GENRE
        dan_color = getattr(self, "dan_genre_var", tk.StringVar(value="金")).get()
        code.append(f"GENRE:段位-{dan_color}\n")
        
        # LEVEL（適当な値を設定、または1曲目から取得）
        level = "10"
        if self.song_paths:
            try:
                # BOM付UTF-8対応のファイル読み込み
                with open(self.song_paths[0], "rb") as f:
                    raw_data = f.read()
                
                # BOM検出と適切なエンコーディングの選択
                if raw_data.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
                    content = raw_data.decode('utf-8-sig')
                elif raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):  # UTF-16 BOM
                    try:
                        content = raw_data.decode('utf-16')
                    except:
                        content = raw_data.decode('shift_jis', errors='ignore')
                else:
                    try:
                        content = raw_data.decode('shift_jis')
                    except:
                        content = raw_data.decode('utf-8', errors='ignore')
                
                level_match = re.search(r'^LEVEL:\s*(\d+)', content, re.MULTILINE | re.IGNORECASE)
                if level_match:
                    level = level_match.group(1).strip()
            except Exception as e:
                print(f"LEVEL取得エラー: {e}")
        
        code.append(f"LEVEL:{level}\n")
    
        course_id_map = {"Easy": "0", "Normal": "1", "Hard": "2", "Oni": "3", "Edit": "4"}
        all_balloons = []
        song_data = []
    
        # 各曲のヘッダー・譜面抽出
        for i, path in enumerate(self.song_paths):
            selected_jp = self.song_courses_temp.get(i, "鬼")
            map_jp = {"かんたん": "Easy", "ふつう": "Normal", "むずかしい": "Hard", "鬼": "Oni", "裏鬼": "Edit"}
            target_course = map_jp.get(selected_jp, "Oni")
    
            try:
                # BOM付UTF-8対応のファイル読み込み
                with open(path, "rb") as f:
                    raw_data = f.read()
                
                # BOM検出と適切なエンコーディングの選択
                if raw_data.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
                    content = raw_data.decode('utf-8-sig')
                elif raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):  # UTF-16 BOM
                    try:
                        content = raw_data.decode('utf-16')
                    except:
                        content = raw_data.decode('shift_jis', errors='ignore')
                else:
                    # BOMなしの場合はSHIFT-JISまたはUTF-8を試す
                    try:
                        content = raw_data.decode('shift_jis')
                    except:
                        content = raw_data.decode('utf-8', errors='ignore')
    
                headers, chart, measure_info = self.extract_song_data(content, target_course)
    
                # BALLOONは選択したコースのものだけ取得
                if headers.get("BALLOON"):
                    balloons = [b.strip() for b in headers["BALLOON"].split(",") if b.strip().isdigit()]
                    all_balloons.extend(balloons)
    
                # ★ GENRE: open_dan_windowで指定した値のみ使用(デフォルト: ナムコオリジナル)
                genre_value = self.song_genres.get(i, "ナムコオリジナル").strip()
                if not genre_value:  # 空白の場合
                    genre_value = "ナムコオリジナル"
                
                # ★ SCOREINIT: ファイルから取得した値とUI入力値をマージ
                file_scoreinit = headers.get("SCOREINIT", "").strip()
                ui_scoreinit = self.song_scoreinit.get(i, "").strip()
                
                # UIで入力されていればUIの値を優先、そうでなければファイルの値
                final_scoreinit = ui_scoreinit if ui_scoreinit else file_scoreinit
                # 数値チェックとデフォルト設定
                if not final_scoreinit or not final_scoreinit.isdigit():
                    final_scoreinit = "0"
                    
                # ★ SCOREDIFF: ファイルから取得した値とUI入力値をマージ
                file_scorediff = headers.get("SCOREDIFF", "").strip()
                ui_scorediff = self.song_scorediff.get(i, "").strip()
                
                # UIで入力されていればUIの値を優先、そうでなければファイルの値
                final_scorediff = ui_scorediff if ui_scorediff else file_scorediff
                # 数値チェックとデフォルト設定
                if not final_scorediff or not final_scorediff.isdigit():
                    final_scorediff = "0"
    
                level = self.song_levels.get(i, headers.get("LEVEL", "10")).strip()
    
                # SUBTITLEの処理: 空白の場合は空白のまま
                subtitle = headers.get("SUBTITLE", "").strip()
                # extract_song_dataで既に処理されているが、念のため再度処理
                if not subtitle or subtitle.isspace() or subtitle == "--":
                    subtitle = ""
                elif subtitle.startswith("--"):
                    # (--)を削除して、残りがあればそれを取得
                    remaining = subtitle[2:].strip()
                    subtitle = remaining if remaining else ""
    
                song_data.append({
                    "title": headers.get("TITLE", "無題").strip() or "無題",
                    "subtitle": subtitle,  # 空白の場合は空白のまま
                    "wave": headers.get("WAVE", "").strip(),
                    "genre": genre_value,  # ★ 手動設定の値のみ
                    "scoreinit": final_scoreinit,  # ★ マージした値（UI優先）
                    "scorediff": final_scorediff,  # ★ マージした値（UI優先）
                    "chart": chart,
                    "course": target_course,
                    "level": level,
                    "bpm": headers.get("BPM", ""),
                    "offset": headers.get("OFFSET", "0"),
                    "measure": measure_info,
                })
    
            except Exception as e:
                messagebox.showerror("読み込み失敗", f"{os.path.basename(path)}\n{e}", parent=self.dan_window)
                return
    
        # BALLOON出力（LEVELの直後、EXAM1より前に配置）
        if all_balloons:
            code.append(f"BALLOON:{','.join(all_balloons)}\n")
    
        # 共通合格条件（BALLOONの後に出力）
        for item in self.DAN_ITEMS:
            if not self.per_song_vars[item].get():
                try:
                    s = self.get_exam_str_common(item)
                    code.append(f"{item}:{s}\n")
                except ValueError as e:
                    messagebox.showerror("入力エラー", f"{item}: {e}", parent=self.dan_window)
                    return
    
        # #STARTの前に2つの改行を追加
        code.append("\n\n#START\n\n\n")
    
        # 各曲の出力
        for i, data in enumerate(song_data):
            # SUBTITLEの処理: 空白の場合は空白のまま
            subtitle_for_nextsong = data["subtitle"]
            
            # 譜面非表示フラグを取得
            is_hidden = self.song_hidden.get(i, False)
            
            # #NEXTSONGの各フィールドを準備（既にマージ済みの値を使用）
            parts = [
                data["title"],  # 1. 曲名
                subtitle_for_nextsong,  # 2. サブタイトル（空白の場合は空白のまま）
                data["genre"],  # 3. ジャンル（open_dan_windowの値のみ使用）
                data["wave"] if data["wave"] else "-",  # 4. 音源ファイル名
                data["scoreinit"],  # 5. 初期スコア（UI優先でマージした値）
                data["scorediff"],  # 6. スコア差分（UI優先でマージした値）
                course_id_map.get(data["course"], "3"),  # 7. コースID（0:Easy, 1:Normal, 2:Hard, 3:Oni, 4:Edit）
                data["level"] or "10",  # 8. レベル
                "true" if is_hidden else "false",  # 9. 譜面非表示フラグ（1=非表示, 0=表示）
            ]
            code.append("#NEXTSONG " + ",".join(parts) + "\n")
    
            # 個別合格条件
            for item in self.per_song_order:
                if i < len(self.per_song_widgets.get(item, [])):
                    try:
                        s = self.get_exam_str_per(item, i)
                        code.append(f"{item}:{s}\n")
                    except ValueError as e:
                        messagebox.showerror("入力エラー", f"曲{i+1} {item}: {e}", parent=self.dan_window)
                        return
    
            if data["bpm"]:
                code.append(f"#BPMCHANGE {data['bpm'].strip()}\n")
    
            try:
                offset = float(data["offset"])
                if offset < 0:
                    code.append(f"#DELAY {-offset}\n")
            except:
                pass
    
            if i >= 1:
                current_measure = data.get("measure")
                if current_measure is None or current_measure != "4/4":
                    has_measure_before_chart_start = False
                    for line in data["chart"]:
                        stripped = line.strip()
                        if not stripped or stripped.startswith("//") or stripped.startswith(";"):
                            continue
                        
                        if stripped.endswith(","):
                            break
                        
                        if stripped.upper().startswith("#MEASURE"):
                            has_measure_before_chart_start = True
                            break
                    
                    if not has_measure_before_chart_start:
                        code.append("#MEASURE 4/4\n")
    
            forbidden = {"#START", "#END"}
            for line in data["chart"]:
                if line.strip().upper() not in forbidden:
                    code.append(line.rstrip("\r\n") + "\n")
            code.append("\n")
            if i < len(song_data) - 1:
                code.append(",\n")
    
        code.append("#END\n")
    
        try:
            # 1. TJA本体を保存
            # 生成されたTJAテキストを結合
            tja_text = "".join(code)
            
            # すべてのコメント（// と ;）を削除
            tja_text = self.remove_all_comments(tja_text)
            
            # SHIFT-JISで保存（cp932はSHIFT-JISのMicrosoft拡張）
            with open(save_path, "w", encoding="cp932", newline="\n") as f:
                f.write(tja_text)
    
            # 2. #NEXTSONGから音源名を取得してコピー
            copied_files = []
            missing_files = []
            dest_folder = os.path.dirname(save_path)
        
            for i, data in enumerate(song_data):
                audio_name = data["wave"].strip()
                if not audio_name:
                    continue
                
                # 拡張子の制限を削除（.oggだけでなく、すべての音声ファイルを処理）
                source_tja_folder = os.path.dirname(self.song_paths[i])
                
                # 共通のヘルパーメソッドを使用してパス解決
                source_audio_path = self.resolve_wave_file_path(audio_name, source_tja_folder)
        
                if not source_audio_path or not os.path.exists(source_audio_path):
                    # 音声ファイルが見つからない場合、警告リストに追加して続行
                    missing_files.append(audio_name)
                    continue
        
                dest_audio_path = os.path.join(dest_folder, os.path.basename(source_audio_path))
        
                # すでに同じ場所にある場合はコピーしない
                if os.path.abspath(source_audio_path) == os.path.abspath(dest_audio_path):
                    copied_files.append(os.path.basename(source_audio_path))
                    continue
        
                try:
                    shutil.copy2(source_audio_path, dest_audio_path)
                    copied_files.append(os.path.basename(source_audio_path))
                except Exception as e:
                    # コピー失敗時も警告リストに追加して続行
                    missing_files.append(f"{audio_name} (コピーエラー: {e})")
    
            # 3. 完了メッセージ
            msg = f"段位道場TJAを保存しました！\n\n{os.path.basename(save_path)}"
            if copied_files:
                msg += f"\n\n以下の音源も自動でコピーしました\n" + "\n".join(f"・{f}" for f in copied_files)
            
            # 見つからなかった/コピー失敗したファイルがある場合、警告を追加
            if missing_files:
                msg += "\n\n⚠ 以下の音声ファイルが見つからないか、コピーに失敗しました:\n"
                msg += "\n".join(f"・{f}" for f in missing_files)
                messagebox.showwarning("保存完了（警告あり）", msg, parent=self.dan_window)
            elif not copied_files:
                msg += "\n\n（音源ファイルは見つかりませんでした）"
                messagebox.showinfo("保存完了", msg, parent=self.dan_window)
            else:
                messagebox.showinfo("保存完了", msg, parent=self.dan_window)
    
            # 4. 保存先フォルダを開く
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

    def new_file(self):
        """新規ファイルを作成"""
        # 未保存の変更があるかチェック
        if self._unsaved_changes:
            response = messagebox.askyesnocancel(
                "新規作成",
                "編集中の内容が保存されていません。\n\n"
                "「はい」 → 保存して新規作成\n"
                "「いいえ」 → 保存せずに新規作成\n"
                "「キャンセル」 → 編集に戻る",
                icon="warning"
            )
            
            if response is True:  # 「はい」保存して新規作成
                if self.current_file:
                    self.save_file()
                else:
                    self.save_as_file()
                    if self.current_file:  # 保存ダイアログでキャンセルされた場合
                        return
            elif response is False:  # 「いいえ」保存せず新規作成
                pass  # そのまま新規作成
            else:  # 「キャンセル」
                return
        
        # テキストエリアをクリア
        self.text.delete("1.0", tk.END)
        
        # 状態をリセット
        self.current_file = None
        self.current_encoding = 'cp932'
        self._unsaved_changes = False
        self._text_content_hash = None
        
        # タイトルを更新
        self.update_title()
        
        # 構文ハイライトを更新
        self.apply_syntax_highlighting()
        
        # 行番号などを更新
        self.update_all()
        
        # ステータスバーにメッセージ表示
        self.statusbar.config(text="新規ファイルを作成しました")
 
    def on_closing(self):
        # グローバルバインディング解除
        try:
            self.root.unbind_all("<F3>")
            self.root.unbind_all("<Shift-F3>")
        except:
            pass
        
        #構文チェックウィンドウを閉じる
        if hasattr(self, 'syntax_window') and self.syntax_window:
            try:
                self.syntax_window.destroy()
            except:
                pass
            self.syntax_window = None
        
        #プレビュー実行中のプロセスを終了
        if hasattr(self, 'preview_running') and self.preview_running:
            if hasattr(self, 'preview_process') and self.preview_process:
                try:
                    self.preview_process.terminate()
                    self.preview_process.wait(timeout=1)
                except:
                    try:
                        self.preview_process.kill()
                    except:
                        pass
                finally:
                    self.preview_running = False
                    self.preview_process = None
        
        #BPMカウンターウィンドウを閉じる
        if hasattr(self, 'bpm_window') and self.bpm_window:
            try:
                self.bpm_window.destroy()
            except:
                pass
            self.bpm_window = None
        
        #段位道場ウィンドウを閉じる
        if hasattr(self, 'dan_window') and self.dan_window:
            try:
                self.dan_window.destroy()
            except:
                pass
            self.dan_window = None
        
        #TODO管理ウィンドウを閉じる
        if hasattr(self, 'todo_window') and self.todo_window:
            try:
                self.todo_window.destroy()
            except:
                pass
            self.todo_window = None
        
        #OFFSET調整ウィンドウを閉じる
        if hasattr(self, 'offset_window') and self.offset_window:
            try:
                self.offset_window.destroy()
            except:
                pass
            self.offset_window = None
        
        #検索ウィンドウを閉じる
        if hasattr(self, 'search_window') and self.search_window:
            try:
                self.search_window.destroy()
            except:
                pass
            self.search_window = None
        
        #設定保存
        self.save_config()
        
        #変更があるかチェック
        if self._unsaved_changes:
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
                    try:
                        self.save_file()
                    except Exception as e:
                        messagebox.showerror("保存エラー", f"保存に失敗しました:\n{e}")
                        return
                else:
                    try:
                        self.save_as_file()
                    except Exception as e:
                        messagebox.showerror("保存エラー", f"保存に失敗しました:\n{e}")
                        return
                
                self.root.destroy()
                
            elif response is False:
                self.root.destroy()
                
            else:
                return
            
        else:
            if messagebox.askokcancel("終了", "TJA Editorを終了しますか?"):
                self.root.destroy()
       
if __name__ == "__main__":
    root = tk.Tk()
    app = TJAEditor(root)
    root.mainloop()