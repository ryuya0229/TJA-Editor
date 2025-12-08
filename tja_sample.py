import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, Toplevel, ttk
from tkinter import font as tkfont
from tkinter import Listbox, Scrollbar, Button, Entry, Label, Frame, LabelFrame, Checkbutton
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "MS Gothic"
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, FancyBboxPatch
import re
import sys
import os
import tempfile
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
        self.root.resizable(True, True)
        self.current_file = None
        self.current_encoding = 'cp932'  # ← この行を追加
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
            self.main_font = ("BIZ UDPゴシック", 15)
        elif "Yu Gothic UI" in tkfont.families():
            self.main_font = ("Yu Gothic UI", 15)
        else:
            self.main_font = ("Consolas", 14)

        self._create_menu()
        self._create_widgets()
        self._bind_events()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.song_settings_frame = None
        self.load_config() 
        self.text.bind("<Return>", self.smart_comma_on_enter)
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
        viewmenu.add_command(label="ダークモード切り替え", command=self.toggle_dark_mode, accelerator="Ctrl+D")
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
        audio_menu = tk.Menu(toolmenu, tearoff=0)
        if PYDUB_AVAILABLE:
            audio_menu.add_command(label="OFFSET自動計測(WAV/OGG対応)", 
                                  command=self.auto_measure_offset_ogg)
            audio_menu.add_command(label="OFFSET自動調節(波形表示+精密調整)", 
                                  command=self.auto_adjust_offset)
        else:
            audio_menu.add_command(label="OFFSET自動計測(無効・pydub未導入)",
                                  command=lambda: messagebox.showwarning(
                                      "機能無効", 
                                      "pydub がインストールされていないため利用できません"))  
        toolmenu.add_cascade(label="音源・タイミング", menu=audio_menu)
        
        toolmenu.add_separator()
        
        # ========== プレビュー・再生 ==========
        preview_menu = tk.Menu(toolmenu, tearoff=0)
        preview_menu.add_command(label="太鼓さん次郎でプレビュー再生 (F5)", 
                                command=self.preview_play, 
                                accelerator="F5")
        preview_menu.add_separator()
        preview_menu.add_command(label="太鼓さん次郎のパスを再設定...", 
                                command=self.reset_taikojiro_path)
        
        toolmenu.add_cascade(label="プレビュー・再生", menu=preview_menu)
        
        toolmenu.add_separator()
        
        # ========== 譜面分析・検証 ==========
        analysis_menu = tk.Menu(toolmenu, tearoff=0)
        analysis_menu.add_command(label="AI添削(ヒューリスティック分析)", 
                                 command=self.ai_autoreview)
        analysis_menu.add_separator()
        analysis_menu.add_command(label="統計情報を表示", 
                                 command=lambda: messagebox.showinfo(
                                     "統計", 
                                     "右側パネルに各難易度の統計が表示されています"))
        
        toolmenu.add_cascade(label="譜面分析・検証", menu=analysis_menu)
        
        toolmenu.add_separator()
        
        # ========== ファイル管理・配布 ==========
        file_manage_menu = tk.Menu(toolmenu, tearoff=0)
        file_manage_menu.add_command(label="配布用ZIPを作成…", 
                                    command=self.create_distribution_zip,
                                    accelerator="Ctrl+E")
        file_manage_menu.add_separator()
        file_manage_menu.add_command(label="バックアップフォルダを開く", 
                                    command=self.open_backup_folder)
        file_manage_menu.add_command(label="バックアップ履歴を表示・復元...", 
                            command=self.show_backup_history)
        file_manage_menu.add_separator()
        file_manage_menu.add_command(label="譜面を画像化（太鼓風）", 
                                    command=self.export_chart_image)
        toolmenu.add_cascade(label="ファイル管理", menu=file_manage_menu)
        
        menubar.add_cascade(label="ツール", menu=toolmenu)

        # ヘルプメニュー追加（最後に追加するのが自然）
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="バージョン情報", command=self.show_version)
        helpmenu.add_separator()
        helpmenu.add_command(label="このエディタについて", command=self.show_about)
        menubar.add_cascade(label="ヘルプ", menu=helpmenu)
        self.root.config(menu=menubar)
        
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
    
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                self.recent_files = []
        
    def save_config(self):
        """終了時に設定を保存"""
        config = {
            "recent_files": self.recent_files,
            "dark_mode": self.dark_mode,
            "last_folder": self.last_folder,
            "taikojiro_path": self.get_taikojiro_path()
        }
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定保存エラー: {e}")
            
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

    def export_chart_image(self):
        """太鼓の達人風の譜面画像を生成"""
        if not self.current_file:
            messagebox.showwarning("未保存", "ファイルを保存してから実行してください")
            return
        
        content = self.text.get("1.0", tk.END)
        chart_data = self._parse_chart_for_taiko_image(content)
        
        if not chart_data:
            messagebox.showwarning("譜面なし", "譜面データが見つかりません")
            return
        
        self._generate_taiko_style_image(chart_data)
    
    def _parse_chart_for_taiko_image(self, content):
        """TJA内容から太鼓風画像用データを抽出(BALLOON値をヘッダーから確実に取得)"""
        lines = content.splitlines()
        
        title = "無題"
        subtitle = ""
        level = "?"
        bpm = 120.0
        course = "鬼"
        balloon_values = []  # ← BALLOON値のリスト
        
        chart_measures = []
        in_chart = False
        gogo_mode = False
        current_bpm = 120.0
        
        for line in lines:
            s = line.strip()
            
            # コメント行は無視
            if s.startswith("//") or s.startswith(";"):
                continue
            
            # ヘッダー情報取得
            if s.upper().startswith("TITLE:"):
                title = s.split(":", 1)[1].strip()
            elif s.upper().startswith("SUBTITLE:"):
                subtitle = s.split(":", 1)[1].strip()
            elif s.upper().startswith("LEVEL:"):
                level = s.split(":", 1)[1].strip()
            elif s.upper().startswith("BPM:"):
                try:
                    bpm = float(s.split(":", 1)[1].strip())
                    current_bpm = bpm
                except:
                    pass
            elif s.upper().startswith("COURSE:"):
                c = s.split(":", 1)[1].strip()
                course_map = {"0":"かんたん","1":"ふつう","2":"むずかしい","3":"鬼","4":"裏鬼",
                             "easy":"かんたん","normal":"ふつう","hard":"むずかしい","oni":"鬼","edit":"裏鬼"}
                course = course_map.get(c.lower(), c)
            elif s.upper().startswith("BALLOON:"):
                # ← BALLOON値を取得(コメント除去も実施)
                balloon_str = s.split(":", 1)[1]
                # コメント除去(//, ; の前まで)
                balloon_str = re.split(r"//|;", balloon_str)[0].strip()
                # カンマ区切りで分割して数値のみ抽出
                balloon_values = []
                for v in balloon_str.split(","):
                    v_clean = v.strip()
                    if v_clean.isdigit():
                        balloon_values.append(v_clean)
            
            # 譜面開始
            if s.upper() in ["#START", "#P1START", "#P2START"]:
                in_chart = True
                continue
            elif s.upper() in ["#END", "#P1END", "#P2END"]:
                break
            
            if not in_chart:
                continue
            
            # コマンド処理
            if s.upper() == "#GOGOSTART":
                gogo_mode = True
                continue
            elif s.upper() == "#GOGOEND":
                gogo_mode = False
                continue
            elif s.upper().startswith("#BPMCHANGE"):
                try:
                    current_bpm = float(s.split()[1])
                except:
                    pass
                continue
            
            # 譜面行を解析
            if "," in s:
                notes_part = s.split(",")[0]
                # コメント除去
                notes_part = re.split(r"//|;", notes_part)[0].strip()
                
                if notes_part:  # 空でなければ追加
                    chart_measures.append({
                        "notes": notes_part,
                        "is_gogo": gogo_mode,
                        "bpm": current_bpm
                    })
        
        return {
            "title": title,
            "subtitle": subtitle,
            "level": level,
            "bpm": bpm,
            "course": course,
            "measures": chart_measures,
            "balloon_values": balloon_values  # ← BALLOON値を返す
        }
    
    def _generate_taiko_style_image(self, data):
        """太鼓の達人風の譜面画像を生成(改善版 - 小節またぎ対応)"""
        
        # 画像サイズ計算
        num_measures = len(data['measures'])
        measures_per_row = 4  # 1行あたり4小節
        num_rows = (num_measures + measures_per_row - 1) // measures_per_row
        
        fig_width = 14  # ← 幅を狭くして小節間隔を詰める
        row_height = 1.0
        title_height = 0.5
        fig_height = title_height + num_rows * row_height + 0.3
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        fig.patch.set_facecolor('#d0d0d0')
        ax.set_facecolor('#d0d0d0')
        
        # ← 左端余白(小節番号用のスペース)
        left_margin = 0.4
        
        # タイトル背景
        title_y = num_rows * row_height
        title_bg = Rectangle((left_margin, title_y), fig_width - left_margin, title_height, 
                             facecolor='#4a4a4a', edgecolor='none', zorder=1)
        ax.add_patch(title_bg)
        
        # タイトルとサブタイトルを組み合わせて表示
        if data['subtitle']:
            full_title = f"{data['title']} {data['subtitle']}"
        else:
            full_title = data['title']
        
        ax.text(left_margin + 0.3, title_y + title_height * 0.65, full_title, 
                fontsize=18, fontweight='bold', color='white',
                ha='left', va='center')
        
        # レベル表示(★)- 右寄せ
        if data['level'].isdigit():
            level_int = int(data['level'])
            stars = '★' * level_int + '☆' * (10 - level_int)
        else:
            stars = data['level']
        
        ax.text(fig_width - 0.3, title_y + title_height * 0.65, 
                f"{data['course']}  {stars}",
                fontsize=14, color='white', ha='right', va='center')
        
        # 譜面描画の設定
        measure_width = (fig_width - left_margin) / measures_per_row
        note_y = 0.5  # ノーツの基準Y座標
        
        balloon_index = 0  # ← 風船のインデックス
        balloon_values = data.get('balloon_values', [])
        
        for idx, measure in enumerate(data['measures']):
            row = num_rows - 1 - (idx // measures_per_row)
            col = idx % measures_per_row
            
            x_start = left_margin + col * measure_width
            y_start = row * row_height
            
            # 背景(ゴーゴータイム)
            if measure['is_gogo']:
                gogo_bg = Rectangle((x_start, y_start), measure_width, row_height,
                                   facecolor='#ffcccc', edgecolor='none', alpha=0.6, zorder=0)
                ax.add_patch(gogo_bg)
            else:
                normal_bg = Rectangle((x_start, y_start), measure_width, row_height,
                                     facecolor='#e0e0e0', edgecolor='none', zorder=0)
                ax.add_patch(normal_bg)
            
            # 譜面ライン
            line_y = y_start + note_y
            ax.plot([x_start, x_start + measure_width], [line_y, line_y],
                   color='#808080', linewidth=3, zorder=1)
            
            # 小節線(左端) ← 太くして視認性向上
            ax.plot([x_start, x_start], [y_start + 0.15, y_start + 0.85],
                   color='white', linewidth=4, zorder=2)
            
            # 小節番号表示(4小節ごと)
            measure_num = idx + 1
            if measure_num % 4 == 1:
                ax.text(left_margin * 0.5, y_start + 0.5, str(measure_num),
                       fontsize=9, color='#333333', ha='center', va='center',
                       fontweight='bold',
                       bbox=dict(boxstyle='round,pad=0.25', facecolor='white', 
                                edgecolor='#cccccc', linewidth=1.5, alpha=0.9))
            
            # ノーツ配置(48分対応 + 小節またぎ考慮)
            notes = measure['notes']
            if not notes:
                continue
            
            # ← 音符の密度を計算
            note_count = len(notes)
            non_zero_count = sum(1 for n in notes if n != '0')
            density = non_zero_count / note_count if note_count > 0 else 0
            
            # 密度が高い場合は間隔を詰める
            spacing_factor = 0.5 if density > 0.25 else 1.0
            
            # ← 小節末尾に音符があるかチェック
            has_end_note = False
            for i in range(len(notes) - 1, max(len(notes) - 4, -1), -1):  # 後ろ3文字をチェック
                if notes[i] != '0':
                    has_end_note = True
                    break
            
            # 次の小節の先頭に音符があるかチェック
            next_has_start_note = False
            if idx + 1 < len(data['measures']):
                next_notes = data['measures'][idx + 1]['notes']
                for i in range(min(3, len(next_notes))):  # 先頭3文字をチェック
                    if next_notes[i] != '0':
                        next_has_start_note = True
                        break
            
            # ← 小節またぎの音符がある場合は余白なし、それ以外は2%の余白
            if has_end_note and next_has_start_note:
                measure_usage = 1.0  # 余白なし(小節またぎ対応)
            else:
                measure_usage = 0.98  # わずかな余白(2%)
            
            note_positions = []
            lcm = 192  # 4,8,16,32,48の最小公倍数
            
            for i, note in enumerate(notes):
                if note != '0':  # 休符以外
                    # 192分音符基準での位置(0.0~1.0の範囲)
                    base_position = (i * lcm // note_count) / lcm
                    # ← 最初の音符は小節線上、その後は密集
                    position = base_position * spacing_factor * measure_usage
                    note_positions.append((position, note, i))
            
            for position, note, original_idx in note_positions:
                x = x_start + position * measure_width
                y = y_start + note_y
                
                if note == '1':  # ドン(小)
                    circle = Circle((x, y), 0.06, facecolor='#ff4444',
                                   edgecolor='#cc0000', linewidth=2, zorder=3)
                    ax.add_patch(circle)
                    
                elif note == '2':  # カツ(小)
                    circle = Circle((x, y), 0.06, facecolor='#4488ff',
                                   edgecolor='#0044cc', linewidth=2, zorder=3)
                    ax.add_patch(circle)
                    
                elif note == '3':  # ドン(大)
                    circle = Circle((x, y), 0.10, facecolor='#ff4444',
                                   edgecolor='#ffdd00', linewidth=3.5, zorder=3)
                    ax.add_patch(circle)
                    
                elif note == '4':  # カツ(大)
                    circle = Circle((x, y), 0.10, facecolor='#4488ff',
                                   edgecolor='#ffdd00', linewidth=3.5, zorder=3)
                    ax.add_patch(circle)
                    
                elif note == '5':  # 連打開始
                    end_idx = original_idx + 1
                    while end_idx < len(notes) and notes[end_idx] not in ['6', '8']:
                        end_idx += 1
                    
                    if end_idx < len(notes):
                        end_base_position = (end_idx * lcm // note_count) / lcm
                        end_position = end_base_position * spacing_factor * measure_usage
                        x_end = x_start + end_position * measure_width
                        renda_width = x_end - x
                        
                        renda_rect = FancyBboxPatch((x, y - 0.05), renda_width, 0.10,
                                                   boxstyle="round,pad=0.01",
                                                   facecolor='#ffdd00', edgecolor='#ff8800',
                                                   linewidth=2.5, zorder=2)
                        ax.add_patch(renda_rect)
                        
                elif note == '7':  # 風船 ← 数値表示追加
                    circle = Circle((x, y), 0.08, facecolor='#ff88ff',
                                   edgecolor='#cc00cc', linewidth=2.5, zorder=3)
                    ax.add_patch(circle)
                    
                    # ← BALLOON値を取得して表示
                    if balloon_index < len(balloon_values):
                        balloon_text = balloon_values[balloon_index]
                        ax.text(x, y, balloon_text, fontsize=6, ha='center', va='center',
                               color='white', fontweight='bold', zorder=4)
                        balloon_index += 1
                    else:
                        # 値がない場合は「風」と表示
                        ax.text(x, y, '風', fontsize=5, ha='center', va='center',
                               color='white', fontweight='bold', zorder=4)
                    
                elif note == '9':  # 芋(大連打)
                    end_idx = original_idx + 1
                    while end_idx < len(notes) and notes[end_idx] not in ['6', '8']:
                        end_idx += 1
                    
                    if end_idx < len(notes):
                        end_base_position = (end_idx * lcm // note_count) / lcm
                        end_position = end_base_position * spacing_factor * measure_usage
                        x_end = x_start + end_position * measure_width
                        imo_width = x_end - x
                        
                        imo_rect = FancyBboxPatch((x, y - 0.07), imo_width, 0.14,
                                                 boxstyle="round,pad=0.015",
                                                 facecolor='#ffff00', edgecolor='#ff4400',
                                                 linewidth=3, zorder=2)
                        ax.add_patch(imo_rect)
        
        # 軸設定
        ax.set_xlim(0, fig_width)
        ax.set_ylim(0, num_rows * row_height + title_height + 0.1)
        ax.set_aspect('equal', adjustable='box')
        ax.axis('off')
        
        # 保存
        default_filename = f"{data['title']}_{data['course']}.png"
        default_filename = re.sub(r'[\\/:*?"<>|]', '', default_filename)
        
        output_path = filedialog.asksaveasfilename(
            title="譜面画像を保存",
            defaultextension=".png",
            filetypes=[("PNG画像", "*.png"), ("JPEG画像", "*.jpg")],
            initialfile=default_filename
        )
        
        if output_path:
            plt.tight_layout(pad=0.2)
            plt.savefig(output_path, dpi=200, facecolor='#d0d0d0', bbox_inches='tight')
            plt.close()
            
            messagebox.showinfo("保存完了", 
                               f"譜面画像を保存しました:\n{os.path.basename(output_path)}\n\n"
                               f"小節数: {num_measures}\n"
                               f"解像度: {int(fig_width * 200)} × {int(fig_height * 200)} px")
            
            if os.name == "nt":
                os.startfile(output_path)

    def apply_dark_mode(self):
        """ダークモードの見た目を強制的に適用（起動時用）"""
        if self.dark_mode:
            self.toggle_dark_mode(force=True)
        else:
            self.toggle_dark_mode(force=False)
        
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

    def ai_autoreview(self):
        """
        AI風（ヒューリスティック）自動添削。
        - 譜面を解析して改善提案（TODOコメント）を生成
        - 指摘を一覧表示し、ユーザーが選んで挿入できる
        """
        content = self.text.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("AI添削", "譜面が空です。TJAを読み込んでください。")
            return

        lines = content.splitlines()

        # ---------- ユーティリティ ----------
        def is_chart_line(s):
            s2 = s.strip()
            # 数字が含まれる行（譜面行）をチャート行とみなす
            return bool(re.search(r"[1-8]", s2)) and not s2.lstrip().startswith("#")

        # measure 単位で解析する：#START〜#ENDの間をカンマで小節分割して行番号を推定
        in_chart = False
        current_measure_line = None
        measures = []  # list of dict {line_num, text, don, katsu, total, unique_pattern_hash}
        pending_buf = ""
        pending_line = None

        for i, raw in enumerate(lines):
            line_num = i + 1
            s = raw.rstrip("\n")
            upper = s.strip().upper()

            if upper.startswith("#START") or upper.startswith("#P1START") or upper.startswith("#P2START"):
                in_chart = True
                pending_buf = ""
                pending_line = line_num + 1  # next lines belong to measures
                continue
            if upper.startswith("#END") or upper.startswith("#P1END") or upper.startswith("#P2END"):
                # flush pending_buf
                if pending_buf is not None:
                    parts = pending_buf.split(",")
                    for part in parts:
                        if part == "":
                            measures.append({"line_num": pending_line, "text": part, "don":0, "katsu":0, "total":0, "hash":""})
                            pending_line = line_num
                            continue
                        cleaned = re.split(r"//|;", part)[0]
                        don = len(re.findall(r"[13]", cleaned))
                        katsu = len(re.findall(r"[24]", cleaned))
                        measures.append({"line_num": pending_line, "text": cleaned, "don":don, "katsu":katsu, "total":don+katsu, "hash":hash(cleaned)})
                        pending_line = line_num
                in_chart = False
                pending_buf = ""
                pending_line = None
                continue

            if not in_chart:
                continue

            # コメント除去末尾スペース除去
            clean = re.split(r"//|;", s)[0].replace(" ", "").replace("\t","")
            pending_buf += clean
            # flush complete measures if comma exists
            while "," in pending_buf:
                part, pending_buf = pending_buf.split(",", 1)
                if part == "":
                    measures.append({"line_num": line_num, "text": part, "don":0, "katsu":0, "total":0, "hash":""})
                else:
                    don = len(re.findall(r"[13]", part))
                    katsu = len(re.findall(r"[24]", part))
                    measures.append({"line_num": line_num, "text": part, "don":don, "katsu":katsu, "total":don+katsu, "hash":hash(part)})

        # If still pending at EOF inside chart, flush remainder
        if pending_buf:
            parts = pending_buf.split(",")
            for part in parts:
                if part == "":
                    measures.append({"line_num": len(lines), "text": part, "don":0, "katsu":0, "total":0, "hash":""})
                else:
                    don = len(re.findall(r"[13]", part))
                    katsu = len(re.findall(r"[24]", part))
                    measures.append({"line_num": len(lines), "text": part, "don":don, "katsu":katsu, "total":don+katsu, "hash":hash(part)})

        if not measures:
            messagebox.showinfo("AI添削", "譜面データが見つかりませんでした（#START/#END 間を確認してください）。")
            return

        # ---------- 統計算出 ----------
        totals = [m["total"] for m in measures]
        import statistics
        mean = statistics.mean(totals) if totals else 0
        stdev = statistics.pstdev(totals) if totals else 0

        # detect repeated patterns (同じハッシュが連続している場合)
        repeat_candidates = []
        for idx in range(len(measures)-3):
            # check 4-measure repetition
            h = measures[idx]["hash"]
            if h != 0 and h == measures[idx+1]["hash"] == measures[idx+2]["hash"] == measures[idx+3]["hash"]:
                repeat_candidates.append((idx, idx+3))

        # ---------- ルールベースの指摘生成 ----------
        suggestions = []  # tuples (line_num, message)

        # 1) 密度ピーク（平均 + 2*stdev を越える小節）
        threshold = mean + 2 * stdev
        for m in measures:
            if m["total"] > 0 and threshold > 0 and m["total"] >= threshold:
                suggestions.append((m["line_num"], f"密度ピーク（ノーツ:{m['total']}）が検出されます。難所か確認・緩和を検討してください。"))

        # 2) 突然の落差（隣接と比べて2倍以上）
        for i in range(1, len(measures)):
            a = measures[i-1]["total"]
            b = measures[i]["total"]
            if a > 0 and b >= 2 * a and b >= 8:
                suggestions.append((measures[i]["line_num"], f"直前小節から急にノーツが増えています（{a}→{b}）。導線/休憩を検討してください。"))
            if b > 0 and a >= 2 * b and a >= 8:
                suggestions.append((measures[i-1]["line_num"], f"直後小節から急にノーツが減っています（{a}→{b}）。違和感がないか確認してください。"))

        # 3) DON/KATSU バランスが極端（片寄り）
        for m in measures:
            if m["total"] >= 8:
                if m["don"] == 0 and m["katsu"] >= 8:
                    suggestions.append((m["line_num"], f"この小節はカツ偏重（{m['katsu']}カツ）。ドンを一部混ぜてバランスを改善すると叩きやすくなります。"))
                if m["katsu"] == 0 and m["don"] >= 8:
                    suggestions.append((m["line_num"], f"この小節はドン偏重（{m['don']}ドン）。カツ挿入を検討してください。"))

        # 4) 連続パターンの繰り返し（退屈/単調）
        for start, end in repeat_candidates:
            ln = measures[start]["line_num"]
            suggestions.append((ln, f"{start+1}〜{end+1} 小節が同一パターンで繰り返されています（単調化の可能性）。変化案を入れてみてください。"))

        # 5) 長い空白小節（ノーツ0）やカンマ抜け
        for m in measures:
            if m["text"] == "" and m["total"] == 0:
                suggestions.append((m["line_num"], "空小節（カンマのみ/ノーツなし）です。意図的か確認してください。"))

        # 6) 風船(7)の不一致チェック（簡易：7の数が奇数）
        all_7 = len(re.findall(r"7", content))
        if all_7 % 2 == 1:
            # try to find approximate line where 7 appears unpaired
            suggestions.append((1, "風船(7) の個数が奇数です。開始/終了が対応しているか確認してください。"))

        # deduplicate suggestions by (line_num,message)
        uniq = []
        seen = set()
        for item in suggestions:
            key = (item[0], item[1])
            if key not in seen:
                uniq.append(item)
                seen.add(key)
        suggestions = uniq

        # ---------- UI: 指摘一覧表示 ----------
        win = Toplevel(self.root if hasattr(self, 'root') else self)
        win.title("AI添削（提案一覧）")
        win.geometry("720x420")

        lbl = Label(win, text=f"自動生成された提案（{len(suggestions)}件）: 挿入する行を選んで「コメントを挿入」を押してください。")
        lbl.pack(padx=8, pady=6)

        frame = Frame(win)
        frame.pack(fill="both", expand=True, padx=8, pady=(0,8))

        sb = Scrollbar(frame)
        sb.pack(side="right", fill="y")

        listbox = Listbox(frame, yscrollcommand=sb.set, selectmode="extended", font=("Meiryo", 10))
        for ln, msg in suggestions:
            display = f"行{ln}: {msg}"
            listbox.insert("end", display)
        listbox.pack(fill="both", expand=True)
        sb.config(command=listbox.yview)

        def apply_comments():
            sel = listbox.curselection()
            if not sel:
                if not messagebox.askyesno("全件挿入確認", "選択がありません。全件を挿入しますか？"):
                    return
                indices = range(0, listbox.size())
            else:
                indices = sel

            # gather selected suggestions and sort by line_num descending to insert safely
            to_insert = []
            for i in indices:
                text = listbox.get(i)
                m = re.match(r"行(\d+):\s*(.+)", text)
                if m:
                    ln = int(m.group(1))
                    msg = m.group(2)
                    to_insert.append((ln, msg))
            if not to_insert:
                messagebox.showinfo("AI添削", "挿入する提案が見つかりません。")
                return

            to_insert.sort(key=lambda x: x[0], reverse=True)
            for ln, msg in to_insert:
                insert_pos = f"{ln}.0"
                comment = f";AI: {msg}\n"
                try:
                    self.text.insert(insert_pos, comment)
                except Exception as e:
                    # fallback: append at end
                    self.text.insert(tk.END, comment)

            win.destroy()
            messagebox.showinfo("AI添削", f"{len(to_insert)} 件のコメントを挿入しました。")

        btn_frame = Frame(win)
        btn_frame.pack(fill="x", padx=8, pady=8)
        Button(btn_frame, text="コメントを挿入", command=apply_comments, width=18).pack(side="left", padx=6)
        Button(btn_frame, text="全件を挿入", command=lambda: [listbox.select_set(0, listbox.size()-1), apply_comments()], width=12).pack(side="left", padx=6)
        Button(btn_frame, text="閉じる", command=win.destroy, width=12).pack(side="right", padx=6)
        
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

    def _create_widgets(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.linenumbers = tk.Canvas(main_frame, width=80, bg="white", highlightthickness=0)
        self.linenumbers.pack(side=tk.LEFT, fill=tk.Y)

        center_frame = tk.Frame(main_frame)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vscroll = ttk.Scrollbar(center_frame, orient=tk.VERTICAL)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll = ttk.Scrollbar(center_frame, orient=tk.HORIZONTAL)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        count_frame = tk.Frame(center_frame, width=230, bg="#f0f0f0", relief="sunken", bd=2)
        count_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,0))
        count_frame.pack_propagate(False)  # 幅を固定

        # 超重要！これがないと他の機能でエラーになる
        self.count_frame = count_frame

        # タイトルラベル
        title_lbl = tk.Label(count_frame, text="■ 各難易度統計 ■", bg="#f0f0f0", 
                             font=("メイリオ", 11, "bold"), fg="#333333")
        title_lbl.pack(pady=(10, 5))

        # 統計表示テキスト（スクロール不要で超軽量）
        self.count_text = tk.Text(count_frame, width=30, height=28,
                                  font=("Courier New", 11), 
                                  bg="#f0f0f0", fg="#000000",
                                  relief="flat", state="disabled",
                                  wrap="none")
        self.count_text.pack(padx=10, pady=(0, 10), expand=True, fill=tk.BOTH)

        # ========== 左側のメインエディタ ==========
        text_container = tk.Frame(center_frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(text_container, yscrollcommand=vscroll.set, xscrollcommand=hscroll.set,
                            undo=True, maxundo=self.MAX_UNDO, font=self.main_font, wrap=tk.NONE)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vscroll.config(command=self.text.yview)
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        hscroll.config(command=self.text.xview)
        self.linenumbers.config(yscrollcommand=vscroll.set)

        # ========== ステータスバー ==========
        self.statusbar = tk.Label(self.root, text="準備完了", relief=tk.SUNKEN, anchor="w", font=("MS Gothic", 10))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        # 検索ハイライト設定
        self.text.tag_configure("search", background="yellow", foreground="black")
        
        # 起動後に1回だけ行番号更新
        self.root.after(100, self.update_linenumbers)

    def _bind_events(self):
        self.root.bind_all("<Control-o>", lambda e: self.open_file())
        self.root.bind_all("<Control-s>", lambda e: self.save_file())
        self.root.bind_all("<Control-Shift-s>", lambda e: self.save_as_file())
        self.root.bind_all("<Control-f>", lambda e: self.open_search())
        self.root.bind_all("<Control-d>", lambda e: self.toggle_dark_mode())
        self.root.bind_all("<Control-e>", lambda e: self.check_syntax_errors())  # ← 追加
        self.root.bind("<F5>", lambda event: self.preview_play())
        self.root.bind_all("<Control-e>", lambda e: self.create_distribution_zip())
        # キー入力中もリアルタイムで行番号を更新
        self.text.bind("<Key>", lambda e: self.root.after_idle(self.update_linenumbers))
        self.text.bind("<KeyRelease>", lambda e: self.root.after_idle(self.update_all))
        self.text.bind("<ButtonRelease>", lambda e: self.root.after_idle(self.update_linenumbers))
        self.text.bind("<Configure>", lambda e: self.root.after_idle(self.update_linenumbers))
        # マウスホイール
        self.text.bind("<MouseWheel>", lambda e: (
            self.text.yview_scroll(-int(e.delta/120), "units"),
            self.root.after_idle(self.update_linenumbers)
        ) or "break")
        self.text.bind("<Shift-MouseWheel>", lambda e: self.text.xview_scroll(-int(e.delta/120), "units") or "break")
        self.statusbar.config(text="準備完了 | F5: プレビュー再生")
        self.text.bind("<<Modified>>", self._on_text_modified)

    def _on_text_modified(self, event=None):
        self.text.edit_modified(False)  # フラグをリセットしないと連続で発火しない！
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
            bg, fg, ins, sel = "#1e1e1e", "#d4d4d4", "#d4d4d4", "#264f78"
            linenum_bg = "#1e1e1e"
            status_bg, status_fg = "#2d2d30", "#d4d4d4"
            count_bg, count_fg = "#2b2b2b", "#ffffff"
        else:
            bg, fg, ins, sel = "white", "black", "black", "lightblue"
            linenum_bg = "white"
            status_bg, status_fg = "SystemButtonFace", "black"
            count_bg, count_fg = "#f0f0f0", "#000000"
    
        # メインエディタ
        self.text.config(bg=bg, fg=fg, insertbackground=ins, selectbackground=sel)
        self.linenumbers.config(bg=linenum_bg)
        self.statusbar.config(bg=status_bg, fg=status_fg)
    
        # 統計枠
        self.count_frame.config(bg=count_bg)
        self.count_text.config(bg=count_bg, fg=count_fg)
        for widget in self.count_frame.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(bg=count_bg, fg=count_fg)
    
        # ttk スクロールバー
        style = ttk.Style()
        if self.dark_mode:
            style.theme_use('clam')
            style.configure("Vertical.TScrollbar", background="#3c3c3c", troughcolor="#1e1e1e", arrowcolor="#d4d4d4")
            style.configure("Horizontal.TScrollbar", background="#3c3c3c", troughcolor="#1e1e1e", arrowcolor="#d4d4d4")
        else:
            style.theme_use('default')
    
        # 行番号とステータス更新
        self.update_linenumbers()
        self.update_statusbar()
    
        # 設定保存（force時も含めて毎回保存）
        self.save_config()  # ← ここで確実に保存


    def _apply_dark_mode_recursive(self, widget, bg, fg):
        try:
            if isinstance(widget, (tk.Entry, tk.Listbox, tk.Text)):
                widget.config(bg=bg, fg=fg, insertbackground=fg)
            elif isinstance(widget, tk.Label):
                widget.config(bg=bg, fg=fg)
        except:
            pass
        for child in widget.winfo_children():
            self._apply_dark_mode_recursive(child, bg, fg)

    def update_all(self):
        self.update_linenumbers()
        self.update_status()
        self.update_statusbar()
        filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
        self.root.title(f"TJA Editor - {filename}")

    def update_statusbar(self):
        line, col = self.text.index(tk.INSERT).split('.')
        total_notes = len(re.findall(r'[12345678]', self.text.get("1.0", tk.END)))
        filename = os.path.basename(self.current_file) if self.current_file else "新規ファイル"
        mode = "ダーク" if self.dark_mode else "ライト"
        self.statusbar.config(text=f"{filename} │ 行:{line} 列:{int(col)+1} │ 総ノート:{total_notes} │ {mode}モード")
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
        width = max(4, len(str(total_lines)) + 1)
        canvas_w = max(80, 60 + width * 10)
        self.linenumbers.config(width=canvas_w)
        try:
            start_idx = self.text.index("@0,0")
            end_idx = self.text.index(f"@0,{self.text.winfo_height()}")
        except:
            return
        start_line = int(start_idx.split('.')[0])
        end_line = min(int(end_idx.split('.')[0]) + 2, total_lines)
        line_num = max(1, start_line)
        index = f"{line_num}.0"
        color = "#777777" if not self.dark_mode else "#e0e0e0"
        while line_num <= end_line:
            dline = self.text.dlineinfo(index)
            if dline is None:
                break
            y = dline[1] + dline[3] // 2
            text = f"{line_num:>{width}}"
            self.linenumbers.create_text(canvas_w - 12, y, anchor="e", text=text, fill=color, font=self.main_font)
            line_num += 1
            index = self.text.index(f"{index} +1line")

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
                    backup_name = f"{ts}_{os.path.basename(self.current_file)}"  # ← ここを変更
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
        file_path = filedialog.asksaveasfilename(initialdir=self.last_folder, defaultextension=".tja", filetypes=[("TJA files", "*.tja")])
        if file_path:
            self.last_folder = os.path.dirname(file_path)
            try:
                content = self.text.get("1.0", tk.END)
                # 自動バックアップ
                if os.path.exists(file_path):
                    backup = file_path + "~"
                    shutil.copy2(file_path, backup)
                # ← 保存時のエンコーディングを設定
                with open(file_path, 'w', encoding=self.current_encoding, newline='\n') as f:
                    f.write(content.rstrip() + "\n")
                self.current_file = file_path
                self.update_all()
                messagebox.showinfo("保存", "保存しました")
                # 最近ファイル追加
                if file_path in self.recent_files:
                    self.recent_files.remove(file_path)
                self.recent_files.insert(0, file_path)
                self.recent_files = self.recent_files[:self.MAX_RECENT]
                self.update_recent_menu()
            except Exception as e:
                messagebox.showerror("エラー", f"保存失敗\n{e}")

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
        if not LIBROSA_AVAILABLE:
            messagebox.showerror("エラー", "librosaがインストールされていません\npip install librosa")
            return
        path = filedialog.askopenfilename(filetypes=[("音声ファイル", "*.ogg *.wav")])
        if not path: return
        
        # ← より安全な一時ファイル処理
        temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(path)[1], prefix="tja_temp_")
        
        try:
            os.close(temp_fd)  # ← ファイルディスクリプタを閉じる
            shutil.copy2(path, temp_path)
            
            try:
                y, sr = librosa.load(temp_path, sr=None, mono=True)
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm = round(tempo, 2)
            except Exception:
                bpm = simpledialog.askfloat("BPM手動入力", "自動取得失敗\nBPMを手動で入力してください", minvalue=1, maxvalue=300, initialvalue=120)
                if bpm is None:
                    return
            
            wave = f"WAVE:{os.path.basename(path)}\n"
            bpm_line = f"BPM:{bpm}\n"
            self.text.insert(tk.INSERT, wave + bpm_line)
            self.text.see(tk.INSERT)
            self.root.after_idle(self.update_all)
            messagebox.showinfo("成功", f"{os.path.basename(path)}\nBPM: {bpm} を挿入しました")
        
        finally:
            # ← 確実に削除
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                print(f"一時ファイル削除失敗: {e}")

    def open_dan_window(self):
        if self.dan_window and self.dan_window.winfo_exists():
            self.dan_window.lift()
            return
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
        self.dan_window.geometry("840x700")  # ★ 初期サイズを大きく変更
        self.dan_window.resizable(True, True)
        
        # ★ Canvas + Scrollbar 構造
        canvas = tk.Canvas(self.dan_window)
        v_scroll = Scrollbar(self.dan_window, orient="vertical", command=canvas.yview)
        h_scroll = Scrollbar(self.dan_window, orient="horizontal", command=canvas.xview)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        
        scrollable_frame = Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        canvas.pack(side="top", fill="both", expand=True)
        
        def _on_mousewheel(event):
            canvas.yview_scroll(-1*(event.delta//120), "units")
        self.dan_window.bind_all("<MouseWheel>", _on_mousewheel)
        
        # ★ コンテナの幅を固定せずに自然な幅に
        container = Frame(scrollable_frame, padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)
        
        # タイトル入力
        title_frame = Frame(container)
        title_frame.pack(pady=10, fill=tk.X)
        Label(title_frame, text="TITLE:", font=("MS Gothic", 12)).grid(row=0, column=0, sticky="e", padx=5)
        self.dan_title_entry = Entry(title_frame, font=("MS Gothic", 12), width=50)  # ★ 幅を広げる
        self.dan_title_entry.grid(row=0, column=1, sticky="ew", padx=5)
        title_frame.grid_columnconfigure(1, weight=1)
        
        # ジャンル選択
        genre_frame = Frame(container)
        genre_frame.pack(pady=10, fill=tk.X)
        Label(genre_frame, text="段位ジャンル:", font=("MS Gothic", 12)).grid(row=0, column=0, sticky="e", padx=5)
        if not hasattr(self, 'dan_genre_var'):
            self.dan_genre_var = tk.StringVar(value="金")
        genre_combo = ttk.Combobox(genre_frame, textvariable=self.dan_genre_var,
                                   values=["黄", "青", "赤", "銀", "金"],
                                   state="readonly", width=10, font=("MS Gothic", 12))
        genre_combo.grid(row=0, column=1, sticky="w", padx=5)
        Label(genre_frame, text="(GENRE:段位-〇 として出力されます)", font=("MS Gothic", 10), fg="gray")\
            .grid(row=0, column=2, padx=20, sticky="w")
        
        # 曲リスト
        list_frame = Frame(container)
        list_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        Label(list_frame, text="曲リスト:", font=("MS Gothic", 12)).grid(row=0, column=0, sticky="w")
        self.song_listbox = Listbox(list_frame, font=("Courier", 11), height=8, selectmode=tk.SINGLE, width=80)  # ★ 幅を広げる
        self.song_listbox.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        list_scroll = Scrollbar(list_frame, orient="vertical", command=self.song_listbox.yview)
        list_scroll.grid(row=1, column=1, sticky="ns")
        self.song_listbox.config(yscrollcommand=list_scroll.set)
        
        # ★ 曲設定フレーム(後で動的にリサイズ)
        self.song_settings_frame = LabelFrame(container, text="各曲の設定(難易度・ジャンル・スコア)", 
                                              font=("MS Gothic", 12), padx=10, pady=10)
        self.song_settings_frame.pack(pady=15, fill=tk.BOTH, expand=True)
        
        list_frame.grid_rowconfigure(1, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # ボタン群
        btn_frame = Frame(container)
        btn_frame.pack(pady=10)
        self.add_button = Button(btn_frame, text="曲追加 (3/3)", command=self.add_song, font=("MS Gothic", 11))
        self.add_button.grid(row=0, column=0, padx=10)
        Button(btn_frame, text="削除", command=self.remove_song, font=("MS Gothic", 11)).grid(row=0, column=1, padx=10)
        Button(btn_frame, text="↑", command=self.move_up, font=("MS Gothic", 11)).grid(row=0, column=2, padx=10)
        Button(btn_frame, text="↓", command=self.move_down, font=("MS Gothic", 11)).grid(row=0, column=3, padx=10)
        
        self.exam_types = ["魂ゲージ", "良の数", "可の数", "不可の数", "スコア", "連打数", "叩けた数", "最大コンボ数"]
        self.exam_codes = {"魂ゲージ":"g","良の数":"jp","可の数":"jg","不可の数":"jb","スコア":"s","連打数":"r","叩けた数":"h","最大コンボ数":"c"}
        self.comparisons_jp = ["～以上", "～未満"]
        self.comparisons = {"～以上":"m", "～未満":"l"}
        self.common_frame = LabelFrame(container, text="共通合格条件", font=("MS Gothic", 12), padx=10, pady=10, relief="groove", borderwidth=2)
        self.common_frame.pack(pady=15, fill=tk.X)
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
            row = Frame(self.common_frame)
            row.grid(row=idx, column=0, sticky="w", pady=5, padx=5)
            Label(row, text=f"{item}:", font=("MS Gothic", 11)).grid(row=0, column=0, padx=5)
            tc = ttk.Combobox(row, values=self.exam_types, width=12, state="readonly", font=("MS Gothic", 10))
            tc.grid(row=0, column=1, padx=3)
            tc.set(typ)
            cc = ttk.Combobox(row, values=self.comparisons_jp, width=8, state="readonly", font=("MS Gothic", 10))
            cc.grid(row=0, column=2, padx=3)
            cc.set(comp)
            ne = Entry(row, width=10, font=("MS Gothic", 10))
            ne.grid(row=0, column=3, padx=3)
            ne.insert(0, n)
            Label(row, text="/", font=("MS Gothic", 10)).grid(row=0, column=4)
            ge = Entry(row, width=10, font=("MS Gothic", 10))
            ge.grid(row=0, column=5, padx=3)
            ge.insert(0, g)
            self.common_type_combos[item] = tc
            self.common_comp_combos[item] = cc
            self.common_normal_entries[item] = ne
            self.common_gold_entries[item] = ge
            var = tk.IntVar(value=0)
            cb = Checkbutton(row, text="曲ごとに設定", variable=var, command=lambda i=item: self.toggle_per_song(i), font=("MS Gothic", 10))
            cb.grid(row=0, column=6, padx=20)
            self.per_song_vars[item] = var
            pf = LabelFrame(container, text=f"{item} - 曲ごとの条件", font=("MS Gothic", 12), padx=10, pady=10, relief="groove", borderwidth=2)
            pf.pack_forget()
            self.per_song_frames[item] = pf
            self.per_song_widgets[item] = []
            self.update_common_state(item)
        
        self.gen_btn = Button(container, text="TJA生成", command=self.generate_dan_code,
                              font=("MS Gothic", 15, "bold"), relief="raised", borderwidth=4, padx=30, pady=12)
        self.gen_btn.pack(pady=30)
        
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
            # チェックON → フレーム表示 + ウィジェット作成
            if item not in self.per_song_order:
                self.per_song_order.append(item)
            frame.pack(pady=15, fill=tk.X, before=self.gen_btn)
            self.create_per_song_widgets(item)
        else:
            # チェックOFF → フレーム非表示 + 内部ウィジェットを完全破棄
            frame.pack_forget()
            if item in self.per_song_order:
                self.per_song_order.remove(item)

            # ← ここが最重要！ウィジェットを完全に削除
            for widget_tuple in self.per_song_widgets[item]:
                for w in widget_tuple:
                    w.destroy()  # 完全破棄
            self.per_song_widgets[item].clear()

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
        for w in frame.winfo_children():
            w.destroy()
        self.per_song_widgets[item] = []
        for i in range(3):
            sub = Frame(frame)
            Label(sub, text=f"曲{i+1}:", font=("MS Gothic", 11)).grid(row=0, column=0, padx=10, pady=5, sticky="e")
            tc = ttk.Combobox(sub, values=self.exam_types, width=12, state="readonly", font=("MS Gothic", 10))
            tc.grid(row=0, column=1, padx=5)
            tc.set(self.common_type_combos[item].get())
            cc = ttk.Combobox(sub, values=self.comparisons_jp, width=8, state="readonly", font=("MS Gothic", 10))
            cc.grid(row=0, column=2, padx=5)
            cc.set(self.common_comp_combos[item].get())
            ne = Entry(sub, width=10, font=("MS Gothic", 10))
            ne.grid(row=0, column=3, padx=5)
            ne.insert(0, self.common_normal_entries[item].get())
            Label(sub, text="/", font=("MS Gothic", 12)).grid(row=0, column=4, padx=0)
            ge = Entry(sub, width=10, font=("MS Gothic", 10))
            ge.grid(row=0, column=5, padx=5)
            ge.insert(0, self.common_gold_entries[item].get())
            sub.pack(fill=tk.X, pady=3)
            self.per_song_widgets[item].append((tc, cc, ne, ge))

    def update_song_settings(self):
        if not hasattr(self, 'song_listbox') or not self.song_listbox.winfo_exists():
            return
        
        self.song_listbox.delete(0, tk.END)
        if self.song_paths:
            for i, path in enumerate(self.song_paths):
                self.song_listbox.insert(tk.END, f"{i+1}. {os.path.basename(path)}")
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

        for i in range(max(len(self.song_paths), 1)):
            row = Frame(self.song_settings_frame)
            row.pack(fill=tk.X, pady=4)

            if i < len(self.song_paths):
                path = self.song_paths[i]
                fname = os.path.basename(path)
                disp = fname if len(fname) <= 28 else "…" + fname[-26:]

                # 曲番号
                Label(row, text=f"曲{i+1}", font=("MS Gothic", 11, "bold")).grid(row=0, column=0, padx=(4,2))

                # ファイル名（28文字まで）
                Label(row, text=disp, font=("MS Gothic", 10), fg="#333399", anchor="w").grid(row=0, column=1, sticky="w", padx=(0,6))

                # 難易度（width=8）
                avail = self.song_course_values.get(i, [])
                avail_jp = [course_jp[course_names.index(c)] for c in avail if c in course_names]
                cur = self.song_courses_temp.get(i, avail_jp[0] if avail_jp else "鬼")
                cbox = ttk.Combobox(row, values=avail_jp, width=10, font=("MS Gothic", 10), state="readonly")
                cbox.set(cur)
                cbox.grid(row=0, column=2, padx=2)
                cbox.bind("<<ComboboxSelected>>", lambda e, idx=i, cb=cbox: self.on_course_changed(idx, cb))

                #LEVEL
                lv = self.song_levels.get(i, "?")
                Label(row, text=f"★{lv}", font=("MS Gothic", 11), fg="#0066cc", width=4, anchor="w").grid(row=0, column=3, padx=2)

                # GENRE（width=14でギリ収まる）
                Label(row, text="GENRE:", font=("MS Gothic", 10, "bold"), fg="#008800").grid(row=0, column=4, padx=(10,1))
                gbox = ttk.Combobox(row, values=genres, width=18, font=("MS Gothic", 9), state="readonly")
                gbox.set(self.song_genres.get(i, "ナムコオリジナル"))
                gbox.grid(row=0, column=5, padx=1)
                gbox.bind("<<ComboboxSelected>>", lambda e, idx=i: self.song_genres.__setitem__(idx, gbox.get()))

                # INIT / DIFF
                Label(row, text="INIT:", font=("MS Gothic", 10, "bold"), fg="#0000aa").grid(row=0, column=6, padx=(8,1))
                init_e = Entry(row, width=7, font=("MS Gothic", 10), justify="center", bg="#f0f8ff")
                init_e.insert(0, self.song_scoreinit.get(i, ""))
                init_e.grid(row=0, column=7, padx=1)

                Label(row, text="DIFF:", font=("MS Gothic", 10, "bold"), fg="#cc4400").grid(row=0, column=8, padx=(6,1))
                diff_e = Entry(row, width=7, font=("MS Gothic", 10), justify="center", bg="#fff0f0")
                diff_e.insert(0, self.song_scorediff.get(i, ""))
                diff_e.grid(row=0, column=9, padx=1)

                # バインド略（同じ）

            else:
                Label(row, text="曲を追加すると設定がここに表示されます", font=("MS Gothic", 10), fg="#999999")\
                    .grid(row=0, column=0, columnspan=10, pady=6)

            row.grid_columnconfigure(1, weight=1)

        # ← これが大事！800×800に固定
        self.dan_window.geometry("900x700")
        self.dan_window.minsize(900, 700)
        self.dan_window.maxsize(800, 1000)  # 高さだけ少し伸ばせる
            
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

    def generate_dan_code(self):
        if not self.song_paths:
            messagebox.showerror("エラー", "曲が1つも選択されていません", parent=self.dan_window)
            return

        code = []
        title = self.dan_title_entry.get().strip()
        code.append(f"TITLE:{title}\n" if title else "TITLE:段位道場\n")
        code.append("SUBTITLE:--\n")
        code.append("WAVE:\n")
        code.append("SCOREMODE:2\n")
        code.append("COURSE:Dan\n")
        dan_color = getattr(self, 'dan_genre_var', tk.StringVar(value="金")).get()
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
        all_balloons = []   # ← ただのリスト（順序・重複をそのまま残す）
        song_data = []

        for i, path in enumerate(self.song_paths):
            selected_jp = self.song_courses_temp.get(i, "鬼")
            map_jp = {"かんたん":"Easy", "ふつう":"Normal", "むずかしい":"Hard", "鬼":"Oni", "裏鬼":"Edit"}
            target = map_jp.get(selected_jp, "Oni")

            try:
                with open(path, 'r', encoding='shift_jis', errors='ignore') as f:
                    content = f.read()

                headers, chart = self.extract_song_data(content, target)

                # ← 選んだコースのBALLOONを、そのまま追加（公式と同じ挙動）
                if headers.get("BALLOON"):
                    balloons = [b.strip() for b in headers["BALLOON"].split(",") if b.strip().isdigit()]
                    all_balloons.extend(balloons)   # 順序・重複そのまま！

                # 手動設定
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
                    "course": target,
                    "level": level,
                    "bpm": headers.get("BPM", ""),
                    "offset": headers.get("OFFSET", "0")
                })

            except Exception as e:
                messagebox.showerror("読み込み失敗", f"{os.path.basename(path)}\n{e}", parent=self.dan_window)
                return

        # BALLOON出力（順序・重複そのまま！）
        if all_balloons:
            code.append(f"BALLOON:{','.join(all_balloons)}\n")

        code.append("\n#START\n")
        forbidden = {"#START", "#END", "#P1START", "#P1END", "#P2START", "#P2END"}

        for i, data in enumerate(song_data):
            parts = [
                data["title"],
                data["subtitle"] or "-",
                data["wave"] or "-",
                data["genre"],
                data["scoreinit"],
                data["scorediff"],
                course_id_map.get(data["course"], "3"),
                data["level"] or "10"
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

            # 譜面
            clean_chart = [line for line in data["chart"] if line.strip().upper() not in forbidden]
            if clean_chart:
                for line in clean_chart:
                    code.append(line + "\n")
            else:
                code.append(",\n")
            
            code.append("\n")
            if i < len(song_data) - 1:
                code.append(",\n")

        code.append("#END\n")

        final_tja = "".join(code)
        if messagebox.askyesno("生成確認", "段位道場TJAを生成しますか？\n\nこの操作は現在のエディタ内容を上書きします。"):
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", final_tja)
            self.root.after_idle(self.update_all)
            messagebox.showinfo("完了", "段位道場TJAを正常に生成しました！")
            if self.dan_window:
                self.dan_window.destroy()

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