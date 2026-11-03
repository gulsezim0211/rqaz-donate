from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import requests

APP_DIR = Path.home() / ".rqaz-donate"
CONFIG = APP_DIR / "config.json"
AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})*|\d+)\s*(?:₸|тг|KZT)", re.I)
YOUTUBE_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+", re.I)


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {"server": "http://localhost:3000", "email": ""}


def save_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_notification(text: str) -> dict | None:
    if "kaspi" not in text.lower():
        return None
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    amount = int(re.sub(r"\D", "", match.group(1)))
    link = YOUTUBE_RE.search(text)
    kind = "music" if link else "donation"
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    donor = "Зритель"
    for line in lines:
        if "kaspi" not in line.lower() and not AMOUNT_RE.search(line) and len(line) <= 80:
            donor = line
            break
    message = link.group(0) if link else "Оплата через Kaspi"
    fingerprint = hashlib.sha256(text.strip().encode("utf-8", "ignore")).hexdigest()
    return {"donor": donor, "amount": amount, "kind": kind, "message": message, "fingerprint": fingerprint}


def phone_link_texts() -> list[str]:
    try:
        from pywinauto import Desktop

        result = []
        for window in Desktop(backend="uia").windows():
            title = window.window_text().lower()
            if any(name in title for name in ("связь с телефоном", "phone link", "your phone")):
                texts = []
                for node in window.descendants(control_type="Text"):
                    value = node.window_text().strip()
                    if value:
                        texts.append(value)
                if texts:
                    result.append("\n".join(texts))
        return result
    except Exception:
        return []


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RQAZ-DONATE")
        self.geometry("620x560")
        self.minsize(560, 500)
        self.configure(bg="#09050f")
        self.token = ""
        self.stop_event = threading.Event()
        self.sent: set[str] = set()
        self.ui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cfg = load_config()
        self._style()
        self._build()
        self.after(150, self._drain)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#09050f")
        style.configure("Card.TFrame", background="#130b20")
        style.configure("TLabel", background="#09050f", foreground="#f4eeff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="#22f0ff")
        style.configure("Muted.TLabel", foreground="#a592c4")
        style.configure("TEntry", fieldbackground="#1c1030", foreground="#f4eeff", insertcolor="#f4eeff")
        style.configure("TButton", background="#8b5cff", foreground="white", padding=10, font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background="#09050f", foreground="#f4eeff")

    def _build(self) -> None:
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="RQAZ-DONATE", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Windows-клиент · Kaspi → эфир", style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

        form = ttk.Frame(root, style="Card.TFrame", padding=18)
        form.pack(fill="x")
        self.server = self._field(form, "Адрес сервера", self.cfg.get("server", "http://localhost:3000"))
        self.email = self._field(form, "Email", self.cfg.get("email", ""))
        self.password = self._field(form, "Пароль", "", show="•")
        self.login_btn = ttk.Button(form, text="Подключиться", command=self.login)
        self.login_btn.pack(fill="x", pady=(14, 0))

        controls = ttk.Frame(root, padding=(0, 18))
        controls.pack(fill="x")
        self.watch = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Следить за Phone Link", variable=self.watch, command=self.toggle_watch).pack(side="left")
        ttk.Button(controls, text="Тестовый донат 500 ₸", command=self.test_donation).pack(side="right")

        self.status = ttk.Label(root, text="● Не подключено", foreground="#ff5d7a")
        self.status.pack(anchor="w", pady=(0, 10))
        self.log = tk.Text(root, height=13, bg="#130b20", fg="#d8caef", insertbackground="white", relief="flat", padx=12, pady=12)
        self.log.pack(fill="both", expand=True)
        self.write_log("Готово. Введите данные аккаунта сайта.")

    def _field(self, parent: ttk.Frame, label: str, value: str, show: str = "") -> ttk.Entry:
        ttk.Label(parent, text=label, background="#130b20").pack(anchor="w", pady=(6, 4))
        entry = ttk.Entry(parent, show=show)
        entry.insert(0, value)
        entry.pack(fill="x")
        return entry

    def api(self, path: str) -> str:
        return self.server.get().strip().rstrip("/") + path

    def login(self) -> None:
        self.login_btn.config(state="disabled")
        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self) -> None:
        try:
            response = requests.post(self.api("/api/login"), json={"email": self.email.get().strip(), "password": self.password.get()}, timeout=12)
            data = response.json()
            if not response.ok:
                raise RuntimeError(data.get("detail", "Ошибка входа"))
            self.token = data["deviceToken"]
            save_config({"server": self.server.get().strip(), "email": self.email.get().strip()})
            self.ui_queue.put(("connected", f"Подключено: {data['username']} · ID {data['userId']}"))
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))

    def toggle_watch(self) -> None:
        if self.watch.get() and not self.token:
            self.watch.set(False)
            messagebox.showwarning("RQAZ-DONATE", "Сначала подключитесь к аккаунту.")
            return
        if self.watch.get():
            self.stop_event.clear()
            threading.Thread(target=self._watch_worker, daemon=True).start()
            self.write_log("Наблюдение за Phone Link включено.")
        else:
            self.stop_event.set()
            self.write_log("Наблюдение остановлено.")

    def _watch_worker(self) -> None:
        while not self.stop_event.wait(2.0):
            texts = phone_link_texts()
            if not texts:
                self.ui_queue.put(("info", "Окно Phone Link не найдено или в нём нет доступного текста."))
                continue
            for text in texts:
                event = parse_notification(text)
                if event and event["fingerprint"] not in self.sent:
                    self._send(event)

    def test_donation(self) -> None:
        if not self.token:
            messagebox.showwarning("RQAZ-DONATE", "Сначала подключитесь к аккаунту.")
            return
        event = {"donor": "Тестовый зритель", "amount": 500, "kind": "donation", "message": "Проверка связи", "fingerprint": f"test-{time.time_ns()}"}
        threading.Thread(target=self._send, args=(event,), daemon=True).start()

    def _send(self, event: dict) -> None:
        try:
            response = requests.post(self.api("/api/donations"), json=event, headers={"Authorization": f"Bearer {self.token}"}, timeout=10)
            data = response.json()
            if not response.ok:
                raise RuntimeError(data.get("detail", "Ошибка отправки"))
            self.sent.add(event["fingerprint"])
            suffix = " (дубликат)" if data.get("duplicate") else ""
            self.ui_queue.put(("donation", f"{event['donor']} · {event['amount']} ₸{suffix}"))
        except Exception as exc:
            self.ui_queue.put(("error", f"Не удалось отправить донат: {exc}"))

    def _drain(self) -> None:
        try:
            while True:
                kind, text = self.ui_queue.get_nowait()
                if kind == "connected":
                    self.status.config(text="● Программа активна", foreground="#b6ff3b")
                    self.login_btn.config(state="normal")
                elif kind == "error":
                    self.status.config(text="● Ошибка", foreground="#ff5d7a")
                    self.login_btn.config(state="normal")
                self.write_log(text)
        except queue.Empty:
            pass
        self.after(150, self._drain)

    def write_log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{stamp}] {text}\n")
        self.log.see("end")

    def close(self) -> None:
        self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
