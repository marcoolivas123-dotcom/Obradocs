"""
Notificaciones — ObraDocs
Detects critical alerts in agent output and dispatches notifications via
email (SMTP), WhatsApp (Twilio), or generic webhooks (Slack, Teams, etc.).

Configuration via environment variables:
    OBRADOCS_NOTIFY_EMAIL_TO      Recipient email address
    OBRADOCS_NOTIFY_EMAIL_FROM    Sender address
    OBRADOCS_SMTP_HOST            SMTP server host (default: smtp.gmail.com)
    OBRADOCS_SMTP_PORT            SMTP port (default: 587)
    OBRADOCS_SMTP_USER            SMTP username
    OBRADOCS_SMTP_PASSWORD        SMTP password

    OBRADOCS_TWILIO_ACCOUNT_SID   Twilio account SID
    OBRADOCS_TWILIO_AUTH_TOKEN    Twilio auth token
    OBRADOCS_TWILIO_FROM          WhatsApp sender (e.g. whatsapp:+14155238886)
    OBRADOCS_TWILIO_TO            WhatsApp recipient (e.g. whatsapp:+521XXXXXXXXXX)

    OBRADOCS_WEBHOOK_URL          Webhook URL (Slack/Teams/custom)

Usage:
    from agents.notificaciones import dispatch

    # From free-text agent output
    dispatch(text=agent_output, source="Obra")

    # From structured JSON report
    dispatch(report=structured_report, source="Ventas")

    # From supervisor dashboard
    dispatch(report=supervisor_report, source="Supervisor")
"""

