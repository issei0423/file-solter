"""
授業ファイル自動振り分けツール（システムトレイ常駐版）
- 初回起動時に自動でスタートアップ登録
- 起動するとシステムトレイに格納
- 右クリックメニューから設定・監視ON/OFF・終了が可能
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime
import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw
import sys
import winreg

# ===== 設定ファイルパス =====
CONFIG_PATH = Path.home() / ".file_sorter_config.json"

DEFAULT_CONFIG = {
    "watch_folder": str(Path.home() / "Downloads"),
    "rules": [],
    "auto_watch": False,
    "startup_registered": False,
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ===== スタートアップ自動登録 =====
APP_NAME = "FileSorterTray"

def get_exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)

def register_startup():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{get_exe_path()}"')
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"スタートアップ登録失敗: {e}")
        return False

def unregister_startup():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def is_startup_registered():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

# ===== トレイアイコン生成 =====
def create_tray_icon(watching=False):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = "#3db87a" if watching else "#4f8ef7"
    draw.rounded_rectangle([4, 14, 28, 22], radius=3, fill=color)
    draw.rounded_rectangle([4, 20, 60, 54], radius=5, fill=color)
    draw.rounded_rectangle([10, 28, 54, 48], radius=3, fill="#ffffff33")
    if watching:
        draw.ellipse([44, 4, 60, 20], fill="#ff5e5e")
        draw.ellipse([48, 8, 56, 16], fill="#ffffff")
    return img

# ===== ファイル振り分けロジック =====
def match_rule(filename, rule):
    keywords = [kw.strip() for kw in rule["keywords"].split(",") if kw.strip()]
    return any(kw.lower() in filename.lower() for kw in keywords)

def sort_file(filepath, rules, log_callback=None):
    filename = os.path.basename(filepath)
    for rule in rules:
        if match_rule(filename, rule):
            dest_dir = Path(rule["folder"])
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename
            if dest.exists():
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = dest_dir / f"{dest.stem}_{ts}{dest.suffix}"
            shutil.move(str(filepath), str(dest))
            if log_callback:
                log_callback(f"[✓] {filename} → {rule['folder']}")
            return True
    return False

# ===== フォルダ監視スレッド =====
class FolderWatcher(threading.Thread):
    def __init__(self, folder, rules, log_callback):
        super().__init__(daemon=True)
        self.folder = folder
        self.rules = rules
        self.log_callback = log_callback
        self.running = True
        self._seen = set()

    def run(self):
        self.log_callback(f"[監視開始] {self.folder}")
        while self.running:
            try:
                for f in Path(self.folder).iterdir():
                    if f.is_file() and str(f) not in self._seen:
                        self._seen.add(str(f))
                        time.sleep(0.5)
                        sort_file(str(f), self.rules, self.log_callback)
            except Exception as e:
                self.log_callback(f"[エラー] {e}")
            time.sleep(2)

    def stop(self):
        self.running = False
        self.log_callback("[監視停止]")

# ===== メインアプリ =====
class FileSorterApp:
    def __init__(self):
        self.config_data = load_config()
        self.watcher = None
        self.window = None
        self.tray_icon = None
        self.log_lines = []

        self.root = tk.Tk()
        self.root.withdraw()

        # 初回起動時に自動でスタートアップ登録
        if not self.config_data.get("startup_registered", False):
            if register_startup():
                self.config_data["startup_registered"] = True
                save_config(self.config_data)

        self._start_tray()

        if self.config_data.get("auto_watch"):
            self._start_watch()

    def _start_tray(self):
        menu = pystray.Menu(
            Item("⚙️ 設定を開く", self._open_settings),
            Item("▶ 今すぐ振り分け", self._run_now_tray),
            pystray.Menu.SEPARATOR,
            Item(self._watch_label, self._toggle_watch_tray),
            pystray.Menu.SEPARATOR,
            Item(self._startup_label, self._toggle_startup),
            pystray.Menu.SEPARATOR,
            Item("❌ 終了", self._quit),
        )
        self.tray_icon = pystray.Icon(
            "file_sorter", create_tray_icon(), "📂 ファイル振り分けツール", menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _watch_label(self, item):
        return "⏹ 監視を停止" if (self.watcher and self.watcher.running) else "👁 監視を開始"

    def _startup_label(self, item):
        return "✅ 自動起動：登録済み" if is_startup_registered() else "🔲 自動起動：未登録"

    def _toggle_startup(self, icon=None, item=None):
        if is_startup_registered():
            unregister_startup()
            self.config_data["startup_registered"] = False
            self._notify("自動起動", "PC起動時の自動起動を解除しました")
        else:
            if register_startup():
                self.config_data["startup_registered"] = True
                self._notify("自動起動", "PC起動時に自動起動するよう登録しました")
        save_config(self.config_data)

    def _update_tray_icon(self):
        watching = bool(self.watcher and self.watcher.running)
        self.tray_icon.icon = create_tray_icon(watching=watching)
        self.tray_icon.title = "📂 振り分けツール（監視中）" if watching else "📂 ファイル振り分けツール"

    def _open_settings(self, icon=None, item=None):
        self.root.after(0, self._show_settings_window)

    def _show_settings_window(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            return
        self.window = SettingsWindow(self)

    def _run_now_tray(self, icon=None, item=None):
        folder = self.config_data.get("watch_folder", "")
        rules = self.config_data.get("rules", [])
        if not folder or not Path(folder).exists():
            self._notify("エラー", "監視フォルダが存在しません")
            return
        count = sum(1 for f in Path(folder).iterdir()
                    if f.is_file() and sort_file(str(f), rules, self._log))
        self._notify("振り分け完了", f"{count}件のファイルを振り分けました")

    def _toggle_watch_tray(self, icon=None, item=None):
        if self.watcher and self.watcher.running:
            self._stop_watch()
        else:
            self._start_watch()

    def _start_watch(self):
        folder = self.config_data.get("watch_folder", "")
        if not folder or not Path(folder).exists():
            return
        self.watcher = FolderWatcher(folder, self.config_data.get("rules", []), self._log)
        self.watcher.start()
        self._update_tray_icon()
        self._notify("監視開始", f"{Path(folder).name} の監視を開始しました")

    def _stop_watch(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self._update_tray_icon()

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"{ts}  {msg}")
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-200:]
        if self.window and self.window.winfo_exists():
            self.root.after(0, self.window.refresh_log)

    def _notify(self, title, msg):
        try:
            self.tray_icon.notify(msg, title)
        except Exception:
            pass

    def _quit(self, icon=None, item=None):
        self._stop_watch()
        save_config(self.config_data)
        self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ===== 設定ウィンドウ =====
class SettingsWindow(tk.Toplevel):
    def __init__(self, app: FileSorterApp):
        super().__init__(app.root)
        self.app = app
        self.title("📂 ファイル振り分け設定")
        self.geometry("860x660")
        self.configure(bg="#1a1f2e")
        self.resizable(True, True)
        self._build_styles()
        self._build_ui()
        self._refresh_rules()
        self.refresh_log()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.lift()
        self.focus_force()

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#1a1f2e")
        style.configure("Card.TFrame", background="#242938", relief="flat")
        style.configure("TLabel", background="#1a1f2e", foreground="#e0e6f0", font=("Helvetica", 10))
        style.configure("Title.TLabel", background="#1a1f2e", foreground="#7eb8f7", font=("Helvetica", 15, "bold"))
        style.configure("Sub.TLabel", background="#242938", foreground="#a0aec0", font=("Helvetica", 9))
        style.configure("Card.TLabel", background="#242938", foreground="#e0e6f0", font=("Helvetica", 10))
        style.configure("Accent.TButton", background="#4f8ef7", foreground="#ffffff", font=("Helvetica", 10, "bold"), padding=(10, 5), relief="flat")
        style.map("Accent.TButton", background=[("active", "#3a7ae0")])
        style.configure("Danger.TButton", background="#e05c5c", foreground="#ffffff", font=("Helvetica", 9), padding=(6, 4), relief="flat")
        style.map("Danger.TButton", background=[("active", "#c74444")])
        style.configure("Success.TButton", background="#3db87a", foreground="#ffffff", font=("Helvetica", 10, "bold"), padding=(10, 5), relief="flat")
        style.map("Success.TButton", background=[("active", "#2ea066")])
        style.configure("TEntry", fieldbackground="#2d3348", foreground="#e0e6f0", insertcolor="#7eb8f7", relief="flat", padding=5)
        style.configure("Treeview", background="#2d3348", foreground="#e0e6f0", fieldbackground="#2d3348", rowheight=30, font=("Helvetica", 10))
        style.configure("Treeview.Heading", background="#1a1f2e", foreground="#7eb8f7", font=("Helvetica", 10, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#4f8ef7")])
        style.configure("TCheckbutton", background="#242938", foreground="#e0e6f0", font=("Helvetica", 10))

    def _build_ui(self):
        header = tk.Frame(self, bg="#1a1f2e", pady=12)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="📂 授業ファイル振り分けツール",
                 bg="#1a1f2e", fg="#7eb8f7", font=("Helvetica", 17, "bold")).pack(side="left")
        self.status_label = tk.Label(header, text="", bg="#1a1f2e", font=("Helvetica", 10, "bold"))
        self.status_label.pack(side="right", padx=10)
        self._refresh_status()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        self._build_left(main)
        self._build_right(main)
        self._build_log()

    def _refresh_status(self):
        watching = bool(self.app.watcher and self.app.watcher.running)
        self.status_label.config(
            text="● 監視中" if watching else "○ 停止中",
            fg="#3db87a" if watching else "#a0aec0"
        )

    def _build_left(self, parent):
        left = ttk.Frame(parent, style="Card.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=4)

        ttk.Label(left, text="⚙️ ルール設定", style="Title.TLabel").pack(anchor="w", pady=(0, 10))

        ttk.Label(left, text="監視フォルダ", style="Card.TLabel").pack(anchor="w")
        wf = ttk.Frame(left, style="Card.TFrame")
        wf.pack(fill="x", pady=(2, 8))
        self.watch_var = tk.StringVar(value=self.app.config_data.get("watch_folder", ""))
        ttk.Entry(wf, textvariable=self.watch_var).pack(side="left", fill="x", expand=True)
        ttk.Button(wf, text="選択", style="Accent.TButton", command=self._pick_watch).pack(side="left", padx=(4, 0))

        self.auto_var = tk.BooleanVar(value=self.app.config_data.get("auto_watch", False))
        ttk.Checkbutton(left, text="起動時に自動で監視を開始する",
                        variable=self.auto_var, style="TCheckbutton").pack(anchor="w", pady=(0, 4))

        self.startup_label = tk.Label(left, bg="#242938", font=("Helvetica", 9))
        self.startup_label.pack(anchor="w", pady=(0, 8))
        self._refresh_startup_label()

        tk.Frame(left, bg="#3a4060", height=1).pack(fill="x", pady=8)
        ttk.Label(left, text="➕ 新規ルール追加", style="Card.TLabel", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 6))

        ttk.Label(left, text="授業名（ルール名）", style="Sub.TLabel").pack(anchor="w")
        self.rule_name_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.rule_name_var).pack(fill="x", pady=(2, 6))

        ttk.Label(left, text="キーワード（カンマ区切り）", style="Sub.TLabel").pack(anchor="w")
        ttk.Label(left, text="例: 数学,math,Math_", style="Sub.TLabel").pack(anchor="w")
        self.keywords_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.keywords_var).pack(fill="x", pady=(2, 6))

        ttk.Label(left, text="振り分け先フォルダ", style="Sub.TLabel").pack(anchor="w")
        df = ttk.Frame(left, style="Card.TFrame")
        df.pack(fill="x", pady=(2, 8))
        self.dest_var = tk.StringVar()
        ttk.Entry(df, textvariable=self.dest_var).pack(side="left", fill="x", expand=True)
        ttk.Button(df, text="選択", style="Accent.TButton", command=self._pick_dest).pack(side="left", padx=(4, 0))

        ttk.Button(left, text="📁 フォルダを新規作成して設定", style="Success.TButton", command=self._create_folder).pack(fill="x", pady=(2, 4))
        ttk.Button(left, text="✅ ルールを追加", style="Accent.TButton", command=self._add_rule).pack(fill="x", pady=2)

    def _refresh_startup_label(self):
        if is_startup_registered():
            self.startup_label.config(text="✅ PC起動時に自動起動：登録済み", fg="#3db87a")
        else:
            self.startup_label.config(text="🔲 PC起動時に自動起動：未登録", fg="#a0aec0")

    def _build_right(self, parent):
        right = ttk.Frame(parent, style="Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=4)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="📋 ルール一覧", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        cols = ("name", "keywords", "folder")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="授業名")
        self.tree.heading("keywords", text="キーワード")
        self.tree.heading("folder", text="振り分け先")
        self.tree.column("name", width=100, anchor="w")
        self.tree.column("keywords", width=130, anchor="w")
        self.tree.column("folder", width=160, anchor="w")
        self.tree.grid(row=1, column=0, columnspan=2, sticky="nsew")
        sb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=2, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

        ttk.Button(right, text="🗑 選択ルール削除", style="Danger.TButton", command=self._delete_rule).grid(row=2, column=0, sticky="ew", pady=(6, 2))
        ttk.Button(right, text="💾 設定を保存", style="Success.TButton", command=self._save).grid(row=2, column=1, sticky="ew", pady=(6, 2), padx=(4, 0))

        tk.Frame(right, bg="#3a4060", height=1).grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(right, text="▶ 手動実行 / 監視モード", style="Card.TLabel", font=("Helvetica", 10, "bold")).grid(row=4, column=0, columnspan=2, sticky="w")

        btns = ttk.Frame(right, style="Card.TFrame")
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(btns, text="▶ 今すぐ振り分け", style="Accent.TButton", command=self._run_now).pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.watch_btn_text = tk.StringVar()
        self._refresh_watch_btn()
        ttk.Button(btns, textvariable=self.watch_btn_text, style="Success.TButton", command=self._toggle_watch).pack(side="left", expand=True, fill="x", padx=(3, 0))

    def _refresh_watch_btn(self):
        watching = bool(self.app.watcher and self.app.watcher.running)
        self.watch_btn_text.set("⏹ 監視停止" if watching else "👁 監視開始")

    def _build_log(self):
        log_frame = ttk.Frame(self, style="Card.TFrame", padding=10)
        log_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Label(log_frame, text="📝 ログ", style="Card.TLabel", font=("Helvetica", 10, "bold")).pack(anchor="w")
        self.log_box = tk.Text(log_frame, height=5, bg="#1a1f2e", fg="#7eb8f7",
                                font=("Courier", 9), state="disabled", relief="flat")
        self.log_box.pack(fill="x")
        ttk.Button(log_frame, text="ログをクリア", style="Danger.TButton", command=self._clear_log).pack(anchor="e", pady=(4, 0))

    def refresh_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for line in self.app.log_lines[-100:]:
            self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self._refresh_status()
        self._refresh_watch_btn()
        self._refresh_startup_label()

    def _pick_watch(self):
        d = filedialog.askdirectory(title="監視フォルダを選択", parent=self)
        if d:
            self.watch_var.set(d)

    def _pick_dest(self):
        d = filedialog.askdirectory(title="振り分け先フォルダを選択", parent=self)
        if d:
            self.dest_var.set(d)

    def _create_folder(self):
        d = filedialog.askdirectory(title="親フォルダを選択", parent=self)
        if not d:
            return
        name = self.rule_name_var.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "授業名を入力してください", parent=self)
            return
        new_folder = Path(d) / name
        new_folder.mkdir(parents=True, exist_ok=True)
        self.dest_var.set(str(new_folder))
        self.app._log(f"[フォルダ作成] {new_folder}")
        messagebox.showinfo("完了", f"フォルダを作成しました:\n{new_folder}", parent=self)

    def _add_rule(self):
        name = self.rule_name_var.get().strip()
        keywords = self.keywords_var.get().strip()
        folder = self.dest_var.get().strip()
        if not name or not keywords or not folder:
            messagebox.showwarning("入力エラー", "授業名・キーワード・フォルダをすべて入力してください", parent=self)
            return
        self.app.config_data["rules"].append({"name": name, "keywords": keywords, "folder": folder})
        self._refresh_rules()
        self.rule_name_var.set("")
        self.keywords_var.set("")
        self.dest_var.set("")
        self.app._log(f"[ルール追加] {name} / {keywords}")

    def _delete_rule(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        rule = self.app.config_data["rules"][idx]
        if messagebox.askyesno("確認", f"ルール「{rule['name']}」を削除しますか？", parent=self):
            self.app.config_data["rules"].pop(idx)
            self._refresh_rules()
            self.app._log(f"[ルール削除] {rule['name']}")

    def _refresh_rules(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.app.config_data["rules"]:
            self.tree.insert("", "end", values=(r["name"], r["keywords"], r["folder"]))

    def _save(self):
        self.app.config_data["watch_folder"] = self.watch_var.get()
        self.app.config_data["auto_watch"] = self.auto_var.get()
        save_config(self.app.config_data)
        self.app._log("[設定保存] 完了")
        messagebox.showinfo("保存完了", "設定を保存しました", parent=self)

    def _run_now(self):
        folder = self.watch_var.get()
        rules = self.app.config_data["rules"]
        if not folder or not Path(folder).exists():
            messagebox.showwarning("エラー", "監視フォルダが存在しません", parent=self)
            return
        count = sum(1 for f in Path(folder).iterdir()
                    if f.is_file() and sort_file(str(f), rules, self.app._log))
        self.refresh_log()
        messagebox.showinfo("完了", f"{count}件のファイルを振り分けました", parent=self)

    def _toggle_watch(self):
        if self.app.watcher and self.app.watcher.running:
            self.app._stop_watch()
        else:
            self.app.config_data["watch_folder"] = self.watch_var.get()
            self.app._start_watch()
        self._refresh_watch_btn()
        self._refresh_status()

    def _clear_log(self):
        self.app.log_lines.clear()
        self.refresh_log()

    def _on_close(self):
        self.destroy()
        self.app.window = None


if __name__ == "__main__":
    app = FileSorterApp()
    app.run()
