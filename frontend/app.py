import sys
import os
import json
import csv as csv_mod
import re
import smtplib
import ssl
import time
import random
import shutil
import subprocess
import webbrowser
import urllib.request
import imaplib
import sqlite3
import unicodedata
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict
from threading import Thread, Event
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from dotenv import load_dotenv, set_key
import ttkbootstrap as ttk
from tkinter import messagebox, filedialog, simpledialog
import tkinter as tk

# ── Path resolution ──
# Installed: exe lives in Program Files, data goes to %APPDATA%
# Dev: run from repo root, data lives in backend/
if getattr(sys, 'frozen', False):
    ROOT = Path(sys.executable).resolve().parent
    DATA_DIR = Path(os.environ.get("APPDATA", ROOT)) / "SaberMail"
    ENV_PATH = DATA_DIR / ".env"  # AppData so user can write
else:
    ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT / "backend"
    ENV_PATH = ROOT / ".env"
LISTAS_DIR = DATA_DIR / "listas"
TEMPLATES_DIR = DATA_DIR / "templates"
LOGS_DIR = DATA_DIR / "logs"
CHECKPOINTS_DIR = DATA_DIR / "checkpoints"
DB_PATH = DATA_DIR / "simpleship.db"

SSL_DIR = DATA_DIR / "ssl"
for d in [DATA_DIR, LISTAS_DIR, TEMPLATES_DIR, LOGS_DIR, CHECKPOINTS_DIR, SSL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def _ssl_ctx():
    ctx = ssl.create_default_context()
    path = ROOT / "backend" / "ssl" / "gmail-ca-bundle.pem"
    if path.exists():
        ctx.load_verify_locations(str(path))
    ctx.verify_flags = ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx

def _connect_smtp(env, timeout=15):
    port = int(env["SMTP_PORT"])
    if port == 465:
        server = smtplib.SMTP_SSL(env["SMTP_HOST"], port, timeout=timeout, context=_ssl_ctx())
    else:
        server = smtplib.SMTP(env["SMTP_HOST"], port, timeout=timeout)
        server.starttls(context=_ssl_ctx())
    server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
    return server

# ── First-run: copy default files from bundled backend/ to DATA_DIR ──
def _init_defaults():
    bundled = ROOT / "backend"
    if bundled.exists():
        for src in bundled.rglob("*"):
            if src.is_file() and                 src.suffix in (".csv", ".html", ".json", ".md", ".txt", ".example", ".pem", ".png"):
                rel = src.relative_to(bundled)
                dst = DATA_DIR / rel
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
    # Frozen mode: copy .env from exe dir to AppData if needed
    if getattr(sys, 'frozen', False):
        src_env = ROOT / ".env"
        if src_env.exists() and not ENV_PATH.exists():
            ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_env, ENV_PATH)
    # Seed .env if still missing
    if not ENV_PATH.exists():
        dotenv_sample = ROOT / "backend" / ".env.example"
        if dotenv_sample.exists():
            ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dotenv_sample, ENV_PATH)
        else:
            ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
            ENV_PATH.write_text(
                'SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USE_SSL=false\n'
                'SMTP_USERNAME=\nSMTP_PASSWORD=\nFROM_NAME=\nFROM_EMAIL=\nSUBJECT=\n'
                'TEMPLATE_PATH=\nREPLY_TO=\nRATE_PER_MIN=12\n'
                'IMAP_HOST=imap.gmail.com\nIMAP_PORT=993\nIMAP_USE_SSL=true\n'
                'IMAP_USERNAME=\nIMAP_PASSWORD=\n'
                'BOUNCE_METHOD=imap\nBOUNCE_API_KEY=\nBOUNCE_API_URL=\n'
                'PROVIDER=\n',
                encoding="utf-8"
            )

_init_defaults()
def load_env():
    load_dotenv(ENV_PATH)
    env = {
        "SMTP_HOST": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": os.getenv("SMTP_PORT", "587"),
        "SMTP_USE_SSL": os.getenv("SMTP_USE_SSL", "false"),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
        "IAM_USERNAME": os.getenv("IAM_USERNAME", ""),
        "FROM_NAME": os.getenv("FROM_NAME", ""),
        "FROM_EMAIL": os.getenv("FROM_EMAIL", ""),
        "SUBJECT": os.getenv("SUBJECT", ""),
        "TEMPLATE_PATH": os.getenv("TEMPLATE_PATH", ""),
        "REPLY_TO": os.getenv("REPLY_TO", ""),
        "RATE_PER_MIN": os.getenv("RATE_PER_MIN", ""),
        "IMAP_HOST": os.getenv("IMAP_HOST", "imap.gmail.com"),
        "IMAP_PORT": os.getenv("IMAP_PORT", "993"),
        "IMAP_USE_SSL": os.getenv("IMAP_USE_SSL", "true"),
        "IMAP_USERNAME": os.getenv("IMAP_USERNAME", ""),
        "IMAP_PASSWORD": os.getenv("IMAP_PASSWORD", ""),
        "BOUNCE_METHOD": os.getenv("BOUNCE_METHOD", "imap"),
        "BOUNCE_API_KEY": os.getenv("BOUNCE_API_KEY", ""),
        "BOUNCE_API_URL": os.getenv("BOUNCE_API_URL", ""),
        "PROVIDER": os.getenv("PROVIDER", ""),
    }
    try:
        db_cfg = load_config()
        db_cfg = {k: v for k, v in db_cfg.items() if v}
        env.update(db_cfg)
    except Exception:
        pass
    return env


def save_env(env_dict):
    save_config(env_dict)


def load_config():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT key, value FROM config").fetchall()
        conn.close()
        return {k: v for k, v in rows}
    except Exception:
        return {}


def save_config(config_dict):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        for k, v in config_dict.items():
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro salvando config: {e}")


def _ascii_name(s):
    nfkd = unicodedata.normalize("NFKD", s)
    plain = "".join(c for c in nfkd if not unicodedata.combining(c))
    return plain.encode("ascii", errors="replace").decode("ascii")


# ── SQLite database ──
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            subject TEXT DEFAULT '',
            csv_file TEXT DEFAULT '',
            template TEXT DEFAULT '',
            status TEXT DEFAULT 'concluido',
            total INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            bounced INTEGER DEFAULT 0,
            skipped_bounce INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            timestamp TEXT NOT NULL,
            bounce_detected INTEGER DEFAULT 0,
            bounce_type TEXT,
            bounce_time TEXT,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );
        CREATE TABLE IF NOT EXISTS bounces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            email TEXT NOT NULL,
            type TEXT NOT NULL,
            source TEXT DEFAULT 'imap',
            detected_at TEXT NOT NULL,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def save_campaign(start_time, subject, csv_file, template, status,
                  total, sent, failed, bounced, skipped_bounce, sends_list):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""INSERT INTO campaigns
        (start_time,subject,csv_file,template,status,total,sent,failed,bounced,skipped_bounce)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (start_time, subject, csv_file, template, status,
         total, sent, failed, bounced, skipped_bounce))
    cid = cur.lastrowid
    for s in sends_list:
        cur.execute("""INSERT INTO sends
            (campaign_id,email,status,error,timestamp,bounce_detected,bounce_type,bounce_time)
            VALUES (?,?,?,?,?,?,?,?)""",
            (cid, s.get("email",""), s.get("status",""),
             s.get("error"), s.get("timestamp",""),
             1 if s.get("bounce_detectado") else 0,
             s.get("bounce_tipo"), s.get("bounce_data")))
    conn.commit()
    conn.close()

