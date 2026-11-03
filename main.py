from __future__ import annotations

import hashlib, json, mimetypes, os, re, secrets, sqlite3, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("RQAZ_DB", ROOT / "rqaz.db"))
STATIC = ROOT / "static"

def db():
    con = sqlite3.connect(DB_PATH, timeout=10); con.row_factory = sqlite3.Row; return con

def init_db():
    with db() as con:
        con.executescript("""PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL,email TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,salt TEXT NOT NULL,device_token TEXT NOT NULL UNIQUE,widget_token TEXT NOT NULL UNIQUE,is_pro INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS donations(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,donor TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT 'windows',fingerprint TEXT,created_at INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id),UNIQUE(user_id,fingerprint));
        CREATE INDEX IF NOT EXISTS idx_donations_user_time ON donations(user_id,created_at DESC);""")

def password_hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 210_000).hex()

def public_user(row, include_device=False):
    out={"success":True,"userId":str(row["id"]),"username":row["username"],"isPro":bool(row["is_pro"]),"widgetToken":row["widget_token"]}
    if include_device: out["deviceToken"]=row["device_token"]
    return out

class ApiError(Exception):
    def __init__(self,status,message): self.status=status; self.message=message

class Handler(BaseHTTPRequestHandler):
    server_version="RQAZ-DONATE/0.1"
    def log_message(self,fmt,*args): print(f"[{self.log_date_time_string()}] {fmt % args}")
    def headers_out(self,status,content_type,length=0):
        self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type, Authorization"); self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(length)); self.end_headers()
    def json_out(self,status,value):
        data=json.dumps(value,ensure_ascii=False).encode(); self.headers_out(status,"application/json; charset=utf-8",len(data)); self.wfile.write(data)
    def html_out(self,status,text):
        data=text.encode(); self.headers_out(status,"text/html; charset=utf-8",len(data)); self.wfile.write(data)
    def body(self):
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size>1_000_000: raise ApiError(413,"Слишком большой запрос")
            return json.loads(self.rfile.read(size) or b"{}")
        except (ValueError,json.JSONDecodeError): raise ApiError(400,"Некорректный JSON")
    def device_user(self):
        auth=self.headers.get("Authorization","")
        if not auth.startswith("Bearer "): raise ApiError(401,"Нужен токен программы")
        with db() as con: row=con.execute("SELECT * FROM users WHERE device_token=?",(auth[7:],)).fetchone()
        if not row: raise ApiError(401,"Недействительный токен")
        return row
    def widget_user(self,token):
        with db() as con: row=con.execute("SELECT * FROM users WHERE widget_token=?",(token,)).fetchone()
        if not row: raise ApiError(404,"Виджет не найден")
        return row
    def do_OPTIONS(self): self.headers_out(204,"text/plain",0)
    def do_POST(self):
        try:
            path=urlparse(self.path).path; payload=self.body()
            if path=="/api/register": self.register(payload)
            elif path=="/api/login": self.login(payload)
            elif path=="/api/donations": self.add_donation(payload)
            else: raise ApiError(404,"Маршрут не найден")
        except ApiError as e: self.json_out(e.status,{"success":False,"error":e.message,"detail":e.message})
        except Exception as e: print("Internal error:",repr(e)); self.json_out(500,{"success":False,"error":"Внутренняя ошибка сервера"})
    def register(self,data):
        username=str(data.get("username","")).strip(); email=str(data.get("email","")).strip().lower(); password=str(data.get("password",""))
        if not 2<=len(username)<=40: raise ApiError(400,"Никнейм: от 2 до 40 символов")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email): raise ApiError(400,"Некорректный email")
        if not 6<=len(password)<=128: raise ApiError(400,"Пароль: от 6 до 128 символов")
        salt=secrets.token_hex(16)
        try:
            with db() as con:
                cur=con.execute("INSERT INTO users(username,email,password_hash,salt,device_token,widget_token,created_at) VALUES(?,?,?,?,?,?,?)",(username,email,password_hash(password,salt),salt,secrets.token_urlsafe(32),secrets.token_urlsafe(18),int(time.time())))
                row=con.execute("SELECT * FROM users WHERE id=?",(cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError: raise ApiError(409,"Пользователь с такой почтой уже существует")
        self.json_out(201,public_user(row))
    def login(self,data):
        email=str(data.get("email","")).strip().lower(); password=str(data.get("password",""))
        with db() as con: row=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if not row or not secrets.compare_digest(password_hash(password,row["salt"]),row["password_hash"]): raise ApiError(401,"Неверный email или пароль")
        self.json_out(200,public_user(row,True))
    def add_donation(self,data):
        user=self.device_user(); donor=str(data.get("donor","Зритель")).strip()[:80] or "Зритель"; message=str(data.get("message",""))[:500]; kind=re.sub(r"[^a-z]","",str(data.get("kind","donation")).lower())[:30] or "donation"
        try: amount=int(data.get("amount",0))
        except (ValueError,TypeError): raise ApiError(400,"Некорректная сумма")
        if not 1<=amount<=100_000_000: raise ApiError(400,"Сумма вне допустимого диапазона")
        fingerprint=str(data.get("fingerprint") or hashlib.sha256(f"{donor}|{amount}|{time.time_ns()}".encode()).hexdigest())[:128]
        try:
            with db() as con: cur=con.execute("INSERT INTO donations(user_id,donor,amount,kind,message,fingerprint,created_at) VALUES(?,?,?,?,?,?,?)",(user["id"],donor,amount,kind,message,fingerprint,int(time.time())))
        except sqlite3.IntegrityError: self.json_out(200,{"success":True,"duplicate":True}); return
        self.json_out(201,{"success":True,"id":cur.lastrowid})
    def do_GET(self):
        try:
            parsed=urlparse(self.path); path=parsed.path
            if path=="/api/health": self.json_out(200,{"ok":True,"time":int(time.time())}); return
            m=re.fullmatch(r"/api/widget/([^/]+)/latest",path)
            if m: self.widget_latest(m.group(1),parse_qs(parsed.query)); return
            m=re.fullmatch(r"/w/([^/]+)/([^/]+)",path)
            if m: self.widget_page(m.group(1),m.group(2)); return
            if path=="/": self.serve_file(STATIC/"index.html"); return
            if path.startswith("/static/"):
                candidate=(STATIC/path.removeprefix("/static/")).resolve()
                if STATIC.resolve() not in candidate.parents: raise ApiError(403,"Доступ запрещён")
                self.serve_file(candidate); return
            raise ApiError(404,"Страница не найдена")
        except ApiError as e: self.json_out(e.status,{"success":False,"error":e.message})
        except Exception as e: print("Internal error:",repr(e)); self.json_out(500,{"success":False,"error":"Внутренняя ошибка сервера"})
    def widget_latest(self,token,query):
        user=self.widget_user(token)
        try: after=int(query.get("after",[0])[0])
        except ValueError: after=0
        with db() as con: row=con.execute("SELECT id,donor,amount,kind,message,created_at FROM donations WHERE user_id=? AND id>? ORDER BY id DESC LIMIT 1",(user["id"],after)).fetchone()
        self.json_out(200,{"donation":dict(row) if row else None})
    def widget_page(self,token,kind):
        self.widget_user(token); safe=re.sub(r"[^a-z]","",kind.lower()) or "alerts"; html=(STATIC/"widget.html").read_text(encoding="utf-8"); self.html_out(200,html.replace("__TOKEN__",token).replace("__KIND__",safe))
    def serve_file(self,path):
        if not path.is_file(): raise ApiError(404,"Файл не найден")
        data=path.read_bytes(); content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"): content_type+="; charset=utf-8"
        self.headers_out(200,content_type,len(data)); self.wfile.write(data)

def run():
    init_db(); host=os.getenv("HOST","0.0.0.0"); port=int(os.getenv("PORT","3000")); server=ThreadingHTTPServer((host,port),Handler); print(f"RQAZ-DONATE запущен: http://localhost:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__": run()
