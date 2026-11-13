#!/usr/bin/env python3
"""
Asistente para reuniones inútiles — núcleo (lo usan la app de escritorio y la línea de comandos).

1. Lee tu Google Calendar y detecta las reuniones que marcaste como "inútiles".
2. Envía un bot de Recall.ai (Zoom, Google Meet, Microsoft Teams, Webex) en tu lugar.
3. Cuando la reunión termina, descarga la transcripción, la resume con Claude
   y te la manda por correo (Gmail), con la transcripción completa adjunta.

Línea de comandos (opcional; la app de escritorio hace lo mismo con botones):
    python asistente.py login
    python asistente.py programar --simular
    python asistente.py ejecutar
"""
import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
import markdown
import requests
import yaml
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def _default_home():
    if os.environ.get("ASISTENTE_HOME"):
        return Path(os.environ["ASISTENTE_HOME"]).expanduser()
    if getattr(sys, "frozen", False):  # app empaquetada: datos en la carpeta del usuario
        return Path.home() / "AsistenteReuniones"
    return Path(__file__).resolve().parent


BASE = _default_home()
BASE.mkdir(parents=True, exist_ok=True)
STATE_FILE = BASE / "estado.json"
SUMMARIES_DIR = BASE / "resumenes"
LOG_FILE = BASE / "log.txt"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
REGIONS = ["us-west-2", "us-east-1", "eu-central-1", "ap-northeast-1"]

# Si la reunión empieza en más de esto, el bot se agenda con join_at; si no, entra ya.
MIN_LEAD = dt.timedelta(minutes=10)
# Si pasado este tiempo desde que terminó no hay transcripción, se da por fallida.
MAX_WAIT = dt.timedelta(hours=3)

MEETING_PATTERNS = [
    r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}",
    r"https://(?:[\w-]+\.)?zoom\.us/(?:j|my|w)/[^\s\"'<>]+",
    r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+",
    r"https://teams\.microsoft\.com/meet/[^\s\"'<>]+",
    r"https://teams\.live\.com/meet/[^\s\"'<>]+",
    r"https://[\w-]+\.webex\.com/[^\s\"'<>]+",
]

DEFAULT_CONFIG = {
    "mi_nombre": "",
    "mi_correo": "",
    "nombre_bot": "",
    "calendario": "primary",
    "horizonte_horas": 24,
    "modelo": "claude-sonnet-5-5",
    "transcripcion": {"recallai_streaming": {"mode": "prioritize_accuracy", "language_code": "es"}},
    "filtro": {
        "marcadores": ["[bot]", "#bot"],
        "nunca_si_titulo_contiene": ["1:1", "1-1", "entrevista", "cliente", "evaluación", "médico"],
        "excluir_si_organizo": True,
        "minimo_asistentes": 3,
        "colores": ["8"],
        "titulo_contiene": ["weekly", "sync", "status", "seguimiento", "all hands",
                            "reunión de avance", "actualización"],
    },
}


class AsistenteError(Exception):
    """Problema de configuración o de conexión que se le muestra al usuario."""


# ---------------------------------------------------------------- utilidades

LOG_HANDLERS = []  # la app de escritorio se suscribe aquí


