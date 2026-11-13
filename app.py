#!/usr/bin/env python3
"""App de escritorio del Asistente para reuniones inútiles (Windows, Mac y Linux)."""
import datetime as dt
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from dotenv import dotenv_values

import asistente as core

APP_NAME = "Asistente de Reuniones"
INTERVAL = dt.timedelta(minutes=5)

# Paleta
BG = "#f6f5f2"
CARD = "#ffffff"
INK = "#1f2328"
MUTED = "#6b7078"
ACCENT = "#2f6f5e"
ACCENT_SOFT = "#e3efe9"
WARN = "#b4532a"
LINE = "#e2dfd8"

# Colores de evento de Google Calendar (colorId -> nombre)
GCAL_COLORS = {"1": "Lavanda", "2": "Salvia", "3": "Uva", "4": "Flamenco", "5": "Plátano",
               "6": "Mandarina", "7": "Pavo real", "8": "Grafito", "9": "Arándano",
               "10": "Albahaca", "11": "Tomate"}


def open_path(path):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def split_list(text):
    return [p.strip() for p in text.split(",") if p.strip()]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1040x680")
        self.minsize(860, 560)
        self.configure(bg=BG)

        self.events = queue.Queue()
        self.busy = False
        self.next_run = None
        self.items = []
        self.auto = tk.BooleanVar(value=False)

        core.LOG_HANDLERS.append(lambda line: self.events.put(("log", line)))
        self._style()
        self._build_header()
        self._build_tabs()
        self._load_settings()
        self._refresh_summaries()
        self._refresh_setup_hint()
        self._status_idle()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._drain_events)
        self.after(1000, self._tick)

        cfg = core.read_config_raw()
        if cfg.get("app_automatico") and self._ready():
            self.auto.set(True)
            self._schedule_now()
        elif self._ready():
            self.after(400, self.preview)

    # ------------------------------------------------------------- estilo
    def _style(self):
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        self.font_title = tkfont.Font(family=base.cget("family"), size=15, weight="bold")
        self.font_h = tkfont.Font(family=base.cget("family"), size=11, weight="bold")
        self.font_small = tkfont.Font(family=base.cget("family"), size=9)

        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=INK, fieldbackground=CARD, bordercolor=LINE)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=INK)
        s.configure("Card.TLabel", background=CARD)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("CardMuted.TLabel", background=CARD, foreground=MUTED)
        s.configure("Warn.TLabel", background=BG, foreground=WARN)
        s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(12, 6, 12, 0))
        s.configure("TNotebook.Tab", padding=(16, 7), background=BG, foreground=MUTED, borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", INK)])
        s.configure("TButton", padding=(12, 5), background=CARD, borderwidth=1, relief="solid",
                    bordercolor="#cfcabf", lightcolor=CARD, darkcolor=CARD)
        s.map("TButton", background=[("active", ACCENT_SOFT)], bordercolor=[("active", ACCENT)])
        s.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT,
                    lightcolor=ACCENT, darkcolor=ACCENT)
        s.map("Accent.TButton", background=[("active", "#255a4c"), ("disabled", "#9db8ae")])
        s.configure("TCheckbutton", background=BG)
        s.configure("Card.TCheckbutton", background=CARD)
        s.configure("TLabelframe", background=CARD, bordercolor=LINE, relief="solid")
        s.configure("TLabelframe.Label", background=CARD, foreground=ACCENT, font=self.font_h)
        s.configure("Treeview", rowheight=30, background=CARD, fieldbackground=CARD, borderwidth=0)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED, relief="flat", padding=(6, 6))
        s.map("Treeview", background=[("selected", "#cfe3da")], foreground=[("selected", INK)])

    # ------------------------------------------------------------ cabecera
    def _build_header(self):
        top = ttk.Frame(self, padding=(18, 14, 18, 6))
        top.pack(fill="x")
        left = ttk.Frame(top)
        left.pack(side="left")
        ttk.Label(left, text=APP_NAME, font=self.font_title).pack(anchor="w")
        self.status = ttk.Label(left, text="Listo.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(top)
        right.pack(side="right")
        self.btn_run = ttk.Button(right, text="Revisar ahora", style="Accent.TButton",
                                  command=self.run_now)
        self.btn_run.pack(side="right", padx=(10, 0))
        ttk.Checkbutton(right, text="Modo automático (cada 5 min)", variable=self.auto,
                        command=self._toggle_auto).pack(side="right")

        self.hint = ttk.Label(self, text="", style="Warn.TLabel", padding=(18, 0, 18, 4))
        self.hint.pack(fill="x")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._build_meetings()
        self._build_summaries()
        self._build_settings()
        self._build_log()

    # ------------------------------------------------------------ reuniones
    def _build_meetings(self):
        tab = ttk.Frame(self.nb, style="Card.TFrame", padding=14)
        self.nb.add(tab, text="Próximas reuniones")

        ttk.Label(tab, text="Elige una reunión y decide quién va. Lo que no toques sigue tus reglas.",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(0, 8))

        cols = ("hora", "titulo", "quien", "motivo")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="extended")
        for col, label, width, stretch in (("hora", "Cuándo", 120, False),
                                           ("titulo", "Reunión", 360, True),
                                           ("quien", "Quién va", 150, False),
                                           ("motivo", "Por qué", 260, True)):
            self.tree.heading(col, text=label, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="w")
        self.tree.tag_configure("bot", foreground=ACCENT)
        self.tree.tag_configure("yo", foreground=INK)
        self.tree.tag_configure("nolink", foreground=MUTED)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._toggle_selected())

        self.empty = ttk.Label(tab, text="", style="CardMuted.TLabel")
        self.empty.pack(anchor="w", pady=(6, 0))

        bar = ttk.Frame(tab, style="Card.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="🤖  Mandar el bot", command=lambda: self._override(True)).pack(side="left")
        ttk.Button(bar, text="🙋  Voy yo", command=lambda: self._override(False)).pack(side="left", padx=6)
        ttk.Button(bar, text="Usar mis reglas", command=lambda: self._override(None)).pack(side="left")
        ttk.Button(bar, text="Abrir reunión", command=self._open_meeting).pack(side="right")

    def _fill_meetings(self, items):
        self.items = items
        self.tree.delete(*self.tree.get_children())
        today = dt.date.today()
        for it in items:
            start = core.parse_dt(it["inicio"]).astimezone()
            day = "Hoy" if start.date() == today else (
                "Mañana" if start.date() == today + dt.timedelta(days=1) else f"{start:%d/%m}")
            if it["bot"]:
                who, tag = ("🤖 Bot (agendado)" if it["programado"] else "🤖 Bot"), "bot"
            elif not it["url"]:
                who, tag = "🙋 Tú (sin enlace)", "nolink"
            else:
                who, tag = "🙋 Tú", "yo"
            reason = it["motivo"] + ("  ✎" if it["override"] is not None else "")
            self.tree.insert("", "end", iid=it["key"], tags=(tag,),
                             values=(f"{day} {start:%H:%M}", it["titulo"], who, reason))
        n_bot = sum(1 for it in items if it["bot"])
        self.empty.configure(
            text="No tienes reuniones en las próximas horas." if not items
            else f"{len(items)} reuniones · el bot irá a {n_bot}.")

    def _selected_keys(self):
        return list(self.tree.selection())

    def _override(self, value):
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo(APP_NAME, "Primero elige una o más reuniones de la lista.")
            return
        for key in keys:
            core.set_override(key, value)
        # Si el modo automático está activo, se aplica de inmediato (agenda o cancela bots).
        self.run_now() if self.auto.get() else self.preview()

    def _toggle_selected(self):
        keys = self._selected_keys()
        if keys:
            current = next((it for it in self.items if it["key"] == keys[0]), None)
            if current:
                self._override(not current["bot"])

    def _open_meeting(self):
        keys = self._selected_keys()
        it = next((it for it in self.items if keys and it["key"] == keys[0]), None)
        if it and it["url"]:
            open_path(it["url"])

    # ------------------------------------------------------------ resúmenes
    def _build_summaries(self):
        tab = ttk.Frame(self.nb, style="Card.TFrame", padding=14)
        self.nb.add(tab, text="Resúmenes")
        pane = ttk.PanedWindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane, style="Card.TFrame")
        self.sum_list = tk.Listbox(left, width=36, activestyle="none", borderwidth=0, highlightthickness=1,
                                   highlightcolor=LINE, highlightbackground=LINE,
                                   selectbackground="#cfe3da", selectforeground=INK, bg=CARD, fg=INK)
        self.sum_list.pack(fill="both", expand=True)
        self.sum_list.bind("<<ListboxSelect>>", lambda e: self._show_summary())
        row = ttk.Frame(left, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Actualizar", command=self._refresh_summaries).pack(side="left")
        ttk.Button(row, text="Abrir carpeta", command=self._open_summaries_dir).pack(side="left", padx=6)
        pane.add(left, weight=1)

        self.sum_text = ScrolledText(pane, wrap="word", borderwidth=0, padx=16, pady=12,
                                     font=tkfont.nametofont("TkDefaultFont"), spacing1=2,
                                     bg=CARD, fg=INK, highlightthickness=1,
                                     highlightbackground=LINE, highlightcolor=LINE)
        self.sum_text.tag_configure("h1", font=self.font_title, spacing3=6)
        self.sum_text.tag_configure("h2", font=self.font_h, foreground=ACCENT, spacing1=10, spacing3=3)
        self.sum_text.tag_configure("muted", foreground=MUTED)
        self.sum_text.configure(state="disabled")
        pane.add(self.sum_text, weight=3)
        self.sum_files = []

    def _refresh_summaries(self):
        files = sorted(core.SUMMARIES_DIR.glob("*.md"), reverse=True) if core.SUMMARIES_DIR.exists() else []
        self.sum_files = files
        self.sum_list.delete(0, "end")
        for f in files:
            try:
                when = dt.datetime.strptime(f.stem[:15], "%Y-%m-%d_%H%M").strftime("%d/%m %H:%M")
                title = f.stem[16:].replace("-", " ")
            except ValueError:
                when, title = "", f.stem
            self.sum_list.insert("end", f"  {when}   {title}")
        if not files:
            self._set_summary_text("# Aún no hay resúmenes\n\nCuando el bot termine su primera reunión, "
                                   "el resumen aparecerá aquí y también te llegará por correo.")

    def _show_summary(self):
        sel = self.sum_list.curselection()
        if sel:
            self._set_summary_text(self.sum_files[sel[0]].read_text(encoding="utf-8"))

    def _set_summary_text(self, md):
        t = self.sum_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for line in md.splitlines():
            if line.startswith("# "):
                t.insert("end", line[2:] + "\n", "h1")
            elif line.startswith("## "):
                t.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("_") and line.endswith("_"):
                t.insert("end", line.strip("_") + "\n", "muted")
            else:
                if line.lstrip().startswith(("- ", "* ")):
                    line = line.replace("- ", "•  ", 1).replace("* ", "•  ", 1)
                t.insert("end", line.replace("**", "") + "\n")
        t.configure(state="disabled")

    def _open_summaries_dir(self):
        core.SUMMARIES_DIR.mkdir(exist_ok=True)
        open_path(core.SUMMARIES_DIR)

    # -------------------------------------------------------------- ajustes
    def _build_settings(self):
        tab = ttk.Frame(self.nb, style="Card.TFrame", padding=14)
        self.nb.add(tab, text="Ajustes")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        self.v = {}

        acc = ttk.LabelFrame(tab, text="Tú y tus claves", padding=12)
        acc.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        rules = ttk.LabelFrame(tab, text="¿Cuándo va el bot?", padding=12)
        rules.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tab.rowconfigure(0, weight=1)

        def field(parent, row, key, label, hint=None, secret=False, values=None):
            ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            if values:
                w = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
            else:
                w = ttk.Entry(parent, textvariable=var, show="•" if secret else "")
            w.grid(row=row, column=1, sticky="ew", pady=4, padx=(10, 0))
            if hint:
                ttk.Label(parent, text=hint, style="CardMuted.TLabel", font=self.font_small).grid(
                    row=row + 1, column=1, sticky="w", padx=(10, 0))
            self.v[key] = var
            if secret:
                self.secret_entries.append(w)
            return w

        self.secret_entries = []
        acc.columnconfigure(1, weight=1)
        field(acc, 0, "mi_nombre", "Tu nombre", "Como apareces en las reuniones")
        field(acc, 2, "mi_correo", "Tu correo", "Donde llegan los resúmenes")
        field(acc, 4, "nombre_bot", "Nombre del bot", "Lo que verán los demás")
        field(acc, 6, "RECALL_API_KEY", "Clave Recall.ai", secret=True)
        field(acc, 7, "RECALL_REGION", "Región Recall", values=core.REGIONS)
        field(acc, 8, "ANTHROPIC_API_KEY", "Clave Anthropic", secret=True)
        self.show_keys = tk.BooleanVar(value=False)
        ttk.Checkbutton(acc, text="Mostrar claves", variable=self.show_keys, style="Card.TCheckbutton",
                        command=self._toggle_secrets).grid(row=9, column=1, sticky="w", padx=(10, 0))

        ttk.Separator(acc).grid(row=10, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(acc, text="Google", style="Card.TLabel", font=self.font_h).grid(row=11, column=0, sticky="w")
        self.google_status = ttk.Label(acc, text="", style="CardMuted.TLabel")
        self.google_status.grid(row=11, column=1, sticky="w", padx=(10, 0))
        gbar = ttk.Frame(acc, style="Card.TFrame")
        gbar.grid(row=12, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(gbar, text="Elegir credentials.json…", command=self._pick_credentials).pack(side="left")
        ttk.Button(gbar, text="Conectar Google", command=self._connect_google).pack(side="left", padx=6)

        rules.columnconfigure(1, weight=1)
        field(rules, 0, "marcadores", "Siempre el bot si el título tiene",
              "Separado por comas. Ej: [bot], #bot")
        field(rules, 2, "titulo_contiene", "El bot va si el título tiene")
        field(rules, 3, "nunca_si_titulo_contiene", "Nunca el bot si el título tiene")
        field(rules, 4, "colores", "Colores que mandan el bot",
              "IDs de color de Google: 8 = Grafito (gris), 11 = Tomate…")
        field(rules, 6, "minimo_asistentes", "Mínimo de asistentes", "Con menos gente, vas tú")
        field(rules, 8, "horizonte_horas", "Mirar hacia adelante (horas)")
        field(rules, 9, "idioma", "Idioma de las reuniones", values=["es", "en", "pt"])
        self.v_excl = tk.BooleanVar(value=True)
        ttk.Checkbutton(rules, text="Si la organizo yo, voy yo", variable=self.v_excl,
                        style="Card.TCheckbutton").grid(row=10, column=1, sticky="w", padx=(10, 0), pady=6)

        bottom = ttk.Frame(tab, style="Card.TFrame")
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(bottom, text="Guardar ajustes", style="Accent.TButton",
                   command=self._save_settings).pack(side="left")
        ttk.Button(bottom, text="Abrir carpeta de datos",
                   command=lambda: open_path(core.BASE)).pack(side="left", padx=8)
        ttk.Label(bottom, text=f"Datos en: {core.BASE}", style="CardMuted.TLabel",
                  font=self.font_small).pack(side="right")

    def _toggle_secrets(self):
        for w in self.secret_entries:
            w.configure(show="" if self.show_keys.get() else "•")

    def _load_settings(self):
        cfg = core.read_config_raw()
        env = dotenv_values(core.BASE / ".env") if (core.BASE / ".env").exists() else {}
        f = cfg["filtro"]
        self.v["mi_nombre"].set(cfg.get("mi_nombre", ""))
        self.v["mi_correo"].set(cfg.get("mi_correo", ""))
        self.v["nombre_bot"].set(cfg.get("nombre_bot", ""))
        self.v["RECALL_API_KEY"].set(env.get("RECALL_API_KEY", "") or "")
        self.v["RECALL_REGION"].set(env.get("RECALL_REGION") or "us-west-2")
        self.v["ANTHROPIC_API_KEY"].set(env.get("ANTHROPIC_API_KEY", "") or "")
        for k in ("marcadores", "titulo_contiene", "nunca_si_titulo_contiene", "colores"):
            self.v[k].set(", ".join(str(x) for x in f.get(k) or []))
        self.v["minimo_asistentes"].set(str(f.get("minimo_asistentes", 3)))
        self.v["horizonte_horas"].set(str(cfg.get("horizonte_horas", 24)))
        lang = ((cfg.get("transcripcion") or {}).get("recallai_streaming") or {}).get("language_code", "es")
        self.v["idioma"].set(lang)
        self.v_excl.set(bool(f.get("excluir_si_organizo", True)))
        self._refresh_google_status()

    def _save_settings(self, quiet=False):
        try:
            min_att = int(self.v["minimo_asistentes"].get() or 3)
            horizon = int(self.v["horizonte_horas"].get() or 24)
        except ValueError:
            messagebox.showerror(APP_NAME, "Mínimo de asistentes y horas deben ser números.")
            return False
        cfg = core.read_config_raw()
        cfg["mi_nombre"] = self.v["mi_nombre"].get().strip()
        cfg["mi_correo"] = self.v["mi_correo"].get().strip()
        cfg["nombre_bot"] = self.v["nombre_bot"].get().strip()
        cfg["horizonte_horas"] = horizon
        cfg["app_automatico"] = bool(self.auto.get())
        cfg.setdefault("transcripcion", {}).setdefault("recallai_streaming", {})
        cfg["transcripcion"]["recallai_streaming"]["language_code"] = self.v["idioma"].get() or "es"
        cfg["transcripcion"]["recallai_streaming"].setdefault("mode", "prioritize_accuracy")
        for k in ("marcadores", "titulo_contiene", "nunca_si_titulo_contiene", "colores"):
            cfg["filtro"][k] = split_list(self.v[k].get())
        cfg["filtro"]["minimo_asistentes"] = min_att
        cfg["filtro"]["excluir_si_organizo"] = bool(self.v_excl.get())
        core.save_config(cfg)

        env_lines = [f"{k}={self.v[k].get().strip()}"
                     for k in ("RECALL_API_KEY", "RECALL_REGION", "ANTHROPIC_API_KEY")]
        env_path = core.BASE / ".env"
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        core.reload_env()
        self._refresh_setup_hint()
        if not quiet:
            self._set_status("Ajustes guardados.")
            if self._ready():
                self.preview()
        return True

    def _refresh_google_status(self):
        if core.google_connected():
            self.google_status.configure(text="✓ Conectado")
        elif (core.BASE / "credentials.json").exists():
            self.google_status.configure(text="credentials.json listo · falta conectar")
        else:
            self.google_status.configure(text="Falta credentials.json")

    def _pick_credentials(self):
        path = filedialog.askopenfilename(title="Elige el credentials.json de Google",
                                          filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if path:
            shutil.copyfile(path, core.BASE / "credentials.json")
            self._refresh_google_status()
            self._refresh_setup_hint()

    def _connect_google(self):
        self._set_status("Se abrió el navegador: autoriza tu cuenta de Google…")
        self._run_bg("google", core.cmd_login)

    # ------------------------------------------------------------- registro
    def _build_log(self):
        tab = ttk.Frame(self.nb, style="Card.TFrame", padding=14)
        self.nb.add(tab, text="Registro")
        self.log_text = ScrolledText(tab, wrap="word", borderwidth=0, bg=CARD, fg=INK,
                                     font=("TkFixedFont", 9), highlightthickness=0)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        if core.LOG_FILE.exists():
            tail = core.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            for line in tail:
                self._append_log(line)

    def _append_log(self, line):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------- estado general
    def _missing(self):
        cfg = core.read_config_raw()
        env = dotenv_values(core.BASE / ".env") if (core.BASE / ".env").exists() else {}
        missing = []
        if not cfg.get("mi_nombre") or not cfg.get("mi_correo"):
            missing.append("tu nombre y correo")
        if not env.get("RECALL_API_KEY"):
            missing.append("clave de Recall.ai")
        if not env.get("ANTHROPIC_API_KEY"):
            missing.append("clave de Anthropic")
        if not core.google_connected():
            missing.append("conectar Google")
        return missing

    def _ready(self):
        return not self._missing()

    def _refresh_setup_hint(self):
        missing = self._missing()
        self.hint.configure(text=("Para empezar, en Ajustes falta: " + ", ".join(missing) + ".")
                            if missing else "")
        self.btn_run.state(["disabled"] if missing else ["!disabled"])
        if missing:
            self.nb.select(2)

    def _set_status(self, text):
        self.status.configure(text=text)

    def _status_idle(self):
        if self.auto.get() and self.next_run:
            self._set_status(f"Modo automático activo · próxima revisión {self.next_run:%H:%M}")
        else:
            self._set_status("Modo automático apagado. Las reuniones solo se revisan al pulsar el botón.")

    # ------------------------------------------------------- trabajo de fondo
    def _run_bg(self, kind, fn):
        if self.busy:
            return
        self.busy = True
        self.btn_run.state(["disabled"])

        def work():
            try:
                self.events.put(("done", kind, fn()))
            except core.AsistenteError as e:
                self.events.put(("error", kind, str(e)))
            except Exception as e:  # noqa: BLE001
                self.events.put(("error", kind, f"{type(e).__name__}: {e}"))
            finally:
                self.events.put(("idle", None, None))

        threading.Thread(target=work, daemon=True).start()

    def preview(self):
        self._set_status("Leyendo tu calendario…")
        self._run_bg("preview", lambda: (core.reload_env(), core.upcoming(core.load_config()))[1])

    def run_now(self):
        if not self._save_settings(quiet=True):
            return
        self._set_status("Revisando calendario y reuniones terminadas…")
        self.next_run = dt.datetime.now() + INTERVAL
        self._run_bg("cycle", core.run_cycle)

    def _schedule_now(self):
        self.next_run = dt.datetime.now()

    def _toggle_auto(self):
        if self.auto.get() and not self._ready():
            self.auto.set(False)
            messagebox.showinfo(APP_NAME, "Antes completa los ajustes: " + ", ".join(self._missing()) + ".")
            return
        self._save_settings(quiet=True)
        if self.auto.get():
            self._schedule_now()
        else:
            self.next_run = None
            self._status_idle()

    def _tick(self):
        if self.auto.get() and self.next_run and dt.datetime.now() >= self.next_run and not self.busy:
            self.run_now()
        self.after(5000, self._tick)

    def _drain_events(self):
        try:
            while True:
                kind, what, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(what)
                elif kind == "done":
                    if what in ("preview", "cycle"):
                        self._fill_meetings(payload)
                        self._refresh_summaries()
                    if what == "google":
                        self._refresh_google_status()
                        self._refresh_setup_hint()
                        if self._ready():
                            self.nb.select(0)
                            self.preview_after_idle = True
                elif kind == "error":
                    self._append_log(f"[error] {payload}")
                    messagebox.showerror(APP_NAME, payload) if what != "cycle" or not self.auto.get() \
                        else None
                    self._set_status(f"⚠️ {payload}")
                elif kind == "idle":
                    self.busy = False
                    if not self._missing():
                        self.btn_run.state(["!disabled"])
                    if not str(self.status.cget("text")).startswith("⚠️"):
                        self._status_idle()
                    if getattr(self, "preview_after_idle", False):
                        self.preview_after_idle = False
                        self.preview()
        except queue.Empty:
            pass
        self.after(150, self._drain_events)

    def _on_close(self):
        if self.auto.get():
            keep = messagebox.askyesnocancel(
                APP_NAME,
                "El modo automático está activo.\n\n"
                "Sí: minimizar y seguir trabajando en segundo plano.\n"
                "No: cerrar la app (no se mandarán más bots ni resúmenes).")
            if keep is None:
                return
            if keep:
                self.iconify()
                return
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
