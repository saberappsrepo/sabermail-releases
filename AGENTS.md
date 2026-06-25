# AGENTS.md — SaberMail

## Architecture

Two independent mailer systems share `.env` but are otherwise decoupled:

| System | Script | Input | Template | Key traits |
|---|---|---|---|---|
| Generic CLI mailer | `backend/mailer.py` | JSON (`--list`, `--test`) | Jinja2 (`{{name}}`, `{% if %}`) | SSL/STARTTLS, rate limiting, dry-run, preview save |
| Campaign bulk mailer (pt-BR) | `backend/envio_newleads.py` | CSV via `backend/listas/` | `str.replace` | Checkpoint/resume, daily limit, pause/cancel, random delay (2-5s) |
| Frontend Campaign tab | `frontend/app.py` | CSV via `DATA_DIR/listas/` | `str.replace`, case-insensitive column match | GUI + IMAP bounce monitor, auto-clean |

Supporting: `testar_envio.py` (test send + HTML preview), `controle.py` (pause/cancel), `bounce_tracker.py` (IMAP).

Frontend: single `ttkbootstrap` app themed `"flatly"` at `frontend/app.py` (6 tabs with custom `_switch_tab` nav — not `ttk.Notebook`). Tabs: Dashboard, Campanha, Listas, Config SMTP, Relatórios, Bounce.

## Commands (from repo root, `venv\` active)

```
python backend/mailer.py --test <email>
python backend/mailer.py --list backend/contacts/example.json
python backend/mailer.py --list contacts.json --dry-run --save-previews ./previews
python backend/envio_newleads.py
python backend/testar_envio.py
python backend/controle.py
python backend/bounce_tracker.py
python frontend/app.py

powershell -File build_exe.ps1              # → dist/SaberMail/
ISCC.exe installer.iss                       # → dist/SaberMail_Installer_v1.0.0.exe
```

## Setup

- **`venv\`** with all deps pre-installed. Activate: `venv\Scripts\activate`.
- **Deps**: `backend/requirements.txt` (mailer libs) and `frontend/requirements.txt` (GUI + build tools).
- **`.env.example`** at `backend/.env.example` (SSL defaults: port 465, `SMTP_USE_SSL=true`). The root `.env` uses STARTTLS (port 587, `SMTP_USE_SSL=false`) and includes IMAP keys absent from the example.

## Critical gotchas

- **Three template systems** — do not confuse:
  - `mailer.py`: Jinja2 (`{{name}}`, `{% if %}`). Any JSON field is a variable.
  - `envio_newleads.py`: `str.replace` with placeholders `{{NOME_EMPRESA}}`, `{{EMPRESA}}`, `{{CIDADE}}`, `{{CNPJ}}`, `{{TELEFONE}}`, `{{APTA}}`, `{{EMAIL}}`, `{{nome}}`, `{{NOME}}`. Unmatched placeholders appear verbatim.
  - `frontend/app.py` Campaign tab: `str.replace` using CSV column names as keys, matching both `{{COLUMN}}` and `{{column}}`.
- **`.env` resolution**: root `./.env`. CLI scripts find it via `Path(__file__).parent.parent / ".env"`. Frontend: dev loads `root/.env`; frozen loads `DATA_DIR/.env` (copied from exe dir on first run). `envio_newleads.py` reads `.env` at module level — `sys.exit(1)` if missing, so the script cannot even be imported without `.env`.
- **Frontend config flow**: loads `.env` → overrides with SQLite `config` table (`DATA_DIR/simpleship.db`). GUI saves to SQLite only (never writes `.env`). Backend scripts never touch SQLite.
- **IMAP config absent from `.env.example`** — `IMAP_HOST`, `IMAP_PORT`, `IMAP_USE_SSL` only appear in frontend's `_init_defaults()` fallback and SQLite.
- **Live credentials in `.env`** — root `.env` contains real SMTP/IMAP credentials (sabermaisapps@gmail.com). Do not commit changes made to `.env`.
- **SSL CA bundle**: all scripts use `backend/ssl/gmail-ca-bundle.pem` with `VERIFY_X509_PARTIAL_CHAIN`.
- **File-based signaling**: `backend/checkpoints/{pausar.txt,cancelar.txt,campanha_atual.json}`. `envio_newleads.py` polls them; `controle.py` writes/removes them.
- **`envio_newleads.py` typo**: prints `'python controles.py'` (line 603) — the actual file is `controle.py`.
- **`bounce_tracker.py` security**: lines 18-19 contain live IMAP credentials (mirroring `.env`). Do not commit changes to this file.
- **`testar_envio.py` hardcoded test email**: line 47 has `danielcarrobr@gmail.com` as the test recipient.
- **`.gitignore`** excludes `backend/templates/*` and `backend/contacts/*` except example files. Only `backend/templates/example.html` and `backend/contacts/example.json` are tracked.
- **No test framework, no CI, no linting/typechecking** — `.gitignore` references pytest/mypy caches but nothing uses them.
- **Platform**: Windows only (`os.name == 'nt'`, `cls`, backslash paths). `venv/` was created on Windows.
- **References**: `backend/instrucoes.md` (pt-BR) is the authoritative NewLeads doc; `ORIENTACAO.md` (root) documents the restructuring history; `README.md` covers end-user/product view.