def get_campaigns():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM campaigns ORDER BY start_time DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sends(campaign_id):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sends WHERE campaign_id=? ORDER BY timestamp", (campaign_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_bounce(campaign_id, email, btype, source):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO bounces (campaign_id,email,type,source,detected_at) VALUES (?,?,?,?,?)",
                 (campaign_id, email, btype, source, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_bounces():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM bounces ORDER BY detected_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def migrate_json_logs():
    conn = sqlite3.connect(str(DB_PATH))
    existing = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    if existing > 0:
        conn.close()
        return 0
    count = 0
    for f in sorted(LOGS_DIR.glob("campanha_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        envios = d.get("envios", [])
        # old format (before ReportsTab) may lack metadata
        subject = d.get("assunto") or ""
        csv_file = d.get("arquivo_csv") or ""
        template = d.get("template") or ""
        status = d.get("status", "concluido")
        total_bounced = d.get("bounces_detectados", sum(1 for e in envios if e.get("bounce_detectado")))
        skipped = d.get("pulados_bounce", 0)
        total = d.get("total_emails", len(envios))
        sent = d.get("sucessos", sum(1 for e in envios if e.get("status") == "sucesso"))
        failed = d.get("falhas", sum(1 for e in envios if e.get("status") == "falha"))
        start = d.get("data_inicio", "")
        # If no data_inicio, try to get from filename
        if not start and not subject:
            from datetime import datetime as dt2
            try:
                ts = f.stem.replace("campanha_", "")
                start = dt2.strptime(ts, "%Y%m%d_%H%M%S").isoformat()
            except Exception:
                start = datetime.now().isoformat()
        cur = conn.cursor()
        cur.execute("""INSERT INTO campaigns
            (start_time,subject,csv_file,template,status,total,sent,failed,bounced,skipped_bounce)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (start, subject, csv_file, template, status,
             total, sent, failed, total_bounced, skipped))
        cid = cur.lastrowid
        for e in envios:
            cur.execute("""INSERT INTO sends
                (campaign_id,email,status,error,timestamp,bounce_detected,bounce_type,bounce_time)
                VALUES (?,?,?,?,?,?,?,?)""",
                (cid, e.get("email",""), e.get("status",""),
                 e.get("erro"), e.get("timestamp",""),
                 1 if e.get("bounce_detectado") else 0,
                 e.get("bounce_tipo"), e.get("bounce_data")))
        # Also migrate any existing bounces from old JSON
        bounce_report = LOGS_DIR / f"bounce_report_{f.stem.replace('campanha_','')}.json"
        if bounce_report.exists():
            try:
                br = json.loads(bounce_report.read_text(encoding="utf-8"))
                for email, info in br.items():
                    conn.execute("INSERT INTO bounces (campaign_id,email,type,source,detected_at) VALUES (?,?,?,?,?)",
                                 (cid, email, info.get("tipo","unknown"), "imap", info.get("data","")))
            except Exception:
                pass
        count += 1
    conn.commit()
    conn.close()
    return count

init_db()
migrated = migrate_json_logs()
if migrated:
    print(f"SQLite: {migrated} campanhas importadas do JSON.")


# ── Dashboard Tab ──
class DashboardTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(padding=16)
        self._build()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Dashboard",
                  font=("Segoe UI", 18, "bold"), bootstyle="primary").pack(side="left")
        btn = tk.Label(header, text="↻ Atualizar",
                       fg="#0d6efd", font=("Segoe UI", 9, "bold"),
                       padx=10, pady=4, cursor="hand2")
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda e: self._refresh())

        self.cards_frame = ttk.Frame(self)
        self.cards_frame.pack(fill="x", pady=(0, 16))

        tree_frame = ttk.LabelFrame(self, text="Últimas campanhas", )
        tree_frame.pack(fill="both", expand=True)
        tree_frame.pack(fill="both", expand=True)
        cols = ("Arquivo", "Data", "Enviados", "Falhas", "Bounces")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=100 if c != "Arquivo" else 250)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self._refresh()

    def _card(self, parent, title, value, color, row, col):
        for i in range(4):
            parent.grid_columnconfigure(i, weight=1)
        card = tk.Frame(parent, bg="#ffffff", padx=16, pady=14,
                        highlightbackground="#d0dce8", highlightcolor="#d0dce8", highlightthickness=1)
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        tk.Label(card, text=title, bg="#ffffff", fg="#4a6a8a",
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(card, text=str(value), bg="#ffffff", fg=color,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w")

    def _refresh(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        for item in self.tree.get_children():
            self.tree.delete(item)

        hoje = date.today()
        camp_hoje = 0
        total_env = 0
        total_bounces = 0
        rows = []

        campaigns = get_campaigns()
        for d in campaigns[:20]:
            ds = d.get("start_time", "")[:10]
            ok = d.get("sent", 0)
            falha = d.get("failed", 0)
            bounce = d.get("bounced", 0)
            total_env += ok
            total_bounces += bounce
            try:
                if date.fromisoformat(ds) == hoje:
                    camp_hoje += 1
            except Exception:
                pass
            display_name = d.get("csv_file") or f"campanha_{d['id']}"
            rows.append((display_name, ds, ok, falha, bounce))

        checkpoint_exists = (CHECKPOINTS_DIR / "campanha_atual.json").exists()

        self._card(self.cards_frame, "Campanhas hoje", camp_hoje, "#0d6efd", 0, 0)
        self._card(self.cards_frame, "Total enviados", total_env, "#198754", 0, 1)
        self._card(self.cards_frame, "Bounces", total_bounces, "#dc3545", 0, 2)
        status_cor = "#ffc107" if checkpoint_exists else "#4a6a8a"
        status_txt = "Em andamento" if checkpoint_exists else "Inativo"
        self._card(self.cards_frame, "Campanha", status_txt, status_cor, 0, 3)

        for row in rows:
            self.tree.insert("", "end", values=row)


# ── Campaign Tab ──
class CampaignTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._running = False
        self._stop = Event()
        self._paused = Event()
        self._contatos = []
        self._server = None
        self._bounced_set = set()
        self._envios_log = []
        self._build()

    def _build(self):
        # ── Configuração (CSV + Template) ──
        cfg = ttk.LabelFrame(self, text="Configuração")
        cfg.pack(fill="x", pady=3)
        cfg.columnconfigure(0, weight=1)

        ttk.Label(cfg, text="Arquivo CSV:", font=("Segoe UI", 9, "bold"), bootstyle="primary").grid(row=0, column=0, sticky="w", pady=(0, 2))
        row_csv = ttk.Frame(cfg)
        row_csv.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        row_csv.columnconfigure(0, weight=1)
        self.csv_var = tk.StringVar()
        self.csv_combo = ttk.Combobox(row_csv, textvariable=self.csv_var, state="readonly")
        self.csv_combo.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(row_csv, text="📂 Upload CSV", command=self._upload_csv, bootstyle="primary").grid(row=0, column=1, padx=1)
        ttk.Button(row_csv, text="🔄", command=self._refresh_csv, width=3, bootstyle="info").grid(row=0, column=2, padx=1)

        ttk.Label(cfg, text="Template HTML:", font=("Segoe UI", 9, "bold"), bootstyle="primary").grid(row=2, column=0, sticky="w", pady=(0, 2))
        row_tpl = ttk.Frame(cfg)
        row_tpl.grid(row=3, column=0, sticky="ew")
        row_tpl.columnconfigure(0, weight=1)
        self.tpl_var = tk.StringVar()
        self.tpl_combo = ttk.Combobox(row_tpl, textvariable=self.tpl_var, state="readonly")
        self.tpl_combo.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(row_tpl, text="📂 Upload Template", command=self._upload_template, bootstyle="primary").grid(row=0, column=1, padx=1)
        ttk.Button(row_tpl, text="🔄", command=self._refresh_tpl, width=3, bootstyle="info").grid(row=0, column=2, padx=1)

        # ── Opções de Envio ──
        opts = ttk.LabelFrame(self, text="Opções de Envio")
        opts.pack(fill="x", pady=3)
        opts.columnconfigure(1, weight=1)

        ttk.Label(opts, text="Assunto:", bootstyle="primary").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.subject_var = tk.StringVar()
        ttk.Entry(opts, textvariable=self.subject_var).grid(row=0, column=1, sticky="ew", pady=2)

        rate_frame = ttk.Frame(opts)
        rate_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(rate_frame, text="Taxa de envio:", bootstyle="primary").pack(side="left")
        self.rate_var = tk.StringVar()
        ttk.Entry(rate_frame, textvariable=self.rate_var, width=6).pack(side="left", padx=5)
        ttk.Label(rate_frame, text="e-mails/minuto", bootstyle="secondary").pack(side="left")
        self.auto_bounce_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rate_frame, text="Monitorar bounces (IMAP)", variable=self.auto_bounce_var, bootstyle="primary").pack(side="left", padx=(15, 0))

        test_frame = ttk.Frame(opts)
        test_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(test_frame, text="Teste:", bootstyle="primary").pack(side="left")
        self.test_email_var = tk.StringVar()
        ttk.Entry(test_frame, textvariable=self.test_email_var, width=30).pack(side="left", padx=5)
        ttk.Button(test_frame, text="📧 Enviar teste", command=self._send_test, bootstyle="info").pack(side="left")

        # ── Progresso (resumo + barra + status) ──
        prog = ttk.LabelFrame(self, text="Progresso", )
        prog.pack(fill="x", pady=3)

        self.summary_var = tk.StringVar(value="Nenhum CSV selecionado.")
        ttk.Label(prog, textvariable=self.summary_var, bootstyle="secondary").pack(anchor="w")

        self.progress = ttk.Progressbar(prog, mode="determinate", bootstyle="primary")
        self.progress.pack(fill="x", pady=4)
        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(prog, textvariable=self.status_var, bootstyle="secondary").pack(anchor="w")

        # ── Controles ──
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=3)
        self.btn_start = ttk.Button(btn_row, text="▶ Iniciar", command=self._start, bootstyle="success")
        self.btn_start.pack(side="left", padx=2)
        self.btn_pause = ttk.Button(btn_row, text="⏸ Pausar", command=self._pause, state="disabled", bootstyle="warning")
        self.btn_pause.pack(side="left", padx=2)
        self.btn_resume = ttk.Button(btn_row, text="▶ Continuar", command=self._resume, state="disabled", bootstyle="success")
        self.btn_resume.pack(side="left", padx=2)
        self.btn_cancel = ttk.Button(btn_row, text="⏹ Cancelar", command=self._cancel, state="disabled", bootstyle="danger")
        self.btn_cancel.pack(side="left", padx=2)

        # ── Log ──
        ttk.Label(self, text="Log:", font=("Segoe UI", 9, "bold"), bootstyle="primary").pack(anchor="w")
        self.log = tk.Text(self, height=8, wrap="word", state="disabled",
                            font=("Consolas", 9), bg="#ffffff", fg="#111827",
                            relief="flat", borderwidth=0, padx=4, pady=4)
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(self.log, orient="vertical", command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)

        self._refresh_csv()
        self._refresh_tpl()
        self._log("Pronto.\n")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_csv(self):
        files = sorted(f.name for f in LISTAS_DIR.glob("*.csv"))
        self.csv_combo["values"] = files
        if files and not self.csv_var.get():
            self.csv_combo.set(files[0])
            self._show_summary()

    def _refresh_tpl(self):
        files = sorted(f.name for f in TEMPLATES_DIR.glob("*.html"))
        self.tpl_combo["values"] = files
        if files and not self.tpl_var.get():
            self.tpl_combo.set(files[0])

    def _upload_csv(self):
        path = filedialog.askopenfilename(
            title="Selecionar CSV",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")]
        )
        if path:
            dst = LISTAS_DIR / Path(path).name
            shutil.copy2(path, dst)
            self._refresh_csv()
            self.csv_combo.set(dst.name)
            self._log(f"✅ CSV importado: {dst.name}\n")

    def _upload_template(self):
        path = filedialog.askopenfilename(
            title="Selecionar HTML",
            filetypes=[("HTML", "*.html"), ("All", "*.*")]
        )
        if path:
            dst = TEMPLATES_DIR / Path(path).name
            shutil.copy2(path, dst)
            self._refresh_tpl()
            self.tpl_combo.set(dst.name)
            self._log(f"✅ Template importado: {dst.name}\n")

    def _show_summary(self):
        csv_name = self.csv_var.get()
        if not csv_name:
            self.summary_var.set("Nenhum CSV selecionado.")
            return
        path = LISTAS_DIR / csv_name
        if not path.exists():
            self.summary_var.set("Arquivo não encontrado.")
            return
        with open(path, "r", encoding="utf-8") as f:
            header = f.readline()
            f.seek(0)
            delim = ";" if ";" in header else ","
            reader = csv_mod.DictReader(f, delimiter=delim)
            rows = list(reader)
        lines = [f"Total: {len(rows)} contatos"]
        for i, r in enumerate(rows[:5], 1):
            nome = (r.get("Razao Social") or r.get("nome_empresa") or r.get("Nome") or "")[:35]
            email = (r.get("Email") or r.get("email") or "")[:40]
            lines.append(f"  {i}. {nome} — {email}")
        if len(rows) > 5:
            lines.append(f"  ... e mais {len(rows)-5}")
        self.summary_var.set("\n".join(lines))
        self.csv_combo.bind("<<ComboboxSelected>>", lambda e: self._show_summary())

    def _load_contatos(self, csv_name):
        path = LISTAS_DIR / csv_name
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            h = f.readline()
            f.seek(0)
            delim = ";" if ";" in h else ","
            reader = csv_mod.DictReader(f, delimiter=delim)
            cols = reader.fieldnames or []
            ce = None
            for c in cols:
                if "email" in c.lower():
                    ce = c
                    break
            if not ce:
                return []
            return [
                {"email": row[ce].strip().lower(), "raw": dict(row)}
                for row in reader
                if row.get(ce, "").strip() and "@" in row[ce]
            ]

    def _check_bounces_imap(self, env):
        if not self.auto_bounce_var.get():
            return set()
        user = env.get("IMAP_USERNAME") or env.get("SMTP_USERNAME", "")
        pwd = env.get("IMAP_PASSWORD") or env.get("SMTP_PASSWORD", "")
        imap_host = env.get("IMAP_HOST", "imap.gmail.com")
        imap_port = int(env.get("IMAP_PORT", "993"))
        imap_ssl = env.get("IMAP_USE_SSL", "true").lower() == "true"
        if not user or not pwd:
            return set()
        try:
            if imap_ssl:
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)

            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=15)
                mail.starttls(ssl_context=_ssl_ctx())
            mail.login(user, pwd)
            mail.select("INBOX")
            status, ids = mail.search(None, "UNSEEN")
            bounced = set()
            if status == "OK" and ids[0]:
                import email as email_lib
                for eid in ids[0].split():
                    s, data = mail.fetch(eid, "(RFC822)")
                    if s != "OK":
                        continue
                    for part in data:
                        if not isinstance(part, tuple):
                            continue
                        msg = email_lib.message_from_bytes(part[1])
                        corpo = ""
                        if msg.is_multipart():
                            for mp in msg.walk():
                                if mp.get_content_type() in ("text/plain", "text/html"):
                                    try:
                                        corpo += mp.get_payload(decode=True).decode("utf-8", errors="replace")
                                    except Exception:
                                        pass
                        else:
                            try:
                                corpo += msg.get_payload(decode=True).decode("utf-8", errors="replace")
                            except Exception:
                                corpo = str(msg.get_payload())
                    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', corpo.lower())
                    for f_email in found:
                        if user.lower() not in f_email:
                            mail.store(eid, "+FLAGS", "\\Seen")
                            tipo = "hard" if any(x in corpo.lower() for x in
                                                  ["550", "user unknown", "no such user", "invalid",
                                                   "mailbox not found", "rejected", "blocked", "spam",
                                                   "does not exist"]) else "soft"
                            try:
                                save_bounce(None, f_email, tipo, "imap")
                            except Exception:
                                pass
                            bounced.add(f_email)
                            break
            mail.close()
            mail.logout()
            return bounced
        except Exception:
            return set()

    def _start(self):
        if self._running:
            return
        csv_name = self.csv_var.get()
        if not csv_name:
            messagebox.showwarning("Aviso", "Selecione um CSV.")
            return
        tpl_name = self.tpl_var.get()
        if not tpl_name:
            messagebox.showwarning("Aviso", "Selecione um template.")
            return

        env = load_env()
        if not env["SMTP_USERNAME"] or not env["SMTP_PASSWORD"]:
            messagebox.showwarning("Aviso", "Configure o SMTP na aba Config SMTP primeiro.")
            return

        self._contatos = self._load_contatos(csv_name)
        if not self._contatos:
            messagebox.showerror("Erro", "Nenhum contato válido no CSV.")
            return

        self._stop.clear()
        self._paused.clear()
        self._running = True
        self._toggle_buttons(True)
        self.progress["maximum"] = len(self._contatos)
        self.progress["value"] = 0
        Thread(target=self._run, args=(tpl_name, env), daemon=True).start()

    def _run(self, tpl_name, env):
        tpl_path = TEMPLATES_DIR / tpl_name
        try:
            html_base = tpl_path.read_text(encoding="utf-8")
        except Exception as e:
            self.after(0, self._log, f"[ERRO] Ler template: {e}\n")
            self.after(0, self._finish)
            return

        try:
            self._server = _connect_smtp(env, timeout=30)
            self.after(0, self._log, "✅ Conectado ao SMTP.\n")
        except Exception as e:
            self.after(0, self._log, f"[ERRO SMTP] {e}\n")
            self.after(0, self._finish)
            return

        subject = self.subject_var.get() or env.get("SUBJECT", "")
        from_name = env.get("FROM_NAME", "")
        reply_to = env.get("REPLY_TO", "")
        rate_str = self.rate_var.get() or env.get("RATE_PER_MIN", "")
        delay = 60.0 / float(rate_str) if rate_str and float(rate_str) > 0 else random.uniform(2, 5)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOGS_DIR / f"campanha_{ts}.json"
        enviados = 0
        falhas = []
        self._bounced_set = set()
        self._envios_log = []
        total = len(self._contatos)
        bounce_check_interval = 10

        self.after(0, self._log,
                   f"{'🤖 Monitoramento IMAP ativo.' if self.auto_bounce_var.get() else '📭 Monitoramento IMAP desligado.'}\n")

        data_inicio = datetime.now().isoformat()
        csv_name = self.csv_var.get()

        for i, c in enumerate(self._contatos):
            if self._stop.is_set():
                self.after(0, self._log, "⏹ Cancelado.\n")
                break
            while self._paused.is_set() and not self._stop.is_set():
                time.sleep(1)
            if self._stop.is_set():
                break

            email = c["email"]

            # Auto-bounce check at first email and every N emails
            if self.auto_bounce_var.get() and (i == 0 or i % bounce_check_interval == 0):
                found = self._check_bounces_imap(env)
                new_bounces = found - self._bounced_set
                if new_bounces:
                    self._bounced_set |= new_bounces
                    self.after(0, self._log, f"📬 Bounces detectados: {', '.join(sorted(new_bounces)[:5])}"
                               f"{'...' if len(new_bounces) > 5 else ''}\n")

            # Skip if email already bounced
            if email.lower() in self._bounced_set:
                self.after(0, self._log, f"[{i+1}/{total}] ⏭ {email} — bounce prévio, pulando.\n")
                self.after(0, self._set_progress, i + 1)
                continue

            try:
                html = html_base
                for k, v in c["raw"].items():
                    html = html.replace("{{" + k.upper() + "}}", str(v) if v else "")
                    html = html.replace("{{" + k + "}}", str(v) if v else "")
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                from_email = env.get("FROM_EMAIL") or env["SMTP_USERNAME"]
                msg["From"] = f"{_ascii_name(from_name)} <{from_email}>"
                msg["To"] = email
                if reply_to:
                    msg["Reply-To"] = reply_to
                msg.attach(MIMEText(html, "html", "utf-8"))
                self._server.sendmail(from_email, email, msg.as_string())
                enviados += 1
                self._envios_log.append({
                    "email": email, "status": "sucesso", "erro": None,
                    "timestamp": datetime.now().isoformat()
                })
                self.after(0, self._log, f"[{i+1}/{total}] ✅ {email}\n")
            except Exception as e:
                falhas.append({"email": email, "erro": str(e)})
                self._envios_log.append({
                    "email": email, "status": "falha", "erro": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                self.after(0, self._log, f"[{i+1}/{total}] ❌ {email} — {e}\n")

            self.after(0, self._set_progress, i + 1)
            if i < total - 1:
                time.sleep(delay if isinstance(delay, (int, float)) else random.uniform(2, 5))

        # Final bounce sweep after sending
        if self.auto_bounce_var.get() and enviados > 0:
            self.after(0, self._log, "🔍 Verificando bounces pós-envio...\n")
            found = self._check_bounces_imap(env)
            new_bounces = found - self._bounced_set
            if new_bounces:
                self._bounced_set |= new_bounces
                self.after(0, self._log, f"📬 Bounces pós-envio: {', '.join(sorted(new_bounces)[:5])}"
                           f"{'...' if len(new_bounces) > 5 else ''}\n")
                # Annotate log entries for bounced emails
                for entry in self._envios_log:
                    if entry["email"].lower() in self._bounced_set and entry["status"] == "sucesso":
                        entry["bounce_detectado"] = True
                        entry["bounce_tipo"] = "hard"
                        entry["bounce_data"] = datetime.now().isoformat()

        if self._server:
            try:
                self._server.quit()
            except Exception:
                pass
        self._server = None

        total_bounced = sum(1 for e in self._envios_log if e.get("bounce_detectado"))
        status = "cancelado" if self._stop.is_set() else "concluido"
        # Also save JSON as backup
        log_data = {
            "data_inicio": data_inicio,
            "assunto": subject,
            "arquivo_csv": csv_name,
            "template": tpl_name,
            "status": status,
            "total_emails": enviados + len(falhas),
            "sucessos": enviados,
            "falhas": len(falhas),
            "bounces_detectados": total_bounced,
            "pulados_bounce": len(self._bounced_set),
            "envios": self._envios_log,
        }
        try:
            log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        # Save to SQLite
        try:
            save_campaign(data_inicio, subject, csv_name, tpl_name, status,
                          enviados + len(falhas), enviados, len(falhas),
                          total_bounced, len(self._bounced_set), self._envios_log)
        except Exception:
            pass

        # Save clean CSV (without bounced emails)
        if self._bounced_set and csv_name:
            try:
                src_path = LISTAS_DIR / csv_name
                clean_name = f"clean_{csv_name}"
                clean_path = LISTAS_DIR / clean_name
                with open(src_path, "r", encoding="utf-8") as f:
                    h = f.readline()
                    f.seek(0)
                    delim = ";" if ";" in h else ","
                    reader = csv_mod.DictReader(f, delimiter=delim)
                    cols = reader.fieldnames
                    clean_rows = [
                        row for row in reader
                        if (row.get("Email") or row.get("email") or "").strip().lower() not in self._bounced_set
                    ]
                with open(clean_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv_mod.DictWriter(f, fieldnames=cols, delimiter=delim)
                    writer.writeheader()
                    writer.writerows(clean_rows)
                self.after(0, self._log, f"🧹 Lista limpa salva: {clean_name} ({len(clean_rows)} contatos)\n")
            except Exception:
                pass

        self.after(0, self._log, f"\n=== FIM === Enviados: {enviados}  Falhas: {len(falhas)}  Bounces: {total_bounced}\n")
        self.after(0, self._finish)

    def _set_progress(self, v):
        self.progress["value"] = v
        self.status_var.set(f"{v}/{self.progress['maximum']}")

    def _pause(self):
        self._paused.set()
        (CHECKPOINTS_DIR / "pausar.txt").write_text("sim", encoding="utf-8")
        self._log("⏸ Pausa solicitada.\n")

    def _resume(self):
        self._paused.clear()
        p = CHECKPOINTS_DIR / "pausar.txt"
        if p.exists():
            p.unlink()
        self._log("▶ Continuando...\n")

    def _cancel(self):
        self._stop.set()
        (CHECKPOINTS_DIR / "cancelar.txt").write_text("sim", encoding="utf-8")
        self._log("⏹ Cancelando...\n")

    def _send_test(self):
        email = self.test_email_var.get().strip()
        if not email:
            messagebox.showwarning("Aviso", "Digite um email para o teste.")
            return
        tpl_name = self.tpl_var.get()
        if not tpl_name:
            messagebox.showwarning("Aviso", "Selecione um template.")
            return
        csv_name = self.csv_var.get()
        if not csv_name:
            messagebox.showwarning("Aviso", "Selecione um CSV.")
            return
        env = load_env()
        if not env["SMTP_USERNAME"] or not env["SMTP_PASSWORD"]:
            messagebox.showwarning("Aviso", "Configure o SMTP na aba Config SMTP primeiro.")
            return
        Thread(target=self._run_test, args=(email, tpl_name, csv_name, env), daemon=True).start()

    def _run_test(self, email, tpl_name, csv_name, env):
        tpl_path = TEMPLATES_DIR / tpl_name
        try:
            html_base = tpl_path.read_text(encoding="utf-8")
        except Exception as e:
            self.after(0, self._log, f"[ERRO] Ler template: {e}\n")
            return
        contatos = self._load_contatos(csv_name)
        if not contatos:
            self.after(0, self._log, "❌ Nenhum contato no CSV para preencher o template.\n")
            return
        c = contatos[0]
        html = html_base
        for k, v in c["raw"].items():
            html = html.replace("{{" + k.upper() + "}}", str(v) if v else "")
            html = html.replace("{{" + k + "}}", str(v) if v else "")
        subject = self.subject_var.get() or env.get("SUBJECT", "")
        from_name = env.get("FROM_NAME", "")
        reply_to = env.get("REPLY_TO", "")
        try:
            server = _connect_smtp(env, timeout=15)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[TESTE] {subject}"
            from_email = env.get("FROM_EMAIL") or env["SMTP_USERNAME"]
            msg["From"] = f"{_ascii_name(from_name)} <{from_email}>"
            msg["To"] = email
            if reply_to:
                msg["Reply-To"] = reply_to
            msg.attach(MIMEText(html, "html", "utf-8"))
            server.sendmail(from_email, email, msg.as_string())
            server.quit()
            self.after(0, self._log, f"✅ Teste enviado para {email}\n")
        except Exception as e:
            self.after(0, self._log, f"[ERRO] Teste falhou: {e}\n")

    def _toggle_buttons(self, running):
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_pause.configure(state="normal" if running else "disabled")
        self.btn_resume.configure(state="normal" if running else "disabled")
        self.btn_cancel.configure(state="normal" if running else "disabled")

    def _finish(self):
        self._running = False
        self._toggle_buttons(False)
        self.status_var.set("Pronto.")


# ── Lists Tab ──
class ListsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._current_csv = None
        self._data = []
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 8))

        ttk.Label(top, text="Arquivo:", bootstyle="primary").pack(side="left")
        self.csv_var = tk.StringVar()
        self.csv_combo = ttk.Combobox(top, textvariable=self.csv_var, state="readonly", width=40)
        self.csv_combo.pack(side="left", padx=5)
        ttk.Button(top, text="📂 Importar CSV", command=self._import_csv, bootstyle="primary").pack(side="right", padx=3)
        ttk.Button(top, text="↻", command=self._refresh_list, width=3, bootstyle="info").pack(side="right")

        mid = ttk.Frame(self)
        mid.pack(fill="x", pady=4)
        self.search_var = tk.StringVar()
        ttk.Label(mid, text="🔍 Buscar:", bootstyle="primary").pack(side="left")
        ttk.Entry(mid, textvariable=self.search_var, width=30).pack(side="left", padx=5)
        ttk.Button(mid, text="Filtrar", command=self._filter, bootstyle="info").pack(side="left")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=2)
        ttk.Button(actions, text="📄 Nova lista", command=self._new_list, bootstyle="primary").pack(side="left", padx=2)
        ttk.Button(actions, text="➕ Adicionar contato", command=self._add_contact, bootstyle="success").pack(side="left", padx=2)
        ttk.Button(actions, text="✏️ Editar contato", command=self._edit_contact, bootstyle="warning").pack(side="left", padx=2)
        ttk.Button(actions, text="🗑️ Remover contato", command=self._delete_selected, bootstyle="danger").pack(side="left", padx=2)
        ttk.Button(actions, text="💾 Salvar", command=self._save, bootstyle="success").pack(side="right", padx=2)
        ttk.Button(actions, text="🗑️ Deletar lista", command=self._delete_list, bootstyle="danger").pack(side="right", padx=2)

        cols = ("#", "Email", "Empresa", "Cidade", "Telefone")
        tree_frame = ttk.LabelFrame(self, text="Dados", )
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14,
                                 selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80 if c == "#" else (200 if c == "Email" else 150))
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._edit_cell)
        self.tree.bind("<Delete>", self._delete_rows)

        self._refresh_list()

    def _refresh_list(self):
        files = sorted(f.name for f in LISTAS_DIR.glob("*.csv"))
        self.csv_combo["values"] = files
        if files:
            self.csv_combo.set(files[0])
            self._load_csv(files[0])
        else:
            for item in self.tree.get_children():
                self.tree.delete(item)

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="Importar CSV",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")]
        )
        if path:
            dst = LISTAS_DIR / Path(path).name
            shutil.copy2(path, dst)
            self._refresh_list()
            self.csv_combo.set(dst.name)
            self._load_csv(dst.name)

    def _load_csv(self, name):
        self._current_csv = name
        self._data = []
        path = LISTAS_DIR / name
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            h = f.readline()
            f.seek(0)
            delim = ";" if ";" in h else ","
            reader = csv_mod.DictReader(f, delimiter=delim)
            for row in reader:
                self._data.append({k.strip(): (v.strip() if v else "") for k, v in row.items()})
        self._render()

    def _render(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        query = self.search_var.get().lower()
        for i, row in enumerate(self._data):
            if query and not any(query in v.lower() for v in row.values()):
                continue
            email = row.get("Email") or row.get("email") or ""
            empresa = row.get("Razao Social") or row.get("nome_empresa") or row.get("Nome") or ""
            cidade = row.get("Cidade") or row.get("cidade") or ""
            telefone = row.get("Telefone") or row.get("telefone") or ""
            self.tree.insert("", "end", values=(i + 1, email, empresa, cidade, telefone))

    def _filter(self):
        self._render()

    def _edit_cell(self, event):
        col = self.tree.identify_column(event.x)
        item = self.tree.selection()[0]
        values = list(self.tree.item(item, "values"))
        idx = int(values[0]) - 1
        col_map = {"#2": "Email", "#3": "Empresa", "#4": "Cidade", "#5": "Telefone"}
        key = col_map.get(col)
        if not key or idx < 0 or idx >= len(self._data):
            return
        old_val = values[int(col.replace("#", "")) - 1] if col != "#1" else ""
        new_val = simpledialog.askstring("Editar", f"Novo valor para {key}:", initialvalue=old_val, parent=self)
        if new_val is not None:
            csv_cols = list(self._data[idx].keys())
            if key == "Email":
                ec = next((c for c in csv_cols if "email" in c.lower()), None)
                if ec:
                    self._data[idx][ec] = new_val
            elif key == "Empresa":
                ec = next((c for c in csv_cols if any(x in c.lower() for x in ("razao", "empresa", "nome"))), None)
                if ec:
                    self._data[idx][ec] = new_val
            elif key == "Cidade":
                ec = next((c for c in csv_cols if "cidade" in c.lower()), None)
                if ec:
                    self._data[idx][ec] = new_val
            elif key == "Telefone":
                ec = next((c for c in csv_cols if "telefone" in c.lower() or "fone" in c.lower()), None)
                if ec:
                    self._data[idx][ec] = new_val
            self._render()

    def _delete_rows(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        indices = sorted((int(self.tree.item(item, "values")[0]) - 1 for item in selected), reverse=True)
        if messagebox.askyesno("Remover", f"Remover {len(indices)} linha(s)?"):
            for i in indices:
                if 0 <= i < len(self._data):
                    self._data.pop(i)
            self._render()

    def _contact_dialog(self, title, defaults=None):
        if not self._data and not defaults:
            cols = ["Email", "Razao Social", "Cidade", "Telefone"]
        elif defaults:
            cols = list(defaults.keys())
        else:
            cols = list(self._data[0].keys())
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("400x300+200+100")
        dialog.transient(self)
        dialog.grab_set()
        entries = {}
        for i, col in enumerate(cols):
            ttk.Label(dialog, text=f"{col}:").grid(row=i, column=0, sticky="w", padx=8, pady=4)
            e = ttk.Entry(dialog, width=40)
            e.grid(row=i, column=1, sticky="ew", padx=8, pady=4)
            if defaults and col in defaults:
                e.insert(0, defaults[col])
            entries[col] = e
        result = {"ok": False, "row": None}
        def confirm():
            result["row"] = {c: entries[c].get() for c in cols}
            result["ok"] = True
            dialog.destroy()
        def cancel():
            dialog.destroy()
        btn_f = ttk.Frame(dialog)
        btn_f.grid(row=len(cols), column=0, columnspan=2, pady=12)
        ttk.Button(btn_f, text="Confirmar", command=confirm, bootstyle="success").pack(side="left", padx=6)
        ttk.Button(btn_f, text="Cancelar", command=cancel, bootstyle="secondary").pack(side="left", padx=6)
        dialog.wait_window()
        return result["row"] if result["ok"] else None

    def _add_contact(self):
        row = self._contact_dialog("Adicionar contato")
        if row:
            self._data.append(row)
            self._render()

    def _edit_contact(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Editar", "Selecione um contato.")
            return
        idx = int(self.tree.item(sel[0], "values")[0]) - 1
        if idx < 0 or idx >= len(self._data):
            return
        row = self._contact_dialog("Editar contato", defaults=self._data[idx])
        if row:
            self._data[idx] = row
            self._render()

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Remover", "Selecione um ou mais contatos.")
            return
        self.tree.event_generate("<Delete>")

    def _new_list(self):
        name = simpledialog.askstring("Nova lista", "Nome do arquivo (sem .csv):", parent=self)
        if name:
            if not name.endswith(".csv"):
                name += ".csv"
            path = LISTAS_DIR / name
            if path.exists():
                messagebox.showwarning("Nova lista", "Já existe.")
                return
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("Email;Razao Social;Cidade;Telefone\n")
            self._refresh_list()
            self.csv_combo.set(name)
            self._load_csv(name)

    def _delete_list(self):
        if not self._current_csv:
            return
        if messagebox.askyesno("Deletar lista", f"Excluir '{self._current_csv}' permanentemente?"):
            path = LISTAS_DIR / self._current_csv
            if path.exists():
                path.unlink()
            self._current_csv = None
            self._data = []
            self._refresh_list()

    def _save(self):
        if not self._current_csv or not self._data:
            return
        path = LISTAS_DIR / self._current_csv
        cols = list(self._data[0].keys())
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=cols, delimiter=";")
            writer.writeheader()
            writer.writerows(self._data)
        messagebox.showinfo("Salvo", f"{path.name} salvo com {len(self._data)} linhas.")


# ── Provider presets ──
PROVIDER_PRESETS = {
    "gmail": {
        "label": "Gmail",
        "emoji": "🔴",
        "smtp": {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": {"IMAP_HOST": "imap.gmail.com", "IMAP_PORT": "993", "IMAP_USE_SSL": "true"},
        "bounce_method": "imap",
        "bounce_note": "Bounce via IMAP. Use a mesma conta ou uma dedicada.",
        "creds_note": "Use App Password (16 chars). Ative 2FA em myaccount.google.com/security",
        "labels": {"SMTP_USERNAME": "Email Gmail:", "SMTP_PASSWORD": "App Password:"},
    },
    "amazon_ses": {
        "label": "Amazon SES",
        "emoji": "☁️",
        "smtp": {"SMTP_HOST": "email-smtp.us-east-1.amazonaws.com", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": None,
        "bounce_method": "api",
        "bounce_note": "Bounce via SES API (SNS). Crie um tópico SNS e assine por email ou HTTP.",
        "creds_note": "Credenciais geradas em SES Console → SMTP Settings. SMTP Username começa com AKIA.",
        "labels": {"SMTP_USERNAME": "SMTP Username:", "SMTP_PASSWORD": "SMTP Password:"},
        "host_options": [
            "email-smtp.us-east-1.amazonaws.com",
            "email-smtp.us-east-2.amazonaws.com",
            "email-smtp.us-west-2.amazonaws.com",
            "email-smtp.eu-west-1.amazonaws.com",
            "email-smtp.eu-central-1.amazonaws.com",
            "email-smtp.ap-southeast-1.amazonaws.com",
            "email-smtp.ap-southeast-2.amazonaws.com",
            "email-smtp.ap-northeast-1.amazonaws.com",
            "email-smtp.sa-east-1.amazonaws.com",
        ],
    },
    "sendgrid": {
        "label": "SendGrid",
        "emoji": "📧",
        "smtp": {"SMTP_HOST": "smtp.sendgrid.net", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": None,
        "bounce_method": "api",
        "bounce_note": "Bounce via SendGrid API. Use API Key do SendGrid.",
        "creds_note": "Usuário fixo: 'apikey'. Cole sua API Key no campo Senha.",
        "labels": {"SMTP_USERNAME": "Usuário (fixo):", "SMTP_PASSWORD": "API Key:"},
        "username_fixed": "apikey",
    },
    "mailgun": {
        "label": "Mailgun",
        "emoji": "🔫",
        "smtp": {"SMTP_HOST": "smtp.mailgun.org", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": None,
        "bounce_method": "api",
        "bounce_note": "Bounce via Mailgun API. Use API Key do Mailgun.",
        "creds_note": "SMTP credentials em Mailgun Dashboard → Domains → SMTP credentials",
        "labels": {"SMTP_USERNAME": "SMTP Login:", "SMTP_PASSWORD": "SMTP Password:"},
    },
    "outlook": {
        "label": "Outlook",
        "emoji": "🔵",
        "smtp": {"SMTP_HOST": "smtp.office365.com", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": {"IMAP_HOST": "outlook.office365.com", "IMAP_PORT": "993", "IMAP_USE_SSL": "true"},
        "bounce_method": "imap",
        "bounce_note": "Bounce via IMAP. Use a mesma conta ou uma dedicada.",
        "creds_note": "Use email e senha da conta Microsoft (ou App Password com 2FA)",
        "labels": {"SMTP_USERNAME": "Email:", "SMTP_PASSWORD": "Senha / App Password:"},
    },
    "generic": {
        "label": "SMTP Genérico",
        "emoji": "⚙️",
        "smtp": {"SMTP_HOST": "", "SMTP_PORT": "587", "SMTP_USE_SSL": "false"},
        "imap": {"IMAP_HOST": "", "IMAP_PORT": "993", "IMAP_USE_SSL": "true"},
        "bounce_method": "imap",
        "bounce_note": "Configure manualmente conforme seu provedor.",
        "creds_note": "Preencha manualmente os campos abaixo conforme seu provedor",
        "labels": {"SMTP_USERNAME": "Usuário:", "SMTP_PASSWORD": "Senha:"},
    },
}

# ── SMTP Config Tab ──
class SMTPTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.fields = {}
        self._field_labels = {}
        self._provider_btns = {}
        self._current_provider = None
        self._creds_label = None
        self._imap_frame = None
        self._imap_note = None
        self._build()

    def _build(self):
        ttk.Label(self, text="Configuração SMTP",
                  font=("Segoe UI", 14, "bold"), bootstyle="primary").pack(anchor="w")

        # ── Provider selector ──
        prov_frame = ttk.LabelFrame(self, text="Provedor")
        prov_frame.pack(fill="x", pady=(4, 0))

        btn_row = ttk.Frame(prov_frame)
        btn_row.pack()

        provider_keys = list(PROVIDER_PRESETS.keys())
        colors = ["danger", "info", "warning", "secondary", "primary", "dark"]
        for idx, pkey in enumerate(provider_keys):
            p = PROVIDER_PRESETS[pkey]
            boot = colors[idx % len(colors)]
            btn = ttk.Button(btn_row, text=f"○  {p['emoji']}  {p['label']}",
                             bootstyle=f"{boot}-outline",
                             command=lambda k=pkey: self._select_provider(k))
            btn.pack(side="left", padx=3, pady=2)
            self._provider_btns[pkey] = (btn, boot)

        self._creds_label = ttk.Label(prov_frame, text="", bootstyle="secondary",
                                       font=("Segoe UI", 9, "italic"))
        self._creds_label.pack(anchor="w", pady=(4, 0))

        # ── SMTP + Sender fields ──
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, pady=4)

        left = ttk.LabelFrame(main, text="Servidor SMTP")
        left.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        right = ttk.LabelFrame(main, text="Remetente")
        right.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)

        smtp_fields = [
            ("SMTP_HOST", "Servidor:"),
            ("SMTP_PORT", "Porta:"),
            ("SMTP_USE_SSL", "Usar SSL:"),
            ("SMTP_USERNAME", "Usuário:"),
            ("SMTP_PASSWORD", "Senha:"),
            ("IAM_USERNAME", "Usuário IAM:"),
        ]
        for i, (key, lbl) in enumerate(smtp_fields):
            lbl_w = ttk.Label(left, text=lbl)
            lbl_w.grid(row=i, column=0, sticky="w", pady=3)
            self._field_labels[key] = lbl_w
            if key == "SMTP_USE_SSL":
                self.fields[key] = ttk.Combobox(left, values=["true", "false"], state="readonly", width=10)
            elif key == "SMTP_PORT":
                self.fields[key] = ttk.Combobox(left, values=["465", "587", "25"], state="readonly", width=10)
            elif key == "SMTP_PASSWORD":
                self.fields[key] = ttk.Entry(left, width=28, show="*")
            elif key == "SMTP_HOST":
                self.fields[key] = ttk.Combobox(left, values=[], state="normal", width=36)
            else:
                self.fields[key] = ttk.Entry(left, width=28)
            self.fields[key].grid(row=i, column=1, sticky="ew", pady=3, padx=5)

        sender_fields = [
            ("FROM_NAME", "Nome do remetente:"),
            ("FROM_EMAIL", "Email do remetente:"),
            ("SUBJECT", "Assunto padrão:"),
            ("REPLY_TO", "Reply-To:"),
            ("TEMPLATE_PATH", "Template HTML:"),
            ("RATE_PER_MIN", "Rate (/min):"),
        ]
        for i, (key, lbl) in enumerate(sender_fields):
            ttk.Label(right, text=lbl).grid(row=i, column=0, sticky="w", pady=3)
            self.fields[key] = ttk.Entry(right, width=30)
            self.fields[key].grid(row=i, column=1, sticky="ew", pady=3, padx=5)

        # ── Bounce section ──
        self._imap_frame = ttk.LabelFrame(main, text="Monitoramento de Bounce")
        self._imap_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)

        ttk.Label(self._imap_frame, text="Método:").grid(row=0, column=0, sticky="w", pady=3)
        self.fields["BOUNCE_METHOD"] = ttk.Combobox(self._imap_frame,
            values=["imap", "api", "desativado"], state="readonly", width=14)
        self.fields["BOUNCE_METHOD"].grid(row=0, column=1, sticky="w", pady=3, padx=5)
        self.fields["BOUNCE_METHOD"].bind("<<ComboboxSelected>>", self._on_bounce_method_change)

        self._imap_fields_frame = ttk.Frame(self._imap_frame)
        self._imap_fields_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=2)

        imap_fields = [
            ("IMAP_HOST", "Servidor IMAP:"),
            ("IMAP_PORT", "Porta IMAP:"),
            ("IMAP_USE_SSL", "Usar SSL:"),
            ("IMAP_USERNAME", "Usuário IMAP:"),
            ("IMAP_PASSWORD", "Senha IMAP:"),
        ]
        for i, (key, lbl) in enumerate(imap_fields):
            ttk.Label(self._imap_fields_frame, text=lbl).grid(row=i, column=0, sticky="w", pady=2)
            if key == "IMAP_USE_SSL":
                self.fields[key] = ttk.Combobox(self._imap_fields_frame, values=["true", "false"], state="readonly", width=10)
            elif key == "IMAP_PORT":
                self.fields[key] = ttk.Combobox(self._imap_fields_frame, values=["993", "143"], state="readonly", width=10)
            elif key == "IMAP_PASSWORD":
                self.fields[key] = ttk.Entry(self._imap_fields_frame, width=50, show="*")
            else:
                self.fields[key] = ttk.Entry(self._imap_fields_frame, width=50)
            self.fields[key].grid(row=i, column=1, sticky="ew", pady=2, padx=5)
        self._imap_fields_frame.grid_columnconfigure(1, weight=1)

        self._api_fields_frame = ttk.Frame(self._imap_frame)
        self._api_fields_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=2)

        ttk.Label(self._api_fields_frame, text="API Key:").grid(row=0, column=0, sticky="w", pady=2)
        self.fields["BOUNCE_API_KEY"] = ttk.Entry(self._api_fields_frame, width=60, show="*")
        self.fields["BOUNCE_API_KEY"].grid(row=0, column=1, sticky="ew", pady=2, padx=5)

        ttk.Label(self._api_fields_frame, text="API URL:").grid(row=1, column=0, sticky="w", pady=2)
        self.fields["BOUNCE_API_URL"] = ttk.Entry(self._api_fields_frame, width=60)
        self.fields["BOUNCE_API_URL"].grid(row=1, column=1, sticky="ew", pady=2, padx=5)
        self._api_fields_frame.grid_columnconfigure(1, weight=1)

        self._imap_note = ttk.Label(self._imap_frame, text="", bootstyle="secondary",
                                     font=("Segoe UI", 9, "italic"))
        self._imap_note.grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        self._bounce_test_btn = ttk.Button(self._imap_frame, text="🔌 Testar bounce",
                                            command=self._test_bounce, bootstyle="info")
        self._bounce_test_btn.grid(row=4, column=0, columnspan=2, sticky="w", pady=2, padx=2)
        self._bounce_test_status = ttk.Label(self._imap_frame, text="", font=("Segoe UI", 9))
        self._bounce_test_status.grid(row=5, column=0, columnspan=2, sticky="w", pady=1)

        # ── Buttons ──
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=8)
        ttk.Button(btn_row, text="★ Definir como padrão", command=self._set_default, bootstyle="warning").pack(side="left", padx=3)
        ttk.Button(btn_row, text="💾 Salvar configurações", command=self._save, bootstyle="success").pack(side="left", padx=3)
        ttk.Button(btn_row, text="🔌 Testar conexão", command=self._test, bootstyle="info").pack(side="left", padx=3)
        ttk.Button(btn_row, text="📂 Selecionar template", command=self._pick_template, bootstyle="primary").pack(side="left", padx=3)

        self.status = ttk.Label(self, text="")
        self.status.pack(anchor="w")

        self._load()

    def _adjust_ui(self, pkey):
        p = PROVIDER_PRESETS[pkey]

        # Update field labels per provider
        overrides = p.get("labels", {})
        for key, lbl_w in self._field_labels.items():
            lbl_w.configure(text=overrides.get(key, {
                "SMTP_HOST": "Servidor:",
                "SMTP_PORT": "Porta:",
                "SMTP_USE_SSL": "Usar SSL:",
                "SMTP_USERNAME": "Usuário:",
                "SMTP_PASSWORD": "Senha:",
                "IAM_USERNAME": "Usuário IAM:",
            }.get(key, "")))

        # Show/hide IAM_USERNAME (SES-only field)
        iam_field = self.fields.get("IAM_USERNAME")
        iam_label = self._field_labels.get("IAM_USERNAME")
        if iam_field and iam_label:
            if pkey == "amazon_ses":
                iam_field.grid()
                iam_label.grid()
            else:
                iam_field.grid_remove()
                iam_label.grid_remove()

        # Update SMTP_HOST combobox options if provider has them
        host_field = self.fields.get("SMTP_HOST")
        if host_field and isinstance(host_field, ttk.Combobox):
            opts = p.get("host_options", [])
            if opts:
                host_field.configure(values=opts, state="normal")
            else:
                host_field.configure(values=[], state="normal")

        # For SendGrid: fix username to "apikey" and make readonly
        username_field = self.fields.get("SMTP_USERNAME")
        if username_field:
            fixed = p.get("username_fixed")
            if fixed:
                username_field.configure(state="normal")
                username_field.delete(0, "end")
                username_field.insert(0, fixed)
                username_field.configure(state="readonly")
            else:
                username_field.configure(state="normal")

        # Set bounce method and update visibility
        method_field = self.fields.get("BOUNCE_METHOD")
        if method_field:
            method_field.set(p.get("bounce_method", "imap"))
        self._imap_note.configure(text=p.get("bounce_note", ""), bootstyle="info")
        self._update_bounce_visibility()

        # Update credential hint
        self._creds_label.configure(text=f"💡 {p['creds_note']}", bootstyle="info")

    def _update_bounce_visibility(self):
        method = self.fields["BOUNCE_METHOD"].get()
        if method == "imap":
            self._imap_fields_frame.grid()
            self._api_fields_frame.grid_remove()
            for key in ("IMAP_HOST", "IMAP_PORT", "IMAP_USE_SSL", "IMAP_USERNAME", "IMAP_PASSWORD"):
                if key in self.fields:
                    self.fields[key].configure(state="normal")
        elif method == "api":
            self._imap_fields_frame.grid_remove()
            self._api_fields_frame.grid()
            for key in ("BOUNCE_API_KEY", "BOUNCE_API_URL"):
                if key in self.fields:
                    self.fields[key].configure(state="normal")
        else:
            self._imap_fields_frame.grid_remove()
            self._api_fields_frame.grid_remove()

    def _on_bounce_method_change(self, event=None):
        self._update_bounce_visibility()

    def _select_provider(self, pkey):
        self._current_provider = pkey
        p = PROVIDER_PRESETS[pkey]

        # Radio indicator + highlight
        for k, (btn, boot) in self._provider_btns.items():
            pk = PROVIDER_PRESETS[k]
            radio = "●" if k == pkey else "○"
            btn.configure(text=f"{radio}  {pk['emoji']}  {pk['label']}",
                          bootstyle=f"{boot}" if k == pkey else f"{boot}-outline")

        self._adjust_ui(pkey)
        full_env = load_env()
        pkey_upper = pkey.upper()

        # SMTP fields: load prefixed or fall back to preset defaults
        for key, default_val in p["smtp"].items():
            if key in self.fields:
                f = self.fields[key]
                prefixed = full_env.get(f"{key}_{pkey_upper}")
                if prefixed:
                    val = prefixed
                elif pkey == "generic":
                    continue  # keep whatever _load set from flat keys
                else:
                    val = default_val
                if isinstance(f, ttk.Combobox):
                    f.set(val)
                else:
                    f.delete(0, "end")
                    f.insert(0, val)

        # IMAP fields: load prefixed or fall back to preset defaults
        if p["imap"]:
            for key, default_val in p["imap"].items():
                if key in self.fields:
                    f = self.fields[key]
                    prefixed = full_env.get(f"{key}_{pkey_upper}")
                    if prefixed:
                        val = prefixed
                    elif pkey == "generic":
                        continue
                    else:
                        val = default_val
                    if isinstance(f, ttk.Combobox):
                        f.set(val)
                    else:
                        f.delete(0, "end")
                        f.insert(0, val)

        # Other fields (sender, bounce): load prefixed if saved, else keep current
        smtp_keys = set(p["smtp"].keys())
        imap_keys = set(p["imap"].keys()) if p["imap"] else set()
        for key in self.fields:
            if key in smtp_keys or key in imap_keys:
                continue
            prefixed = full_env.get(f"{key}_{pkey_upper}")
            if prefixed:
                f = self.fields[key]
                if isinstance(f, ttk.Combobox):
                    f.set(prefixed)
                else:
                    f.delete(0, "end")
                    f.insert(0, prefixed)

    def _load(self):
        env = load_env()
        # Load flat keys into fields (active/default provider's config)
        for k, v in env.items():
            if k in self.fields:
                if isinstance(self.fields[k], ttk.Combobox):
                    self.fields[k].set(v)
                else:
                    self.fields[k].delete(0, "end")
                    self.fields[k].insert(0, v)
        saved_provider = env.get("PROVIDER", "")
        if saved_provider in PROVIDER_PRESETS:
            self._select_provider(saved_provider)
            return
        # Auto-detect provider from SMTP_HOST
        host = self.fields.get("SMTP_HOST")
        if host:
            host_val = host.get()
            for pkey, preset in PROVIDER_PRESETS.items():
                if preset["smtp"].get("SMTP_HOST", "").lower() == host_val.lower():
                    self._select_provider(pkey)
                    return
        # Fallback: select generic
        self._select_provider("generic")

    def _save(self):
        provider = self._current_provider
        if not provider:
            self.status.configure(text="❌ Selecione um provedor primeiro.", foreground="#dc3545")
            return
        p = PROVIDER_PRESETS.get(provider, {})
        label = p.get("label", provider)
        env = {}
        for k, field in self.fields.items():
            env[f"{k}_{provider.upper()}"] = field.get() if isinstance(field, ttk.Combobox) else field.get()
        try:
            save_env(env)
            self.status.configure(text=f"✅ {label} salvo individualmente.", foreground="#198754")
        except Exception as e:
            self.status.configure(text=f"❌ Erro ao salvar: {e}", foreground="#dc3545")

    def _set_default(self):
        provider = self._current_provider or "generic"
        p = PROVIDER_PRESETS.get(provider, {})
        label = p.get("label", provider)
        env = {}
        for k, field in self.fields.items():
            val = field.get() if isinstance(field, ttk.Combobox) else field.get()
            env[k] = val
            env[f"{k}_{provider.upper()}"] = val
        env["PROVIDER"] = provider
        try:
            save_env(env)
            self.status.configure(text=f"★ {label} definido como padrão!", foreground="#198754")
        except Exception as e:
            self.status.configure(text=f"❌ Erro: {e}", foreground="#dc3545")

    def _test(self):
        env = {}
        for k, field in self.fields.items():
            if isinstance(field, ttk.Combobox):
                env[k] = field.get()
            else:
                env[k] = field.get()
        provider = self._current_provider or "personalizado"
        provider_label = PROVIDER_PRESETS.get(provider, {}).get("label", provider)
        self.status.configure(text=f"🔌 Testando {provider_label}...", foreground="#0d6efd")
        Thread(target=self._test_connection, args=(env, provider_label), daemon=True).start()

    def _test_connection(self, env, provider_label="SMTP"):
        try:
            server = _connect_smtp(env)
            server.quit()
            self.after(0, lambda: self.status.configure(
                text=f"✅ {provider_label}: conexão SMTP bem-sucedida!", foreground="#198754"))
        except Exception as e:
            self.after(0, lambda: self.status.configure(
                text=f"❌ {provider_label}: {e}", foreground="#dc3545"))

    def _test_bounce(self):
        env = {}
        for k, field in self.fields.items():
            env[k] = field.get() if isinstance(field, ttk.Combobox) else field.get()
        method = env.get("BOUNCE_METHOD", "imap")
        self._bounce_test_status.configure(text="🔌 Testando...", foreground="#0d6efd")
        Thread(target=self._run_bounce_test, args=(env, method), daemon=True).start()

    def _run_bounce_test(self, env, method):
        if method == "imap":
            user = env.get("IMAP_USERNAME") or env.get("SMTP_USERNAME", "")
            pwd = env.get("IMAP_PASSWORD") or env.get("SMTP_PASSWORD", "")
            host = env.get("IMAP_HOST", "")
            port = int(env.get("IMAP_PORT", "993"))
            ssl = env.get("IMAP_USE_SSL", "true").lower() == "true"
            if not host or not user or not pwd:
                self.after(0, lambda: self._bounce_test_status.configure(
                    text="❌ Preencha IMAP_HOST, usuário e senha.", foreground="#dc3545"))
                return
            try:
                if ssl:
                    mail = imaplib.IMAP4_SSL(host, port, timeout=15)
                else:
                    mail = imaplib.IMAP4(host, port, timeout=15)
                    mail.starttls(ssl_context=_ssl_ctx())
                mail.login(user, pwd)
                mail.logout()
                self.after(0, lambda: self._bounce_test_status.configure(
                    text="✅ Conexão IMAP OK!", foreground="#198754"))
            except Exception as e:
                self.after(0, lambda: self._bounce_test_status.configure(
                    text=f"❌ IMAP: {e}", foreground="#dc3545"))
        elif method == "api":
            key = env.get("BOUNCE_API_KEY", "")
            url = env.get("BOUNCE_API_URL", "")
            if not key:
                self.after(0, lambda: self._bounce_test_status.configure(
                    text="❌ Informe a API Key.", foreground="#dc3545"))
                return
            try:
                import urllib.request
                headers = {"Authorization": f"Bearer {key}"}
                if url:
                    req = urllib.request.Request(url, headers=headers, method="HEAD")
                else:
                    req = urllib.request.Request("https://api.sendgrid.com/v3/mail/send",
                                                 headers=headers, method="HEAD")
                urllib.request.urlopen(req, timeout=10)
                self.after(0, lambda: self._bounce_test_status.configure(
                    text="✅ API respondeu!", foreground="#198754"))
            except urllib.error.HTTPError as e:
                self.after(0, lambda: self._bounce_test_status.configure(
                    text=f"⚠️  API: {e.code} {e.reason}", foreground="#ffc107"))
            except Exception as e:
                self.after(0, lambda: self._bounce_test_status.configure(
                    text=f"❌ API: {e}", foreground="#dc3545"))
        else:
            self.after(0, lambda: self._bounce_test_status.configure(
                text="ℹ️ Bounce desativado.", foreground="#6c757d"))

    def _pick_template(self):
        path = filedialog.askopenfilename(
            title="Selecionar template HTML",
            filetypes=[("HTML", "*.html"), ("All", "*.*")],
            initialdir=str(TEMPLATES_DIR),
        )
        if path:
            dst = TEMPLATES_DIR / Path(path).name
            if path != str(dst):
                shutil.copy2(path, dst)
            rel = f"./backend/templates/{dst.name}"
            self.fields["TEMPLATE_PATH"].delete(0, "end")
            self.fields["TEMPLATE_PATH"].insert(0, rel)
            self._save()


# ── Bounce Tracker Tab ──
class BounceTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._bounces = {}
        self._build()

    def _build(self):
        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=4)
        ttk.Button(btn_row, text="📬 Processar bounces",
                   command=self._process, bootstyle="info").pack(side="left", padx=3)
        ttk.Button(btn_row, text="📋 Carregar de campanhas", bootstyle="primary",
                   command=self._from_campaigns, ).pack(side="left", padx=3)
        ttk.Button(btn_row, text="🧹 Gerar lista limpa",
                   command=self._clean_list, bootstyle="success").pack(side="left", padx=3)
        ttk.Button(btn_row, text="📁 Exportar",
                   command=self._export, bootstyle="secondary").pack(side="right", padx=3)

        cols = ("Email", "Tipo", "Data")
        tree_frame = ttk.LabelFrame(self, text="Bounces", )
        tree_frame.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=300 if c == "Email" else 120)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        self.stats = ttk.Label(self, text="Nenhum dado.", bootstyle="secondary")
        self.stats.pack(anchor="w")

        log_frame = ttk.LabelFrame(self, text="Log", )
        log_frame.pack(fill="x", pady=4)
        self.log = tk.Text(log_frame, height=5, wrap="word", state="disabled",
                           font=("Consolas", 9), bg="#ffffff", fg="#111827",
                           relief="flat", borderwidth=0, padx=4, pady=4)
        self.log.pack(fill="x")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _process(self):
        self._log("🔌 Conectando ao IMAP...\n")
        Thread(target=self._run_process, daemon=True).start()

    def _run_process(self):
        env = load_env()
        user = env.get("IMAP_USERNAME") or env.get("SMTP_USERNAME", "")
        pwd = env.get("IMAP_PASSWORD") or env.get("SMTP_PASSWORD", "")
        imap_host = env.get("IMAP_HOST", "imap.gmail.com")
        imap_port = int(env.get("IMAP_PORT", "993"))
        imap_ssl = env.get("IMAP_USE_SSL", "true").lower() == "true"
        if not user or not pwd:
            self.after(0, self._log, "[ERRO] Configure IMAP ou SMTP primeiro.\n")
            return
        try:
            if imap_ssl:
                mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port, timeout=15)
                mail.starttls(ssl_context=_ssl_ctx())
            mail.login(user, pwd)
        except Exception as e:
            self.after(0, self._log, f"[ERRO IMAP] {e}\n")
            return

        try:
            mail.select("INBOX")
            status, ids = mail.search(None, "UNSEEN")
            if status != "OK" or not ids[0]:
                self.after(0, self._log, "📭 Nenhum email não lido.\n")
                return
            id_list = ids[0].split()
            self.after(0, self._log, f"📧 {len(id_list)} emails.\n")
            import email as email_lib
            self._bounces = {}
            for eid in id_list:
                s, data = mail.fetch(eid, "(RFC822)")
                if s != "OK":
                    continue
                for part in data:
                    if not isinstance(part, tuple):
                        continue
                    msg = email_lib.message_from_bytes(part[1])
                    corpo = ""
                    if msg.is_multipart():
                        for mp in msg.walk():
                            if mp.get_content_type() in ("text/plain", "text/html"):
                                try:
                                    corpo += mp.get_payload(decode=True).decode("utf-8", errors="replace")
                                except Exception:
                                    pass
                    else:
                        try:
                            corpo += msg.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            corpo = str(msg.get_payload())
                    found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', corpo.lower())
                    for f_email in found:
                        if user.lower() not in f_email:
                            tipo = "hard" if any(x in corpo.lower() for x in
                                                  ["550", "user unknown", "no such user", "invalid",
                                                   "mailbox not found", "rejected", "blocked", "spam",
                                                   "does not exist"]) else "soft"
                            self._bounces[f_email] = {"tipo": tipo, "data": datetime.now().isoformat()[:19]}
                            break
            mail.close()
        except Exception as e:
            self.after(0, self._log, f"[ERRO] {e}\n")
        finally:
            mail.logout()
        self.after(0, self._render)

    def _from_campaigns(self):
        self._bounces = {}
        for d in get_campaigns():
            for e in get_sends(d["id"]):
                if e.get("bounce_detected"):
                    self._bounces[e["email"]] = {
                        "tipo": e.get("bounce_type", "unknown"),
                        "data": e.get("bounce_time", ""),
                    }
        self._render()
        self._log(f"📋 Carregados {len(self._bounces)} bounces de campanhas.\n")

    def _render(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for email, info in self._bounces.items():
            self.tree.insert("", "end", values=(email, info["tipo"], info["data"]))
        hards = sum(1 for v in self._bounces.values() if v["tipo"] == "hard")
        softs = sum(1 for v in self._bounces.values() if v["tipo"] == "soft")
        self.stats.configure(
            text=f"Total: {len(self._bounces)}  |  🔴 Hard: {hards}  |  🟡 Soft: {softs}")

    def _clean_list(self):
        campaigns = get_campaigns()
        if not campaigns:
            messagebox.showinfo("Lista Limpa", "Nenhuma campanha.")
            return
        d = campaigns[0]
        envios = get_sends(d["id"])
        hards = set(e["email"] for e in envios
                    if e.get("bounce_detected") and e.get("bounce_type") == "hard")
        msg = f"🔴 Hard bounces: {len(hards)}\n"
        for e in hards:
            msg += f"   - {e}\n"
        msg += "\nRemova estes emails antes de reenviar."
        messagebox.showinfo("Lista Limpa", msg)

    def _export(self):
        if not self._bounces:
            messagebox.showwarning("Aviso", "Nada para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialdir=str(LOGS_DIR),
        )
        if path:
            Path(path).write_text(
                json.dumps(self._bounces, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log(f"✅ Exportado: {path}\n")


# ── Reports Tab ──
class ReportsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Histórico de Campanhas",
                  font=("Segoe UI", 14, "bold"), ).pack(side="left")
        ttk.Button(top, text="↻ Atualizar", command=self._refresh, bootstyle="info").pack(side="right")
        ttk.Button(top, text="📁 Abrir pasta de logs",
                   command=lambda: os.startfile(LOGS_DIR), bootstyle="primary").pack(side="right", padx=5)

        cols = ("Início", "Assunto", "CSV", "Total", "Enviados", "Falhas", "Bounces", "Pulados", "Status")
        tree_frame = ttk.LabelFrame(self, text="Campanhas", )
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
        widths = [150, 200, 130, 60, 70, 60, 70, 60, 90]
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, minwidth=50)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll_v.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll_v.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = ttk.LabelFrame(self, text="Detalhes dos envios", )
        detail_frame.pack(fill="both", expand=True, pady=(6, 0))
        inner = ttk.Frame(detail_frame)
        inner.pack(fill="both", expand=True)
        cols_d = ("Email", "Status", "Erro", "Timestamp", "Bounce")
        self.detail_tree = ttk.Treeview(inner, columns=cols_d, show="headings", height=6)
        for c, w in zip(cols_d, [250, 70, 200, 140, 70]):
            self.detail_tree.heading(c, text=c)
            self.detail_tree.column(c, width=w, minwidth=50)
        self.detail_tree.pack(side="left", fill="both", expand=True)
        scroll_d = ttk.Scrollbar(inner, orient="vertical", command=self.detail_tree.yview)
        scroll_d.pack(side="right", fill="y")
        self.detail_tree.configure(yscrollcommand=scroll_d.set)

        self.summary_label = ttk.Label(detail_frame, text="", bootstyle="secondary")
        self.summary_label.pack(anchor="w")

        self._campaigns = []
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._campaigns = get_campaigns()
        for d in self._campaigns:
            inicio = (d.get("start_time") or "")[:19]
            assunto = (d.get("subject") or "")[:40]
            csv_name = (d.get("csv_file") or "")[:30]
            total = d.get("total", 0)
            suc = d.get("sent", 0)
            fal = d.get("failed", 0)
            bou = d.get("bounced", 0)
            pul = d.get("skipped_bounce", 0)
            status = d.get("status", "")
            self.tree.insert("", "end", values=(inicio, assunto, csv_name, total, suc, fal, bou, pul, status))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self._campaigns):
            return
        d = self._campaigns[idx]
        for item in self.detail_tree.get_children():
            self.detail_tree.delete(item)
        envios = get_sends(d["id"])
        for e in envios:
            email = e.get("email", "")
            status = e.get("status", "")
            erro = (e.get("error") or "")[:50]
            ts = (e.get("timestamp") or "")[:19]
            bounce = "🔴" if e.get("bounce_detected") else ""
            self.detail_tree.insert("", "end", values=(email, status, erro, ts, bounce))
        hards = sum(1 for e in envios if e.get("bounce_detected") and e.get("bounce_type") == "hard")
        self.summary_label.configure(
            text=f"Total: {len(envios)}  ✅ Sucesso: {d.get('sent', 0)}  "
                 f"❌ Falhas: {d.get('failed', 0)}  🔴 Bounce: {hards}")


# ── Main App ──
class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="flatly")
        self.title("SaberMail — Gestão de Campanhas")
        self.geometry("900x600+100+50")
        self.state("zoomed")

        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        s = ttk.Style()
        s.configure(".", background="#eaf0f9", foreground="#1a3a5c")
        s.configure("TFrame", background="#eaf0f9")
        s.configure("TLabel", background="#eaf0f9", foreground="#1a3a5c")
        s.configure("TLabelframe.Label", foreground="#1a3a5c",
                     font=("Segoe UI", 9, "bold"))
        s.configure("Treeview", foreground="#1a3a5c", rowheight=30)
        s.configure("Treeview.Heading", foreground="#1a3a5c", font=("Segoe UI", 9, "bold"))
        s.configure("TCheckbutton", background="#eaf0f9")
        s.configure("TRadiobutton", background="#eaf0f9")
        s.configure("TEntry", foreground="#1a3a5c")
        s.configure("TCombobox", foreground="#1a3a5c")

        # ── Sidebar ──
        sidebar = tk.Frame(self, bg="#1a3a5c")
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")

        title_f = tk.Frame(sidebar, bg="#1a3a5c")
        title_f.pack(fill="x", pady=(16, 4))
        tk.Label(title_f, text="SaberMail",
                 bg="#1a3a5c", fg="white", font=("Segoe UI", 15, "bold")).pack()
        tk.Label(title_f, text="Gestão de Campanhas",
                 bg="#1a3a5c", fg="#b8c8d8", font=("Segoe UI", 9)).pack()

        sep = tk.Frame(sidebar, bg="#2a4a6e", height=1)
        sep.pack(fill="x", padx=14, pady=(10, 8))

        nav = tk.Frame(sidebar, bg="#1a3a5c")
        nav.pack(fill="both", expand=True)

        nav_items = [
            ("📊", "Dashboard", "dashboard"),
            ("🚀", "Campanha", "campanha"),
            ("📋", "Listas", "listas"),
            ("⚙️", "Config SMTP", "smtp"),
            ("📋", "Relatórios", "relatorios"),
            ("📬", "Bounce", "bounce"),
        ]
        self._nav_btns = {}
        self._current_tab = None
        self.tabs = {}

        # ── Content area (tabs + footer) — moved early so self.tabs exists ──
        content = ttk.Frame(self)
        content.grid(row=0, column=1, sticky="nsew")

        tabs_area = ttk.Frame(content)
        tabs_area.pack(fill="both", expand=True)

        for icon, label, key in nav_items:
            frame = tk.Frame(nav, bg="#1a3a5c")
            frame.pack(fill="x", padx=8, pady=1)
            inner = tk.Frame(frame, bg="#1a3a5c")
            inner.pack(fill="x")
            accent = tk.Frame(inner, bg="#1a3a5c", width=3)
            accent.pack(side="left", fill="y")
            btn = tk.Label(inner, text=f"  {icon}  {label}",
                           bg="#1a3a5c", fg="#b8c8d8", font=("Segoe UI", 10),
                           anchor="w", padx=10, pady=8, cursor="hand2")
            btn.pack(side="left", fill="x", expand=True)
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda e, fr=frame, inn=inner, ac=accent, b=btn: (
                fr.configure(bg="#2a4a6e"), inn.configure(bg="#2a4a6e"),
                ac.configure(bg="#2a4a6e"), b.configure(bg="#2a4a6e")))
            btn.bind("<Leave>", lambda e, fr=frame, inn=inner, ac=accent, b=btn, k=key: (
                fr.configure(bg="#1a3a5c" if k != self._current_tab else "#2a4a6e"),
                inn.configure(bg="#1a3a5c" if k != self._current_tab else "#2a4a6e"),
                ac.configure(bg="#0d6efd" if k == self._current_tab else "#1a3a5c"),
                b.configure(bg="#1a3a5c" if k != self._current_tab else "#2a4a6e",
                            fg="white" if k == self._current_tab else "#b8c8d8")))
            self._nav_btns[key] = (frame, inner, accent, btn)

        tk.Frame(nav, bg="#1a3a5c").pack(fill="both", expand=True)

        # ── Sidebar banner (fixed at bottom) ──
        self._banner_bg = "#2a4a6e"
        banner = tk.Frame(sidebar, bg=self._banner_bg,
                          highlightbackground="#3B82F6", highlightcolor="#3B82F6", highlightthickness=2)
        banner.pack(fill="x", padx=8, pady=(0, 8))

        logo_path = DATA_DIR / "newleads_logo.png"
        self._sidebar_logo = None
        if logo_path.exists():
            try:
                raw = tk.PhotoImage(file=str(logo_path))
                f = max(1, raw.width() // 180)
                self._sidebar_logo = raw.subsample(f, f)
            except Exception:
                pass
        if self._sidebar_logo:
            tk.Label(banner, image=self._sidebar_logo, bg=self._banner_bg).pack(pady=(6, 0))
        else:
            c = tk.Canvas(banner, width=100, height=100, bg=self._banner_bg, highlightthickness=0)
            c.create_oval(5, 5, 95, 95, fill="#0d6efd", outline="")
            c.create_text(50, 50, text="NL", fill="white", font=("Segoe UI", 28, "bold"))
            c.pack(pady=(6, 0))

        self._banner_logo = list(banner.winfo_children())

        tk.Label(banner, text="NewLeads",
                 bg=self._banner_bg, fg="white",
                 font=("Segoe UI", 12, "bold")).pack()
        tk.Label(banner, text="Leads CNPJ com filtros por segmento e região",
                 bg=self._banner_bg, fg="#d0dce8",
                 font=("Segoe UI", 8)).pack()
        tk.Label(banner, text="Telefones e emails verificados",
                 bg=self._banner_bg, fg="#b8c8d8",
                 font=("Segoe UI", 7)).pack()

        link_lbl = tk.Label(banner, text="newleads.com.br →",
                            bg=self._banner_bg, fg="#5dade2",
                            font=("Segoe UI", 8, "bold"), cursor="hand2")
        link_lbl.pack(pady=(2, 6))
        link_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://newleads.com.br"))
        self._banner_link = link_lbl

        self._banner = banner

        # ── Populate tabs & footer ──
        self.tabs.update({
            "dashboard": DashboardTab(tabs_area),
            "campanha": CampaignTab(tabs_area),
            "listas": ListsTab(tabs_area),
            "smtp": SMTPTab(tabs_area),
            "relatorios": ReportsTab(tabs_area),
            "bounce": BounceTab(tabs_area),
        })
        for tab in self.tabs.values():
            tab.pack(fill="both", expand=True)

        footer = ttk.Frame(content)
        footer.pack(fill="x")
        ttk.Label(footer, text="Freeware — © Saber Apps (saberapps.com.br). Todos os direitos reservados.",
                  font=("Segoe UI", 8), bootstyle="secondary").pack(pady=3)

        self._switch_tab("dashboard")

    def _download_logo(self, path):
        try:
            urllib.request.urlretrieve(
                "https://newleads.com.br/_next/image?url=%2Flogo.png&w=384&q=75",
                path
            )
            return True
        except Exception:
            return False

    def _switch_tab(self, key):
        self._current_tab = key
        for k, (frame, inner, accent, btn) in self._nav_btns.items():
            if k == key:
                frame.configure(bg="#2a4a6e")
                inner.configure(bg="#2a4a6e")
                accent.configure(bg="#0d6efd")
                btn.configure(bg="#2a4a6e", fg="white")
            else:
                frame.configure(bg="#1a3a5c")
                inner.configure(bg="#1a3a5c")
                accent.configure(bg="#1a3a5c")
                btn.configure(bg="#1a3a5c", fg="#b8c8d8")
        for k, tab in self.tabs.items():
            if k == key:
                tab.pack(fill="both", expand=True)
            else:
                tab.pack_forget()


if __name__ == "__main__":
    app = App()
    app.mainloop()
