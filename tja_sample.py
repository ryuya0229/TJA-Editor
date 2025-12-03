import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, Toplevel, ttk
from tkinter import font as tkfont
from tkinter import Listbox, Scrollbar, Button, Entry, Label, Frame, LabelFrame, Checkbutton
import numpy as np
import matplotlib.pyplot as plt
import re
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
        self.current_encoding = 'shift_jis'  # ← この行を追加
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
        self.load_config()  # ← この行も追加(設定読み込み)

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
        viewmenu.add_separator()
        viewmenu.add_command(label="太鼓さん次郎のパスを再設定...", command=self.reset_taikojiro_path)
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
        if PYDUB_AVAILABLE:
            toolmenu.add_command(label="OFFSET自動計測(WAV/OGG対応)", command=self.auto_measure_offset_ogg)
            toolmenu.add_command(label="OFFSET自動調節(波形表示+精密調整)", command=self.auto_adjust_offset)
        else:
            toolmenu.add_command(label="OFFSET自動計測(無効・pydub未導入)",
                                 command=lambda: messagebox.showwarning("機能無効", "pydub がインストールされていないため利用できません"))
            toolmenu.add_separator()
        toolmenu.add_command(label="太鼓さん次郎でプレビュー再生 (F5)", command=self.preview_play, accelerator="F5")
        toolmenu.add_command(label="構文エラーチェック", command=self.check_syntax_errors, accelerator="Ctrl+E")
        menubar.add_cascade(label="ツール", menu=toolmenu)
    
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
                    
                    # ← ここが抜けていた！メニュー即時更新
                    self.root.after(100, self.update_recent_menu)
                    
                    # ダークモード適用（前回の修正と併用）
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
            
    def apply_dark_mode(self):
        """ダークモードの見た目を強制的に適用（起動時用）"""
        if self.dark_mode:
            self.toggle_dark_mode(force=True)  # force=True でトグルせずに適用
        else:
            self.toggle_dark_mode(force=False)  # ライトモード確定
        
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
        
    def check_syntax_errors(self):
        """TJAファイルの構文エラーをチェックして表示(//コメント完全除外対応 + カンマ欠落検出)"""
        content = self.text.get("1.0", tk.END).strip()
        
        if not content:
            self.show_syntax_result([], [], set(), is_empty=True)
            return
        
        lines = content.splitlines()
        
        errors = []
        warnings = []
        
        has_title = False
        has_bpm = False
        has_wave = False
        courses = set()
        current_course = None
        chart_started = False
        chart_ended = False
        gogo_stack = 0
        branch_stack = 0
        p1_stack = 0
        p2_stack = 0
        
        header_pattern = re.compile(r"^(\w+):\s*(.+)", re.IGNORECASE)
        course_pattern = re.compile(r"^COURSE:\s*(.+)", re.IGNORECASE)
    
        # ★ 速度変化コマンドのリスト
        speed_commands = ["#BPMCHANGE", "#SCROLL", "#DELAY", "#HBSCROLL"]
    
        # ★ 各行が速度変化コマンドかどうかを事前に判定(空行・コメント行を除外)
        is_speed_command_line = {}  # {行番号: True/False}
        for idx, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            
            # 空行・コメント行はスキップ
            if not stripped or stripped.lstrip().startswith("//"):
                is_speed_command_line[idx] = None  # 判定対象外
                continue
            
            # コメント除去
            clean = re.split(r"//|;", stripped, 1)[0].rstrip()
            if not clean:
                is_speed_command_line[idx] = None
                continue
            
            # 速度変化コマンドかどうか
            upper_clean = clean.upper()
            is_speed = any(upper_clean.startswith(cmd) for cmd in speed_commands)
            is_speed_command_line[idx] = is_speed
    
        for line_num, raw_line in enumerate(lines, 1):
            stripped = raw_line.strip()
            
            # 空行 or 行頭が // で始まる行 → 完全スキップ
            if not stripped or stripped.lstrip().startswith("//"):
                continue
            
            # 行中コメント(// または ;)以降を切り捨てる
            clean_line = re.split(r"//|;", stripped, 1)[0].rstrip()
            if not clean_line:
                continue
    
            # 以降は clean_line で判定
            upper_clean = clean_line.upper()
    
            # ヘッダーチェック
            header_match = header_pattern.match(clean_line)
            if header_match:
                key = header_match.group(1).upper()
                value = header_match.group(2).strip()
                
                if key == "TITLE":
                    has_title = True
                    if not value:
                        errors.append((line_num, "TITLE が空です"))
                
                elif key == "BPM":
                    has_bpm = True
                    try:
                        bpm_val = float(value)
                        if bpm_val <= 0:
                            errors.append((line_num, "BPM は正の数である必要があります"))
                        elif bpm_val > 1000:
                            warnings.append((line_num, f"BPM が異常に高い値です: {bpm_val}"))
                    except ValueError:
                        errors.append((line_num, f"BPM の値が不正です: {value}"))
                
                elif key == "WAVE":
                    has_wave = True
                    if not value:
                        warnings.append((line_num, "WAVE ファイルが指定されていません"))
                
                elif key == "OFFSET":
                    try:
                        offset_val = float(value)
                        if abs(offset_val) > 10:
                            warnings.append((line_num, f"OFFSET の値が大きすぎます: {offset_val}"))
                    except ValueError:
                        errors.append((line_num, f"OFFSET の値が不正です: {value}"))
                
                elif key == "LEVEL":
                    try:
                        level_val = int(value)
                        if level_val < 1 or level_val > 10:
                            warnings.append((line_num, f"LEVEL は通常 1-10 です: {level_val}"))
                    except ValueError:
                        errors.append((line_num, f"LEVEL の値が不正です: {value}"))
                
                elif key == "BALLOON":
                    balloon_values = [v.strip() for v in value.split(",")]
                    for b in balloon_values:
                        if not b.isdigit():
                            errors.append((line_num, f"BALLOON の値が不正です: {b}"))
    
            # COURSEチェック
            course_match = course_pattern.match(clean_line)
            if course_match:
                course_name = course_match.group(1).strip()
                if course_name in ["0", "1", "2", "3", "4"]:
                    course_name = ["Easy", "Normal", "Hard", "Oni", "Edit"][int(course_name)]
                courses.add(course_name)
                current_course = course_name
                chart_started = False
                chart_ended = False
            
            # 譜面コマンドチェック
            if upper_clean.startswith("#START") or upper_clean == "#P1START" or upper_clean == "#P2START":
                if chart_started and not chart_ended:
                    errors.append((line_num, f"{clean_line} が二重に開始されています"))
                chart_started = True
                chart_ended = False
                if upper_clean == "#P1START":
                    p1_stack += 1
                elif upper_clean == "#P2START":
                    p2_stack += 1
            
            elif upper_clean.startswith("#END") or upper_clean == "#P1END" or upper_clean == "#P2END":
                if not chart_started:
                    errors.append((line_num, f"{clean_line} に対応する開始コマンドがありません"))
                chart_ended = True
                chart_started = False
                if upper_clean == "#P1END":
                    p1_stack -= 1
                    if p1_stack < 0:
                        errors.append((line_num, "#P1END が #P1START より多いです"))
                elif upper_clean == "#P2END":
                    p2_stack -= 1
                    if p2_stack < 0:
                        errors.append((line_num, "#P2END が #P2START より多いです"))
            
            elif upper_clean == "#GOGOSTART":
                gogo_stack += 1
                if gogo_stack > 1:
                    warnings.append((line_num, "#GOGOSTART がネストしています"))
            
            elif upper_clean == "#GOGOEND":
                gogo_stack -= 1
                if gogo_stack < 0:
                    errors.append((line_num, "#GOGOEND に対応する #GOGOSTART がありません"))
            
            elif upper_clean.startswith("#BRANCHSTART"):
                branch_stack += 1
            
            elif upper_clean == "#BRANCHEND":
                branch_stack -= 1
                if branch_stack < 0:
                    errors.append((line_num, "#BRANCHEND に対応する #BRANCHSTART がありません"))
            
            elif upper_clean.startswith("#BPMCHANGE"):
                parts = clean_line.split()
                if len(parts) < 2:
                    errors.append((line_num, "#BPMCHANGE に値が指定されていません"))
                else:
                    try:
                        bpm_val = float(parts[1])
                        if bpm_val <= 0:
                            errors.append((line_num, "#BPMCHANGE の値が不正です"))
                    except ValueError:
                        errors.append((line_num, f"#BPMCHANGE の値が不正です: {parts[1]}"))
            
            elif upper_clean.startswith("#MEASURE"):
                parts = clean_line.split()
                if len(parts) < 2:
                    errors.append((line_num, "#MEASURE に値が指定されていません"))
                else:
                    measure_val = parts[1]
                    if "/" not in measure_val:
                        errors.append((line_num, f"#MEASURE の形式が不正です: {measure_val}"))
                    else:
                        try:
                            num, denom = measure_val.split("/")
                            int(num), int(denom)
                        except:
                            errors.append((line_num, f"#MEASURE の値が不正です: {measure_val}"))
            
            # ★ カンマ欠落チェック(譜面データ行のみ)
            elif chart_started and not upper_clean.startswith("#"):
                # 譜面データとして扱うべき行(ノート記号を含む行)
                note_chars = re.findall(r"[0-9ABCDEFGH]", clean_line)
                
                if note_chars:  # ノート記号が1つでもある場合
                    if "," not in raw_line:  # カンマがない
                        # ★ 前後の行をチェック(速度変化コマンドのみ)
                        current_idx = line_num - 1  # 0ベースのインデックス
                        
                        # 前の有効行を探す
                        prev_is_speed_command = False
                        for prev_idx in range(current_idx - 1, -1, -1):
                            if is_speed_command_line.get(prev_idx) is None:  # 空行・コメント行
                                continue
                            if is_speed_command_line.get(prev_idx) is True:  # 速度変化コマンド
                                prev_is_speed_command = True
                            break
                        
                        # 次の有効行を探す
                        next_is_speed_command = False
                        for next_idx in range(current_idx + 1, len(lines)):
                            if is_speed_command_line.get(next_idx) is None:  # 空行・コメント行
                                continue
                            if is_speed_command_line.get(next_idx) is True:  # 速度変化コマンド
                                next_is_speed_command = True
                            break
                        
                        # 前後どちらも速度変化コマンドでない場合のみエラー
                        if not prev_is_speed_command and not next_is_speed_command:
                            errors.append((line_num, "譜面データ行にカンマ(,)がありません"))
                    
                    # カンマはあるが不明な記号がある場合の既存チェック
                    elif "," in raw_line:
                        notes = clean_line.replace(",", "").strip()
                        for char in notes:
                            if char not in "0123456789ABCDEFGH ":
                                warnings.append((line_num, f"不明なノート記号: {char}"))
    
        # 全体チェック
        if not has_title:
            errors.append((0, "TITLE が定義されていません"))
        if not has_bpm:
            errors.append((0, "BPM が定義されていません"))
        if not has_wave:
            warnings.append((0, "WAVE ファイルが指定されていません"))
        if not courses:
            errors.append((0, "COURSE が定義されていません"))
        if gogo_stack != 0:
            errors.append((0, f"#GOGOSTART と #GOGOEND の数が一致しません (差分: {gogo_stack})"))
        if branch_stack != 0:
            errors.append((0, f"#BRANCHSTART と #BRANCHEND の数が一致しません (差分: {branch_stack})"))
        if p1_stack != 0:
            errors.append((0, f"#P1START と #P1END の数が一致しません (差分: {p1_stack})"))
        if p2_stack != 0:
            errors.append((0, f"#P2START と #P2END の数が一致しません (差分: {p2_stack})"))
    
        self.show_syntax_result(errors, warnings, courses, is_empty=False)
            
    def show_syntax_result(self, errors, warnings, courses, is_empty=False):
        """構文チェック結果を表示(クリックで該当行にジャンプ機能付き)"""
        
        # ★ on_syntax_close を最初に定義(スコープエラー対策)
        def on_syntax_close():
            if hasattr(self, 'syntax_window'):
                self.syntax_window = None
            if 'result_window' in locals() and result_window:
                result_window.destroy()
        
        if hasattr(self, 'syntax_window') and self.syntax_window and self.syntax_window.winfo_exists():
            result_window = self.syntax_window
            # ★ ボタンフレーム以外を削除(ボタンは最後に再作成)
            for widget in result_window.winfo_children():
                widget.destroy()
        else:
            result_window = Toplevel(self.root)
            result_window.title("構文チェック結果")
            result_window.geometry("720x600")
            result_window.resizable(True, True)
            result_window.transient(self.root)
            self.syntax_window = result_window
            result_window.protocol("WM_DELETE_WINDOW", on_syntax_close)
    
        # ★ メイン枠(grid使用でボタンを最下部に固定)
        main_frame = Frame(result_window, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ★ gridの行設定(0行目は伸縮、1行目は固定)
        main_frame.grid_rowconfigure(0, weight=1)  # コンテンツ部分は伸縮
        main_frame.grid_rowconfigure(1, weight=0)  # ボタン部分は固定
        main_frame.grid_columnconfigure(0, weight=1)
    
        # ★ コンテンツフレーム(サマリー+詳細)
        content_frame = Frame(main_frame)
        content_frame.grid(row=0, column=0, sticky="nsew")
    
        # サマリー
        summary_frame = LabelFrame(content_frame, text="概要", font=("メイリオ", 11, "bold"), padx=10, pady=10)
        summary_frame.pack(fill=tk.X, pady=(0, 15))
    
        error_count = len(errors)
        warning_count = len(warnings)
    
        if is_empty:
            status_text = "テキストが空です"
            status_color = "#666666"
        elif error_count == 0 and warning_count == 0:
            status_text = "エラーはありません!"
            status_color = "#008800"
        elif error_count > 0:
            status_text = f"エラー: {error_count}件、警告: {warning_count}件"
            status_color = "#cc0000"
        else:
            status_text = f"警告: {warning_count}件"
            status_color = "#ff8800"
    
        Label(summary_frame, text=status_text, font=("メイリオ", 13, "bold"), fg=status_color).pack(anchor="w")
        if courses:
            Label(summary_frame, text="検出されたコース: " + ", ".join(sorted(courses)),
                  font=("メイリオ", 10), fg="#0066cc").pack(anchor="w", pady=(5, 0))
    
        # 詳細
        detail_frame = LabelFrame(content_frame, text="詳細 (クリックで該当行にジャンプ)", font=("メイリオ", 11, "bold"), padx=10, pady=10)
        detail_frame.pack(fill=tk.BOTH, expand=True)
    
        text_scroll = Scrollbar(detail_frame, orient=tk.VERTICAL)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        result_text = tk.Text(detail_frame, font=("Consolas", 10), yscrollcommand=text_scroll.set,
                              wrap=tk.WORD, bg="#f9f9f9", relief="sunken", borderwidth=2, cursor="hand2")
        result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.config(command=result_text.yview)
    
        # タグ設定
        result_text.tag_configure("error", foreground="#cc0000", font=("Consolas", 10, "bold"))
        result_text.tag_configure("warning", foreground="#ff8800", font=("Consolas", 10, "bold"))
        result_text.tag_configure("line", foreground="#0066cc", underline=True)
        result_text.tag_configure("line_hover", foreground="#0099ff", underline=True, background="#e6f3ff")
        result_text.tag_configure("success", foreground="#008800", font=("Consolas", 11, "bold"))
        result_text.tag_configure("empty", foreground="#666666", font=("Consolas", 11))
    
        # ジャンプ機能付きエラー/警告の挿入関数
        def insert_error_line(line_num, msg, tag_prefix):
            if line_num > 0:
                # クリック可能な行番号
                prefix_start = result_text.index(tk.INSERT)
                result_text.insert(tk.END, f"  行 {line_num}: ", tag_prefix)
                prefix_end = result_text.index(tk.INSERT)
                
                # 行番号部分にクリックイベントとタグを追加
                line_tag = f"line_{line_num}_{tag_prefix}"
                result_text.tag_add(line_tag, prefix_start, prefix_end)
                result_text.tag_add("line", prefix_start, prefix_end)
                result_text.tag_bind(line_tag, "<Button-1>", lambda e, ln=line_num: self.jump_to_line(ln))
                result_text.tag_bind(line_tag, "<Enter>", lambda e, s=prefix_start, end=prefix_end: result_text.tag_add("line_hover", s, end))
                result_text.tag_bind(line_tag, "<Leave>", lambda e, s=prefix_start, end=prefix_end: result_text.tag_remove("line_hover", s, end))
                
                result_text.insert(tk.END, msg + "\n")
            else:
                result_text.insert(tk.END, f"  全体: {msg}\n")
    
        if is_empty:
            result_text.insert(tk.END, "テキストが空です\n\nTJAファイルを開くか内容を入力してから構文チェックを実行してください。", "empty")
        else:
            if errors:
                result_text.insert(tk.END, "【エラー】\n", "error")
                for line_num, msg in sorted(errors):
                    insert_error_line(line_num, msg, "error")
                result_text.insert(tk.END, "\n")
    
            if warnings:
                result_text.insert(tk.END, "【警告】\n", "warning")
                for line_num, msg in sorted(warnings):
                    insert_error_line(line_num, msg, "warning")
                result_text.insert(tk.END, "\n")
    
            if error_count == 0 and warning_count == 0:
                result_text.insert(tk.END, "構文エラーは検出されませんでした!\n\nこのTJAファイルは正常に記述されています。", "success")
    
        result_text.config(state=tk.DISABLED)
    
        # ★ ボタンフレーム(gridで最下部に固定配置)
        button_frame = Frame(main_frame, height=50)
        button_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        button_frame.grid_propagate(False)  # サイズ固定
    
        # ★ 更新ボタン - 現在の内容で再チェック
        def refresh_check():
            self.check_syntax_errors()
    
        # ★ ボタン作成
        update_btn = Button(button_frame, text="更新", command=refresh_check,
                           font=("メイリオ", 11), width=12, 
                           bg="#e8f4f8", relief="raised", borderwidth=2)
        update_btn.pack(side=tk.LEFT, padx=5, pady=8, ipady=3)
    
        close_btn = Button(button_frame, text="閉じる", command=on_syntax_close,
                          font=("メイリオ", 11), width=12)
        close_btn.pack(side=tk.LEFT, padx=5, pady=8, ipady=3)
    
        # ★ ウィンドウを最前面に表示して更新を確実に反映
        result_window.update_idletasks()
        result_window.lift()
        result_window.focus_force()
 
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
                    backup_name = f"{os.path.basename(self.current_file)}.{ts}"
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
        self.dan_window.geometry("1100x800")  # ★ 初期サイズを大きく変更
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
        self.comparisons_jp = ["~以上", "~未満"]
        self.comparisons = {"~以上":"m", "~未満":"l"}
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
        if not self.song_settings_frame or not self.song_settings_frame.winfo_exists():
            self.song_settings_frame = LabelFrame(self.count_frame, text="■ 曲設定 ■", font=("メイリオ", 10, "bold"))
            self.song_settings_frame.pack(fill=tk.X, pady=(10, 0))
        
        for widget in self.song_settings_frame.winfo_children():
            widget.destroy()
        self.song_listbox.delete(0, tk.END)
        for i, path in enumerate(self.song_paths):
            self.song_listbox.insert(tk.END, f"{i+1}. {os.path.basename(path)}")
        
        genres = ["ポップス","キッズ","アニメ","ボーカロイド","ゲームミュージック","バラエティ","クラシック","ナムコオリジナル"]
        jp_names = ["かんたん","ふつう","むずかしい","鬼","裏鬼"]
        course_names = ["Easy","Normal","Hard","Oni","Edit"]
        
        # ★ 最大幅を計算するための変数
        max_width_needed = 0
        
        for i in range(len(self.song_paths)):
            path = self.song_paths[i]
            avail = self.song_course_values.get(i, [])
            available_jp = [jp_names[course_names.index(c)] for c in avail if c in course_names]
            
            row = Frame(self.song_settings_frame, pady=4)
            row.pack(fill=tk.X)
            
            Label(row, text=f"曲{i+1}:", font=("MS Gothic", 10, "bold"), width=5).pack(side=tk.LEFT, padx=(5,0))
            
            # ★ ファイル名ラベル(長さに応じて幅を調整)
            filename = os.path.basename(path)
            filename_label = Label(row, text=filename, font=("MS Gothic", 9), fg="gray", anchor="w")
            filename_label.pack(side=tk.LEFT, fill=tk.X, expand=False, padx=(0,15))
            
            current_selection = self.song_courses_temp.get(i, available_jp[0] if available_jp else "鬼")
            cbox = ttk.Combobox(row, values=available_jp, width=9, font=("MS Gothic", 9), state="readonly" if available_jp else "disabled")
            cbox.set(current_selection)
            cbox.pack(side=tk.LEFT, padx=2)
            cbox.bind("<<ComboboxSelected>>", lambda e, idx=i, cb=cbox: self.on_course_changed(idx, cb))
            
            level = self.song_levels.get(i, "?")
            Label(row, text=f"LEVEL: {level}", font=("MS Gothic", 11, "bold"), fg="#0066cc", width=10).pack(side=tk.LEFT, padx=8)
            
            Label(row, text="GENRE:", font=("MS Gothic", 9, "bold"), fg="#008800").pack(side=tk.LEFT, padx=(15,2))
            gbox = ttk.Combobox(row, values=genres, width=14, font=("MS Gothic", 9), state="readonly")
            current_genre = self.song_genres.get(i, "ナムコオリジナル")
            gbox.set(current_genre)
            gbox.pack(side=tk.LEFT, padx=2)
            gbox.bind("<<ComboboxSelected>>", lambda e, idx=i, box=gbox: self.song_genres.__setitem__(idx, box.get()))
            
            Label(row, text="INIT:", font=("MS Gothic", 9, "bold"), fg="#0000ff").pack(side=tk.LEFT, padx=(20,2))
            init_entry = Entry(row, width=7, font=("MS Gothic", 9), justify="center", bg="#f0f8ff")
            init_entry.insert(0, self.song_scoreinit.get(i, ""))
            init_entry.pack(side=tk.LEFT, padx=2)
            init_entry.bind("<KeyRelease>", lambda e, idx=i: self.song_scoreinit.__setitem__(idx, init_entry.get()))
            init_entry.bind("<FocusOut>", lambda e, idx=i: self.song_scoreinit.__setitem__(idx, init_entry.get()))
            
            Label(row, text="DIFF:", font=("MS Gothic", 9, "bold"), fg="#ff4500").pack(side=tk.LEFT, padx=(10,2))
            diff_entry = Entry(row, width=7, font=("MS Gothic", 9), justify="center", bg="#fff0f0")
            diff_entry.insert(0, self.song_scorediff.get(i, ""))
            diff_entry.pack(side=tk.LEFT, padx=2)
            diff_entry.bind("<KeyRelease>", lambda e, idx=i: self.song_scorediff.__setitem__(idx, diff_entry.get()))
            diff_entry.bind("<FocusOut>", lambda e, idx=i: self.song_scorediff.__setitem__(idx, diff_entry.get()))
            
            # ★ この行の実際の幅を計算
            row.update_idletasks()
            row_width = row.winfo_reqwidth()
            if row_width > max_width_needed:
                max_width_needed = row_width
        
        # ★ 段位道場ウィンドウの幅を調整
        if hasattr(self, 'dan_window') and self.dan_window and self.dan_window.winfo_exists():
            self.dan_window.update_idletasks()
            
            # ★ 必要な最小幅を計算(パディング等を考慮)
            required_width = max_width_needed + 100  # マージン追加
            current_width = self.dan_window.winfo_width()
            current_height = self.dan_window.winfo_height()
            
            # ★ 現在の幅より大きい場合のみリサイズ
            if required_width > current_width:
                new_width = min(required_width, 1400)  # 最大幅を制限
                self.dan_window.geometry(f"{new_width}x{current_height}")
            
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