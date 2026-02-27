# -*- coding: utf-8 -*-
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque, defaultdict

import ccxt


# -------------------------
# Gate exchange factory
# -------------------------
def make_gate_exchange():
    exchange = None
    last_err = None

    for ex_id in ("gate", "gateio"):
        try:
            ex_class = getattr(ccxt, ex_id)
            exchange = ex_class({
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
            exchange.load_markets()
            return exchange
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Не вдалося ініціалізувати Gate/Gate.io через ccxt. Остання помилка: {last_err}")


# -------------------------
# Time formatting
# -------------------------
def fmt_mm_ss_xx(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    mm = int(seconds // 60)
    ss = int(seconds % 60)
    xx = int((seconds - int(seconds)) * 100)  # соті
    return f"{mm:02d}:{ss:02d}.{xx:02d}"


# -------------------------
# GUI App
# -------------------------
class GateTickTimerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Gate Tick Timer")
        self.geometry("720x520")
        self.minsize(640, 460)
        self.configure(bg="#0b0b0b")

        # --- State ---
        self.exchange = None
        self.worker_thread = None
        self.stop_event = threading.Event()

        self.monitoring = False
        self.timer_running = False

        self.start_perf = None          # perf_counter when first tick received
        self.last_tick_perf = None      # perf_counter of previous tick

        # anti-duplicate cache (останні N тiків)
        self.recent_tick_keys = deque(maxlen=120)
        self.recent_tick_set = set()

        self.interval_items = defaultdict(list)  # interval_key -> [tree_item_ids]

        # UI build
        self._build_styles()
        self._build_layout()

        # timer UI refresh loop
        self.after(30, self._ui_timer_tick)

    # -------------------------
    # Styles
    # -------------------------
    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # базові кольори
        self.COL_BG = "#0b0b0b"
        self.COL_TEXT = "#eaeaea"

        # кнопки
        self.COL_GREEN = "#2ecc71"
        self.COL_RED = "#ff4d4d"

        # підсвітка однакових інтервалів
        self.COL_ORANGE_BG = "#7a3f00"
        self.COL_ORANGE_FG = "#ffffff"

        style.configure("TFrame", background=self.COL_BG)
        style.configure("TLabel", background=self.COL_BG, foreground=self.COL_TEXT)

        style.configure(
            "TEntry",
            fieldbackground="#141414",
            foreground=self.COL_TEXT,
            insertcolor=self.COL_TEXT,
        )

        style.configure(
            "TButton",
            background="#1b1b1b",
            foreground=self.COL_TEXT,
            bordercolor="#2b2b2b",
            focusthickness=0,
            padding=10
        )
        style.map("TButton", background=[("active", "#222222")])

        style.configure(
            "Green.TButton",
            background="#14301f",
            foreground=self.COL_GREEN,
            bordercolor=self.COL_GREEN
        )
        style.map("Green.TButton", background=[("active", "#184026")])

        style.configure(
            "Red.TButton",
            background="#3a0f0f",
            foreground=self.COL_RED,
            bordercolor=self.COL_RED
        )
        style.map("Red.TButton", background=[("active", "#4a1414")])

        style.configure(
            "Treeview",
            background="#0f0f0f",
            fieldbackground="#0f0f0f",
            foreground=self.COL_TEXT,
            bordercolor="#2b2b2b",
            rowheight=26,
            font=("Consolas", 21)
        )
        style.configure(
            "Treeview.Heading",
            background="#151515",
            foreground=self.COL_TEXT,
            relief="flat"
        )
        style.map("Treeview.Heading", background=[("active", "#1a1a1a")])

    # -------------------------
    # Layout
    # -------------------------
    def _build_layout(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=14, pady=14)

        # Top row
        top = ttk.Frame(root)
        top.pack(fill="x")

        ttk.Label(top, text="Пара (token/USDT):").pack(side="left", padx=(0, 8))

        self.symbol_var = tk.StringVar(value="BBLAST/USDT")
        self.symbol_entry = ttk.Entry(top, textvariable=self.symbol_var, width=18)
        self.symbol_entry.pack(side="left")

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(top, textvariable=self.status_var, foreground="#aaaaaa").pack(side="left", padx=14)

        # Timer panel
        timer_panel = tk.Frame(root, bg="#060606", highlightthickness=1, highlightbackground="#2b2b2b")
        timer_panel.pack(fill="both", expand=False, pady=(14, 10))

        self.small_time_var = tk.StringVar(value="00:00.00")
        tk.Label(
            timer_panel,
            textvariable=self.small_time_var,
            bg="#060606",
            fg="#8a8a8a",
            font=("Consolas", 16)
        ).pack(pady=(10, 0))

        self.big_time_var = tk.StringVar(value="00:00.00")
        tk.Label(
            timer_panel,
            textvariable=self.big_time_var,
            bg="#060606",
            fg="#f4f4f4",
            font=("Consolas", 64)
        ).pack(pady=(0, 8))

        # Buttons
        btns = ttk.Frame(timer_panel)
        btns.pack(fill="x", padx=16, pady=(0, 14))

        self.reset_btn = ttk.Button(btns, text="Скинути", command=self.reset_all)
        self.reset_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.start_btn = ttk.Button(btns, text="Старт", style="Green.TButton", command=self.start_monitoring)
        self.start_btn.pack(side="left", fill="x", expand=True)

        self.stop_btn = ttk.Button(btns, text="Стоп", style="Red.TButton", command=self.stop_monitoring, state="disabled")
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(10, 0))

        # Table (ONLY Interval + Side)
        table_frame = tk.Frame(root, bg=self.COL_BG)
        table_frame.pack(fill="both", expand=True)

        cols = ("interval", "side")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")

        self.tree.heading("interval", text="Інтервал")
        self.tree.heading("side", text="Side")

        self.tree.column("interval", width=170, anchor="center")
        self.tree.column("side", width=120, anchor="center")

        self.tree.tag_configure(
            "repeat_interval",
            background=self.COL_ORANGE_BG,
            foreground=self.COL_ORANGE_FG
        )

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # -------------------------
    # Helpers
    # -------------------------
    def _clear_recent_tick_cache(self):
        self.recent_tick_keys.clear()
        self.recent_tick_set.clear()

    def _make_tick_key(self, trade: dict):
        """
        Стабільний ключ для дедуплікації.
        Якщо 'id' є — ок. Якщо нема, беремо комбінацію полів.
        """
        tid = trade.get("id")
        if tid:
            return ("id", tid)

        ts = trade.get("timestamp")
        side = trade.get("side")
        price = trade.get("price")
        amount = trade.get("amount")

        p = round(price, 12) if isinstance(price, (int, float)) else price
        a = round(amount, 12) if isinstance(amount, (int, float)) else amount

        return ("fb", ts, side, p, a)

    def _is_duplicate_tick(self, key) -> bool:
        if key in self.recent_tick_set:
            return True

        self.recent_tick_keys.append(key)
        # rebuild set (простий і надійний спосіб, maxlen малий)
        self.recent_tick_set = set(self.recent_tick_keys)
        return False

    def _interval_key_centiseconds(self, interval_sec: float) -> int:
        # ключ однаковості: соті секунди
        return int(round(interval_sec * 100))

    # -------------------------
    # Actions
    # -------------------------
    def reset_all(self):
        self.stop_monitoring()

        self.timer_running = False
        self.start_perf = None
        self.last_tick_perf = None

        self._clear_recent_tick_cache()
        self.interval_items.clear()

        self.small_time_var.set("00:00.00")
        self.big_time_var.set("00:00.00")
        self.status_var.set("Скинуто")

        for row in self.tree.get_children():
            self.tree.delete(row)

    def start_monitoring(self):
        symbol = self.symbol_var.get().strip().upper()
        if not symbol or "/" not in symbol:
            messagebox.showerror("Помилка", "Вкажи пару у форматі типу CTP/USDT")
            return

        if self.monitoring:
            return

        try:
            if self.exchange is None:
                self.exchange = make_gate_exchange()
        except Exception as e:
            messagebox.showerror("Помилка", str(e))
            return

        if symbol not in self.exchange.markets:
            messagebox.showerror("Помилка", f"Пара {symbol} не знайдена на Gate.")
            return

        # prepare
        self.stop_event.clear()
        self.monitoring = True

        self.timer_running = False
        self.start_perf = None
        self.last_tick_perf = None
        self._clear_recent_tick_cache()
        self.interval_items.clear()

        # clear table
        for row in self.tree.get_children():
            self.tree.delete(row)

        self.status_var.set(f"Моніторинг: {symbol} (очікую перший тік...)")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        # start worker
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(symbol,),
            daemon=True
        )
        self.worker_thread.start()

    def stop_monitoring(self):
        if not self.monitoring and not self.timer_running:
            return

        # stop worker + stop timer
        self.stop_event.set()
        self.monitoring = False
        self.timer_running = False

        self.status_var.set("Зупинено")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    # -------------------------
    # Worker: poll trades
    # -------------------------
    def _worker_loop(self, symbol: str):
        while not self.stop_event.is_set():
            try:
                trades = self.exchange.fetch_trades(symbol, limit=10)
                if trades:
                    # найсвіжіший
                    t = max(trades, key=lambda x: x.get("timestamp") or 0)

                    # only buy/sell
                    side = (t.get("side") or "").lower()
                    if side not in ("buy", "sell"):
                        time.sleep(0.25)
                        continue

                    # dedupe
                    tick_key = self._make_tick_key(t)
                    if self._is_duplicate_tick(tick_key):
                        time.sleep(0.25)
                        continue

                    self.after(0, lambda tr=t: self._handle_tick_ui(tr))

            except Exception as e:
                self.after(0, lambda err=str(e): self.status_var.set(f"Помилка API: {err}"))

            time.sleep(0.25)

    # -------------------------
    # Tick handling (UI thread)
    # -------------------------
    def _handle_tick_ui(self, trade: dict):
        now = time.perf_counter()

        # first tick starts timer
        if not self.timer_running:
            self.timer_running = True
            self.start_perf = now
            self.last_tick_perf = now
            self.status_var.set("Секундомір запущено (перший тік отримано)")
            return

        # lap interval
        interval = now - (self.last_tick_perf or now)
        self.last_tick_perf = now

        side = (trade.get("side") or "").upper()
        interval_str = fmt_mm_ss_xx(interval)

        item_id = self.tree.insert(
            "",
            0,  # insert at top
            values=(interval_str, side)
        )

        # highlight equal intervals
        k = self._interval_key_centiseconds(interval)
        self.interval_items[k].append(item_id)

        if len(self.interval_items[k]) >= 2:
            for iid in self.interval_items[k]:
                self.tree.item(iid, tags=("repeat_interval",))

        # keep table size reasonable
        max_rows = 500
        children = self.tree.get_children()
        if len(children) > max_rows:
            for iid in children[max_rows:]:
                self.tree.delete(iid)

    # -------------------------
    # UI Timer refresh
    # -------------------------
    def _ui_timer_tick(self):
        if self.timer_running and self.start_perf is not None:
            total = time.perf_counter() - self.start_perf
            self.big_time_var.set(fmt_mm_ss_xx(total))

            if self.last_tick_perf is not None:
                since_last = time.perf_counter() - self.last_tick_perf
                self.small_time_var.set(fmt_mm_ss_xx(since_last))

        self.after(30, self._ui_timer_tick)


if __name__ == "__main__":
    app = GateTickTimerApp()
    app.mainloop()