def log(msg):
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    for handler in LOG_HANDLERS:
        handler(line)


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def parse_dt(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def reload_env():
    load_dotenv(BASE / ".env", override=True)


def read_config_raw():
    """Config tal cual está en disco, completada con los valores por defecto."""
    path = BASE / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = cfg or {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in cfg.items():
        if k == "filtro" and isinstance(v, dict):
            merged["filtro"].update(v)
        else:
            merged[k] = v
    return merged


def save_config(cfg):
    (BASE / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_config():
    cfg = read_config_raw()
    for k, label in (("mi_nombre", "tu nombre"), ("mi_correo", "tu correo")):
        if not cfg.get(k):
            raise AsistenteError(f"Falta {label} en los ajustes.")
    return cfg


def load_state():
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    state.setdefault("bots", {})
    state.setdefault("overrides", {})  # clave de reunión -> True (bot) / False (voy yo)
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def set_override(key, value):
    """value: True = mandar bot, False = voy yo, None = usar reglas."""
    state = load_state()
    if value is None:
        state["overrides"].pop(key, None)
    else:
        state["overrides"][key] = bool(value)
    save_state(state)


# ------------------------------------------------------------------- Google

def google_connected():
    return (BASE / "token.json").exists()


def google_creds(interactive=False):
    token = BASE / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not interactive:
            raise AsistenteError("Google no está conectado. Ve a Ajustes → Conectar Google.")
        secret = BASE / "credentials.json"
        if not secret.exists():
            raise AsistenteError("Falta credentials.json (cliente OAuth de Google). "
                                 "Elígelo en Ajustes; el README explica cómo obtenerlo.")
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
        creds = flow.run_local_server(port=0)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def meeting_url(ev):
    if ev.get("hangoutLink"):
        return ev["hangoutLink"]
    for ep in (ev.get("conferenceData") or {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video" and ep.get("uri", "").startswith("https://"):
            return ep["uri"]
    text = html.unescape(" ".join([ev.get("location") or "", ev.get("description") or ""]))
    for pattern in MEETING_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(0).rstrip(".,;)]")
    return None


def is_useless(ev, cfg):
    """Devuelve (True/False, motivo) según las reglas de config.yaml -> filtro."""
    f = cfg.get("filtro") or {}
    title = (ev.get("summary") or "").lower()
    attendees = ev.get("attendees") or []
    me = next((a for a in attendees if a.get("self")), None)

    if me and me.get("responseStatus") == "declined":
        return False, "la rechazaste"
    # Un marcador explícito manda sobre todo lo demás.
    if any(m.lower() in title for m in f.get("marcadores") or []):
        return True, "marcada a mano"
    if any(k.lower() in title for k in f.get("nunca_si_titulo_contiene") or []):
        return False, "palabra excluida en el título"
    if f.get("excluir_si_organizo", True) and (ev.get("organizer") or {}).get("self"):
        return False, "la organizas tú"
    if attendees and len(attendees) < int(f.get("minimo_asistentes", 3)):
        return False, "muy pocos asistentes"
    if str(ev.get("colorId", "")) in [str(c) for c in f.get("colores") or []]:
        return True, "color del evento"
    if any(k.lower() in title for k in f.get("titulo_contiene") or []):
        return True, "palabra clave en el título"
    return False, "no cumple ninguna regla"


def decide(ev, cfg, overrides, key):
    if key in overrides:
        return (True, "elegiste mandar el bot") if overrides[key] else (False, "elegiste ir tú")
    return is_useless(ev, cfg)


def send_email(creds, to, subject, md_text, transcript=None, attachment_name="transcripcion.txt"):
    msg = MIMEMultipart("mixed")
    msg["To"] = to
    msg["Subject"] = subject
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(md_text, "plain", "utf-8"))
    body.attach(MIMEText(markdown.markdown(md_text, extensions=["tables"]), "html", "utf-8"))
    msg.attach(body)
    if transcript:
        part = MIMEApplication(transcript.encode("utf-8"), Name=attachment_name)
        part["Content-Disposition"] = f'attachment; filename="{attachment_name}"'
        msg.attach(part)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


# ---------------------------------------------------------------- Recall.ai

def recall(method, path, **kw):
    key = os.environ.get("RECALL_API_KEY", "")
    if not key:
        raise AsistenteError("Falta la clave de Recall.ai en los ajustes.")
    region = os.environ.get("RECALL_REGION", "us-west-2")
    r = requests.request(
        method,
        f"https://{region}.recall.ai/api/v1{path}",
        headers={"Authorization": f"Token {key}", "accept": "application/json"},
        timeout=30,
        **kw,
    )
    if r.status_code >= 400:
        raise AsistenteError(f"Recall.ai respondió {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def create_bot(url, start, title, cfg):
    body = {
        "meeting_url": url,
        "bot_name": cfg.get("nombre_bot") or f"Notas de {cfg['mi_nombre']}",
        "recording_config": {
            "transcript": {
                "provider": cfg.get("transcripcion")
                or DEFAULT_CONFIG["transcripcion"]
            }
        },
        "metadata": {"titulo": title[:200]},
    }
    if start - now_utc() > MIN_LEAD:
        body["join_at"] = start.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return recall("POST", "/bot/", json=body)


def format_transcript(segments):
    lines, last = [], None
    for seg in segments or []:
        name = (seg.get("participant") or {}).get("name") or "Desconocido"
        words = seg.get("words") or []
        text = " ".join(w.get("text", "") for w in words).strip()
        if not text:
            continue
        if name == last:
            lines[-1] += " " + text
            continue
        ts = (words[0].get("start_timestamp") or {}).get("relative")
        stamp = f"[{int(ts // 60):02d}:{int(ts % 60):02d}] " if isinstance(ts, (int, float)) else ""
        lines.append(f"{stamp}{name}: {text}")
        last = name
    return "\n".join(lines)


# ------------------------------------------------------------------- Claude

SYSTEM_PROMPT = """Eres el asistente personal de {me}. {me} no asistió a esta reunión y \
mandó un bot a grabarla. Tu trabajo es que {me} sepa en 1 minuto todo lo que le importa.

Reglas:
- Usa solo lo que está en la transcripción. No inventes nada.
- La transcripción automática tiene errores; si algo es ambiguo, dilo.
- Escribe en español, directo y sin relleno.
- Si una sección no tiene contenido, escribe "Nada".
- Presta especial atención a cualquier mención de {me} (o variantes de su nombre)."""

USER_PROMPT = """Reunión: {title}
Fecha: {date}

<transcripcion>
{transcript}
</transcripcion>

Devuelve el resumen en Markdown con exactamente estas secciones:

## En 30 segundos
(máximo 3 viñetas con lo esencial)

## Decisiones
## Tareas y responsables
(marca en **negrita** las que son de {me} o le afectan)

## Te mencionaron
(cada vez que alguien nombró a {me} o le hizo una pregunta, con la marca de tiempo)

## ¿Tienes que hacer algo?
(Sí o No, y qué exactamente, con plazo si se dijo)

## Veredicto
(una sola línea honesta, con algo de humor: ¿esta reunión pudo ser un correo?)"""


def summarize(cfg, title, date, transcript):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AsistenteError("Falta la clave de Anthropic en los ajustes.")
    client = anthropic.Anthropic()
    me = cfg["mi_nombre"]
    msg = client.messages.create(
        model=cfg.get("modelo", "claude-sonnet-5-5"),
        max_tokens=2500,
        system=SYSTEM_PROMPT.format(me=me),
        messages=[{
            "role": "user",
            "content": USER_PROMPT.format(title=title, date=date, transcript=transcript, me=me),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# ----------------------------------------------------------------- comandos

def cmd_login(cfg=None):
    google_creds(interactive=True)
    log("Google conectado (Calendar de solo lectura + envío por Gmail).")


def upcoming(cfg, state=None):
    """Reuniones próximas con la decisión de quién va. No modifica nada."""
    state = state or load_state()
    creds = google_creds()
    cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
    start = now_utc()
    end = start + dt.timedelta(hours=int(cfg.get("horizonte_horas", 24)))
    events = cal.events().list(
        calendarId=cfg.get("calendario", "primary"),
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])

    items = []
    for ev in events:
        begins = (ev.get("start") or {}).get("dateTime")
        if not begins or ev.get("status") == "cancelled":
            continue  # eventos de día completo o cancelados
        key = f"{ev['id']}|{begins}"
        bot, reason = decide(ev, cfg, state["overrides"], key)
        url = meeting_url(ev)
        if bot and not url:
            bot, reason = False, "sin enlace de Zoom/Meet/Teams/Webex"
        items.append({
            "key": key,
            "titulo": ev.get("summary") or "(sin título)",
            "inicio": begins,
            "fin": (ev.get("end") or {}).get("dateTime", begins),
            "url": url,
            "bot": bot,
            "motivo": reason,
            "override": state["overrides"].get(key),
            "programado": key in state["bots"],
        })
    return items


def cmd_programar(cfg, simular=False):
    """Agenda bots (o cancela los que ya no corresponden). Devuelve la lista de reuniones."""
    state = load_state()
    items = upcoming(cfg, state)
    for it in items:
        key, title = it["key"], it["titulo"]
        begins_dt = parse_dt(it["inicio"])
        scheduled = state["bots"].get(key)

        if not it["bot"]:
            # Si había un bot y cambiaste de opinión (y aún no empieza), se cancela.
            if scheduled and scheduled["estado"] == "programado" and begins_dt > now_utc():
                if simular:
                    log(f"Cancelaría el bot de: {title}")
                    continue
                try:
                    recall("DELETE", f"/bot/{scheduled['bot_id']}/")
                    log(f"Bot cancelado: {title}  ({it['motivo']})")
                except AsistenteError as e:
                    log(f"No pude cancelar el bot de '{title}': {e}")
                    continue
                del state["bots"][key]
                save_state(state)
                it["programado"] = False
            continue

        if scheduled:
            continue
        if simular:
            log(f"Mandaría bot: {title}  [{begins_dt.astimezone():%d/%m %H:%M}]  ({it['motivo']})")
            continue
        try:
            bot = create_bot(it["url"], begins_dt, title, cfg)
        except AsistenteError as e:
            log(f"ERROR creando bot para '{title}': {e}")
            continue
        state["bots"][key] = {
            "bot_id": bot["id"],
            "titulo": title,
            "inicio": it["inicio"],
            "fin": it["fin"],
            "estado": "programado",
        }
        save_state(state)
        it["programado"] = True
        log(f"Bot programado: {title}  [{begins_dt.astimezone():%d/%m %H:%M}]  ({it['motivo']})")
    return items


def cmd_procesar(cfg):
    state = load_state()
    creds = None
    for key, item in list(state["bots"].items()):
        if item["estado"] in ("enviado", "fallido"):
            continue
        try:
            bot = recall("GET", f"/bot/{item['bot_id']}/")
        except Exception as e:  # noqa: BLE001
            log(f"No pude consultar el bot de '{item['titulo']}': {e}")
            continue

        changes = bot.get("status_changes") or []
        last = changes[-1] if changes else {}
        code = last.get("code")
        too_late = now_utc() - parse_dt(item["fin"]) > MAX_WAIT

        problem = None
        transcript_url = None
        if code == "fatal":
            problem = f"el bot no pudo grabar ({last.get('sub_code') or 'error'})"
        elif code == "done":
            recs = bot.get("recordings") or []
            tr = ((recs[0].get("media_shortcuts") or {}).get("transcript") if recs else None) or {}
            transcript_url = (tr.get("data") or {}).get("download_url")
            if not recs:
                problem = "el bot terminó sin grabación (¿no lo dejaron entrar?)"
            elif not transcript_url and too_late:
                problem = "la transcripción nunca quedó lista"
        elif too_late:
            problem = f"el bot quedó en estado '{code}' tras terminar la reunión"

        if not problem and not transcript_url:
            continue  # todavía en curso o procesando

        creds = creds or google_creds()
        title = item["titulo"]
        date = parse_dt(item["inicio"]).astimezone()
        date_txt = f"{date:%d/%m/%Y %H:%M}"

        if problem:
            send_email(creds, cfg["mi_correo"], f"⚠️ Sin resumen: {title}",
                       f"No hay resumen de **{title}** ({date_txt}): {problem}.\n\n"
                       "Quizás convenga pedirle a alguien que te cuente qué pasó.")
            item["estado"] = "fallido"
            save_state(state)
            log(f"Fallido: {title} — {problem}")
            continue

        segments = requests.get(transcript_url, timeout=120).json()
        transcript = format_transcript(segments)
        if not transcript.strip():
            summary = "La reunión no tiene conversación transcrita: nadie habló o el bot no escuchó audio."
        else:
            summary = summarize(cfg, title, date_txt, transcript)

        SUMMARIES_DIR.mkdir(exist_ok=True)
        slug = re.sub(r"[^\w-]+", "-", title.lower()).strip("-")[:60] or "reunion"
        (SUMMARIES_DIR / f"{date:%Y-%m-%d_%H%M}_{slug}.md").write_text(
            f"# {title}\n_{date_txt}_\n\n{summary}\n\n---\n\n## Transcripción\n\n{transcript}\n",
            encoding="utf-8",
        )
        send_email(creds, cfg["mi_correo"], f"📝 Resumen: {title}", summary,
                   transcript=transcript or None, attachment_name=f"transcripcion_{slug}.txt")
        item["estado"] = "enviado"
        save_state(state)
        log(f"Resumen enviado: {title}")

    # Limpia del estado lo que tenga más de 7 días.
    cutoff = now_utc() - dt.timedelta(days=7)
    state["bots"] = {
        k: v for k, v in state["bots"].items()
        if parse_dt(v["inicio"]) > cutoff or v["estado"] not in ("enviado", "fallido")
    }
    state["overrides"] = {
        k: v for k, v in state["overrides"].items() if parse_dt(k.split("|", 1)[1]) > cutoff
    }
    save_state(state)


def run_cycle(simular=False):
    """Una pasada completa: lo que hace el modo automático cada 5 minutos."""
    reload_env()
    cfg = load_config()
    items = cmd_programar(cfg, simular=simular)
    if not simular:
        cmd_procesar(cfg)
    return items


def main():
    parser = argparse.ArgumentParser(description="Asistente para reuniones inútiles")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Autoriza tu cuenta de Google")
    p = sub.add_parser("programar", help="Programa bots para las reuniones inútiles próximas")
    p.add_argument("--simular", action="store_true", help="Solo muestra qué haría")
    sub.add_parser("procesar", help="Resume y envía las reuniones terminadas")
    sub.add_parser("ejecutar", help="programar + procesar (para cron)")
    args = parser.parse_args()

    reload_env()
    try:
        if args.cmd == "login":
            cmd_login()
        elif args.cmd == "programar":
            cmd_programar(load_config(), simular=args.simular)
        elif args.cmd == "procesar":
            cmd_procesar(load_config())
        else:
            run_cycle()
    except AsistenteError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