import os
import re
import json
import smtplib
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _ascii(s: str) -> str:
    """Strip diacritics so 'CRÍTICA' → 'CRITICA' for safe ASCII comparisons."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class Alert:
    nivel: str          # "CRÍTICA", "MEDIA", "BAJA"
    modulo: str         # e.g. "Obra", "Ventas", "Corretaje"
    descripcion: str
    accion: str = ""

    @property
    def is_critical(self) -> bool:
        return self.nivel.upper() in ("CRÍTICA", "CRITICA", "CRITICAL")

    def __str__(self) -> str:
        base = f"[{self.nivel}] {self.modulo}: {self.descripcion}"
        if self.accion:
            base += f"\n  → Acción: {self.accion}"
        return base


@dataclass
class NotificationResult:
    channel: str
    success: bool
    error: str = ""


# ── Alert extraction ─────────────────────────────────────────────────────────

def extract_alerts_from_text(text: str, source: str = "") -> list[Alert]:
    """Parse [ALERTA CRÍTICA], [ALERTA MEDIA], [ALERTA BAJA] markers from free text.

    Uses split-based parsing to avoid regex accent-sensitivity issues.
    """
    alerts: list[Alert] = []

    # Split on any [ALERTA ...] tag — capture the tag itself
    parts = re.split(r"(\[ALERTA[^\]]*\])", text, flags=re.IGNORECASE)
    # parts layout: [prefix, tag1, content1, tag2, content2, ...]
    i = 1
    while i < len(parts) - 1:
        tag = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""

        tag_ascii = _ascii(tag.upper())
        if "CRIT" in tag_ascii:
            nivel = "CRÍTICA"
        elif "MEDIA" in tag_ascii:
            nivel = "MEDIA"
        elif "BAJA" in tag_ascii:
            nivel = "BAJA"
        else:
            i += 2
            continue

        # Truncate content at the next section/ok marker
        stop = re.search(r"\[(?:OK|SECCI)", content, re.IGNORECASE)
        if stop:
            content = content[: stop.start()]

        # Extract [ACCIÓN] from the content block
        accion_match = re.search(r"\[ACCI[ÓO]N\](.*?)(?=\[|\Z)", content, re.IGNORECASE | re.DOTALL)
        accion = accion_match.group(1).strip() if accion_match else ""
        descripcion = re.sub(r"\[ACCI[ÓO]N\].*?(?=\[|\Z)", "", content, flags=re.IGNORECASE | re.DOTALL).strip()

        alerts.append(Alert(nivel=nivel, modulo=source, descripcion=descripcion, accion=accion))
        i += 2
    return alerts


def extract_alerts_from_report(report: dict, source: str = "") -> list[Alert]:
    """Extract alerts from a structured JSON report (obra, ventas, or supervisor)."""
    alerts: list[Alert] = []

    # Supervisor dashboard: report["alertas_criticas"]
    for a in report.get("alertas_criticas", []):
        alerts.append(Alert(
            nivel="CRÍTICA",
            modulo=a.get("modulo", source),
            descripcion=a.get("descripcion", ""),
            accion=a.get("accion_inmediata", ""),
        ))

    # Obra structured: report["proyectos"][*]["alertas"]
    for proyecto in report.get("proyectos", []):
        for a in proyecto.get("alertas", []):
            alerts.append(Alert(
                nivel=a.get("nivel", "BAJA").replace("CRÍTICA", "CRÍTICA"),
                modulo=source or proyecto.get("nombre", "Obra"),
                descripcion=a.get("descripcion", ""),
                accion=a.get("accion", ""),
            ))

    # Ventas structured: report["alertas"]
    for a in report.get("alertas", []):
        alerts.append(Alert(
            nivel=a.get("nivel", "BAJA"),
            modulo=source,
            descripcion=a.get("descripcion", ""),
            accion=a.get("accion", ""),
        ))

    return alerts


# ── Notification channels ────────────────────────────────────────────────────

def _send_email(subject: str, body: str) -> NotificationResult:
    to_addr = os.getenv("OBRADOCS_NOTIFY_EMAIL_TO", "")
    from_addr = os.getenv("OBRADOCS_NOTIFY_EMAIL_FROM", "")
    host = os.getenv("OBRADOCS_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("OBRADOCS_SMTP_PORT", "587"))
    user = os.getenv("OBRADOCS_SMTP_USER", "")
    password = os.getenv("OBRADOCS_SMTP_PASSWORD", "")

    if not all([to_addr, from_addr, user, password]):
        return NotificationResult("email", False, "Missing SMTP environment variables")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, to_addr, msg.as_string())
        return NotificationResult("email", True)
    except Exception as exc:
        return NotificationResult("email", False, str(exc))


def _send_whatsapp(message: str) -> NotificationResult:
    account_sid = os.getenv("OBRADOCS_TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("OBRADOCS_TWILIO_AUTH_TOKEN", "")
    from_wa = os.getenv("OBRADOCS_TWILIO_FROM", "")
    to_wa = os.getenv("OBRADOCS_TWILIO_TO", "")

    if not all([account_sid, auth_token, from_wa, to_wa]):
        return NotificationResult("whatsapp", False, "Missing Twilio environment variables")

    try:
        import base64
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        payload = f"From={urllib.parse.quote(from_wa)}&To={urllib.parse.quote(to_wa)}&Body={urllib.parse.quote(message)}"
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                return NotificationResult("whatsapp", True)
            return NotificationResult("whatsapp", False, f"HTTP {resp.status}")
    except Exception as exc:
        return NotificationResult("whatsapp", False, str(exc))


def _send_webhook(payload: dict) -> NotificationResult:
    webhook_url = os.getenv("OBRADOCS_WEBHOOK_URL", "")
    if not webhook_url:
        return NotificationResult("webhook", False, "OBRADOCS_WEBHOOK_URL not set")
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201, 202, 204):
                return NotificationResult("webhook", True)
            return NotificationResult("webhook", False, f"HTTP {resp.status}")
    except Exception as exc:
        return NotificationResult("webhook", False, str(exc))


# ── Main dispatch ────────────────────────────────────────────────────────────

def dispatch(
    text: str = "",
    report: dict = None,
    source: str = "ObraDocs",
    only_critical: bool = True,
    channels: list[str] = None,
) -> list[NotificationResult]:
    """
    Extract alerts from agent output and send notifications via configured channels.

    Args:
        text: Free-text agent output to parse for alert markers.
        report: Structured JSON report dict (from structured=True run or supervisor).
        source: Module name used to label alerts (e.g. "Obra", "Ventas").
        only_critical: If True, only send notifications for CRÍTICA-level alerts.
        channels: List of channels to use: ["email", "whatsapp", "webhook"].
                  Defaults to all channels that have their env vars configured.

    Returns:
        List of NotificationResult, one per channel attempted.
    """
    import urllib.parse  # noqa: needed inside _send_whatsapp

    alerts: list[Alert] = []
    if report:
        alerts.extend(extract_alerts_from_report(report, source))
    if text:
        alerts.extend(extract_alerts_from_text(text, source))

    if only_critical:
        alerts = [a for a in alerts if a.is_critical]

    if not alerts:
        return []

    subject = f"🚨 ObraDocs — {len(alerts)} alerta(s) crítica(s) en {source}"
    body_lines = [f"ObraDocs detectó {len(alerts)} alerta(s) crítica(s):\n"]
    for a in alerts:
        body_lines.append(str(a))
    body = "\n\n".join(body_lines)

    webhook_payload = {
        "source": source,
        "critical_alerts": len(alerts),
        "alerts": [
            {
                "nivel": a.nivel,
                "modulo": a.modulo,
                "descripcion": a.descripcion,
                "accion": a.accion,
            }
            for a in alerts
        ],
        "summary": subject,
    }

    available = channels or ["email", "whatsapp", "webhook"]
    results: list[NotificationResult] = []

    if "email" in available:
        results.append(_send_email(subject, body))
    if "whatsapp" in available:
        short_msg = f"🚨 {subject}\n\n" + "\n".join(
            f"• {a.descripcion[:120]}" for a in alerts[:5]
        )
        results.append(_send_whatsapp(short_msg))
    if "webhook" in available:
        results.append(_send_webhook(webhook_payload))

    return results


if __name__ == "__main__":
    # Dry-run: extract alerts from sample text without actually sending
    sample = """
[SECCIÓN: Proyectos de Obra]
[ALERTA CRÍTICA] Resi. Bosques: margen neto 9.1% por debajo del umbral de 12%.
[ACCIÓN] Revisar contratos de subcontratistas y renegociar precios de materiales.
[ALERTA MEDIA] Torre Cumbres: desviación de costo +4.2%, cerca del umbral de 5%.
[ACCIÓN] Auditar partidas de acabados y ajustar presupuesto de contingencia.
[OK] Torre Cumbres: avance físico alineado con financiero, curva S dentro de rango.
    """

    alerts = extract_alerts_from_text(sample, source="Obra")
    print(f"Alertas detectadas: {len(alerts)}")
    for a in alerts:
        print(f"\n{a}")

    # To actually send, set env vars and call:
    # results = dispatch(text=sample, source="Obra")
