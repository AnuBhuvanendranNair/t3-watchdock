"""E-mail and Microsoft Teams notifications."""
import html
import json
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from .core import SMTP_PASSWORD_FILE, TEAMS_FILE, config, lock, log, save_config, write_secret


# ---------------------------------------------------------------- email
def email_cfg():
    e = config().get("email") or {}
    return {"enabled": bool(e.get("enabled")), "host": e.get("host", ""), "port": int(e.get("port") or 587),
            "security": e.get("security", "starttls"), "user": e.get("user", ""),
            "from": e.get("from", ""), "to": e.get("to", [])}


def smtp_password():
    if SMTP_PASSWORD_FILE.exists():
        return SMTP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    return ""


def save_email(b):
    to = [a.strip() for a in re.split(r"[,;\s]+", b.get("to") or "") if a.strip()]
    sec = b.get("security", "starttls")
    if sec not in ("starttls", "ssl", "none"):
        raise RuntimeError("Security must be starttls, ssl or none")
    e = {"enabled": bool(b.get("enabled")), "host": (b.get("host") or "").strip(),
         "port": int(b.get("port") or (465 if sec == "ssl" else 587)), "security": sec,
         "user": (b.get("user") or "").strip(), "from": (b.get("from") or "").strip(), "to": to}
    if e["enabled"] and not (e["host"] and e["from"] and to):
        raise RuntimeError("SMTP host, sender and at least one recipient are required")
    with lock:
        cfg = config()
        cfg["email"] = e
        save_config(cfg)
    pw = b.get("password")
    if b.get("clear_password"):
        SMTP_PASSWORD_FILE.unlink(missing_ok=True)
    elif pw:                                   # empty field = keep stored password
        write_secret(SMTP_PASSWORD_FILE, pw)
    log("Email settings saved")
    return e


def send_mail(subject, text, cfg=None, html_body=None):
    e = cfg or email_cfg()
    if not (e["host"] and e["from"] and e["to"]):
        raise RuntimeError("Email not configured (SMTP host, sender, recipients)")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, e["from"], ", ".join(e["to"])
    msg.set_content(text)
    # HTML copy of the same text: mail clients and relays (e.g. Brevo) render plain text as HTML,
    # which collapses the column spacing and swallows anything that looks like a tag
    msg.add_alternative(html_body or '<pre style="font-family:Consolas,Menlo,monospace;font-size:13px;'
                        'white-space:pre-wrap">' + html.escape(text) + "</pre>", subtype="html")
    ctx = ssl.create_default_context()
    if e["security"] == "ssl":
        s = smtplib.SMTP_SSL(e["host"], e["port"], timeout=30, context=ctx)
    else:
        s = smtplib.SMTP(e["host"], e["port"], timeout=30)
    with s:
        if e["security"] == "starttls":
            s.starttls(context=ctx)
        if e["user"]:
            s.login(e["user"], smtp_password())
        s.send_message(msg)


# ---------------------------------------------------------------- Microsoft Teams
def teams_url():
    return TEAMS_FILE.read_text(encoding="utf-8").strip() if TEAMS_FILE.exists() else ""


def teams_cfg():
    return {"enabled": bool((config().get("teams") or {}).get("enabled"))}


def save_teams(b):
    url = (b.get("url") or "").strip()
    if b.get("clear_url"):
        TEAMS_FILE.unlink(missing_ok=True)
    elif url:                                  # empty field = keep stored URL
        if not url.startswith("https://") or any(c.isspace() for c in url):
            raise RuntimeError("Webhook URL must start with https:// and contain no spaces")
        write_secret(TEAMS_FILE, url)
    enabled = bool(b.get("enabled"))
    if enabled and not teams_url():
        raise RuntimeError("Webhook URL is required")
    with lock:
        cfg = config()
        cfg["teams"] = {"enabled": enabled}
        save_config(cfg)
    log("Teams settings saved")
    return teams_cfg()


def send_teams(title, intro, facts, link=None, link_title="Open pipeline", code=None, sections=None):
    """Post an Adaptive Card (format accepted by Teams Workflows and legacy incoming webhooks)."""
    url = teams_url()
    if not url:
        raise RuntimeError("No Teams webhook URL stored")
    card = {"type": "AdaptiveCard", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4", "body": [
                {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
                {"type": "TextBlock", "text": intro, "wrap": True}]}
    for sec in _sections(facts, sections):
        card["body"] += _teams_section(sec)
    if code:                                   # monospace block to copy (e.g. update commands)
        card["body"].append({"type": "TextBlock", "text": code, "fontType": "Monospace", "wrap": True,
                             "separator": True})
    if link:
        card["actions"] = [{"type": "Action.OpenUrl", "title": link_title, "url": link}]
    body = json.dumps({"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Teams HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Teams not reachable: {e.reason}") from None


# ---------------------------------------------------------------- message layout
# A section is {"title", "note", "cols", "rows"}. A cell is text, (text, tone) or a dict:
#   {"text", "sub": grey second line, "tone": "bad"|"warn"|"ok"|"muted", "tag": small label, "num": right-aligned,
#    "mono": monospace}. Plain facts [(label, value), ...] become one section without title and header.
# Optional "widths" (e.g. ["30%", "16%"]) keeps the first columns aligned across sections.
# stats = [(label, value, tone)] for the number row at the top of the email.
INK, MUTED, LINE, BG = "#101828", "#667085", "#eaecf0", "#f5f6f8"
FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "SFMono-Regular,Consolas,Menlo,monospace"
TONES = {"bad": ("#d92d20", "#fef3f2", "Attention"), "warn": ("#b54708", "#fffaeb", "Warning"),
         "ok": ("#067647", "#ecfdf3", "Good"), "muted": ("#98a2b3", "#f2f4f7", "Default")}


def _sections(facts, sections):
    out = [{"rows": [list(f) for f in facts]}] if facts else []
    return out + [x for x in (sections or []) if x.get("rows")]


def _cell(c):
    if isinstance(c, dict):
        return dict(c, text=str(c.get("text", "")))
    if isinstance(c, tuple):
        return {"text": str(c[0]), "tone": c[1]}
    return {"text": str(c)}


def _plain(c):
    c = _cell(c)
    return " – ".join(x for x in (c["text"], c.get("tag", ""), c.get("sub", "")) if x)


def _mail_text(intro, facts, sections, link, code, stats=None):
    """Plain text: one block per section, columns padded so they line up."""
    parts = [intro]
    if stats:
        parts.append("   ".join(f"{label}: {value}" for label, value, *_ in stats))
    for sec in _sections(facts, sections):
        rows = ([sec["cols"]] if sec.get("cols") else []) + [[_plain(c) for c in r] for r in sec["rows"]]
        widths = [max(len(r[i]) for r in rows if i < len(r)) for i in range(len(rows[0]))]
        block = [sec["title"], "-" * len(sec["title"])] if sec.get("title") else []
        if sec.get("note"):
            block.append(sec["note"])
        block += ["  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in rows]
        parts.append("\n".join(block))
    if link:
        parts.append(f"Link: {link}")
    if code:
        parts.append(code)
    return "\n\n".join(parts) + "\n"


def _html_cell(c, first_plain):
    """One <td>. Inline styles only: Outlook ignores <style> blocks."""
    e, c = html.escape, _cell(c)
    fg = TONES[c["tone"]][0] if c.get("tone") else INK
    st = f"padding:10px 12px 10px 0;border-top:1px solid {LINE};vertical-align:top;color:{fg};"
    if c.get("num"):
        st += "text-align:right;font-variant-numeric:tabular-nums;"
    if c.get("mono"):
        st += f"font-family:{MONO};font-size:12px;"
    if first_plain:
        st += f"color:{MUTED};width:30%;"
    body = e(c["text"]) or "&nbsp;"
    if c.get("tag"):
        tfg, tbg, _ = TONES[c.get("tag_tone", "warn")]
        body += (f' <span style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:4px;'
                 f'font-family:{FONT};font-size:11px;font-weight:600;color:{tfg};background:{tbg}">{e(c["tag"])}</span>')
    if c.get("sub"):
        body += f'<div style="margin-top:2px;font-size:12px;color:{MUTED}">{e(c["sub"])}</div>'
    return f'<td style="{st}">{body}</td>'


def _mail_html(title, intro, facts, sections, link, link_title, code, stats=None, headline=None):
    """Email layout: 800px card on a grey page, built from tables so Outlook renders it too."""
    e = html.escape
    out = [f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" '
           f'style="background:{BG};font-family:{FONT};color:{INK}"><tr><td align="center" style="padding:24px 12px">'
           f'<table role="presentation" width="800" cellpadding="0" cellspacing="0" '
           f'style="width:100%;max-width:800px;background:#ffffff;border:1px solid {LINE};border-radius:8px">'
           f'<tr><td style="padding:28px 32px 8px">'
           f'<div style="font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:{MUTED}">'
           f'T3 Watchdock</div>'
           f'<div style="margin-top:6px;font-size:22px;line-height:28px;font-weight:600">{e(headline or title)}</div>'
           f'<div style="margin-top:6px;font-size:14px;line-height:20px;color:{MUTED}">{e(intro)}</div></td></tr>']
    if stats:
        tds = "".join(
            f'<td width="{100 // len(stats)}%" style="padding:14px 16px;border-left:{"0" if i == 0 else "1px"} solid {LINE}">'
            f'<div style="font-size:24px;line-height:28px;font-weight:600;'
            f'color:{TONES[tone][0] if tone else INK}">{e(str(value))}</div>'
            f'<div style="margin-top:2px;font-size:12px;color:{MUTED}">{e(label)}</div></td>'
            for i, (label, value, tone) in enumerate(stats))
        out.append(f'<tr><td style="padding:16px 32px 0"><table role="presentation" width="100%" cellpadding="0" '
                   f'cellspacing="0" style="border:1px solid {LINE};border-radius:8px"><tr>{tds}</tr></table></td></tr>')
    for sec in _sections(facts, sections):
        part = ['<tr><td style="padding:24px 32px 0">']
        if sec.get("title"):
            part.append(f'<div style="font-size:15px;font-weight:600">{e(sec["title"])}</div>')
        if sec.get("note"):
            part.append(f'<div style="margin-top:2px;font-size:13px;color:{MUTED}">{e(sec["note"])}</div>')
        part.append('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                    'style="margin-top:8px;font-size:13px;line-height:18px;border-collapse:collapse">')
        if sec.get("cols"):
            nums = [_cell(c).get("num") for c in sec["rows"][0]]
            widths = list(sec.get("widths") or []) + [""] * len(sec["cols"])
            part.append("<tr>" + "".join(
                f'<th{f" width={chr(34)}{w}{chr(34)}" if w else ""} style="padding:0 12px 6px 0;font-size:11px;'
                f'font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:{MUTED};'
                f'text-align:{"right" if n else "left"}">{e(c)}</th>'
                for c, n, w in zip(sec["cols"], nums, widths)) + "</tr>")
        for r in sec["rows"]:
            part.append("<tr>" + "".join(_html_cell(c, not sec.get("cols") and i == 0)
                                         for i, c in enumerate(r)) + "</tr>")
        part.append("</table></td></tr>")
        out.append("".join(part))
    if code:
        out.append(f'<tr><td style="padding:24px 32px 0"><pre style="margin:0;padding:12px;background:{BG};'
                   f'border-radius:6px;font-family:{MONO};font-size:12px;white-space:pre-wrap">{e(code)}</pre></td></tr>')
    if link:
        out.append(f'<tr><td style="padding:28px 32px 0"><a href="{e(link)}" style="display:inline-block;'
                   f'padding:10px 16px;background:{INK};color:#ffffff;border-radius:6px;font-size:14px;'
                   f'font-weight:600;text-decoration:none">{e(link_title)}</a></td></tr>')
    out.append(f'<tr><td style="padding:28px 32px 24px;font-size:12px;color:{MUTED}">'
               f'Sent automatically by T3 Watchdock.</td></tr></table></td></tr></table>')
    return "".join(out)


def _teams_section(sec):
    """Adaptive Card 1.4 has no table: one ColumnSet per row (header row bold)."""
    body = []
    if sec.get("title"):
        body.append({"type": "TextBlock", "text": sec["title"], "weight": "Bolder", "wrap": True,
                     "separator": True, "spacing": "Medium"})
    if sec.get("note"):
        body.append({"type": "TextBlock", "text": sec["note"], "isSubtle": True, "wrap": True, "spacing": "None"})
    if not sec.get("cols"):                    # label/value pairs
        return body + [{"type": "FactSet", "facts": [{"title": _plain(r[0]), "value": " · ".join(
            _plain(c) for c in r[1:])} for r in sec["rows"]]}]

    def row(cells, head=False):
        cols = []
        for c in cells:
            c = _cell(c)
            items = [{"type": "TextBlock", "text": c["text"] + (f" ({c['tag']})" if c.get("tag") else "") or " ",
                      "wrap": True, "size": "Small"}]
            if head:
                items[0].update(weight="Bolder", isSubtle=True)
            if c.get("tone"):
                items[0]["color"] = TONES[c["tone"]][2]
            if c.get("num"):
                items[0]["horizontalAlignment"] = "Right"
            if c.get("sub"):
                items.append({"type": "TextBlock", "text": c["sub"], "wrap": True, "size": "Small",
                              "isSubtle": True, "spacing": "None"})
            cols.append({"type": "Column", "width": "stretch", "items": items})
        return {"type": "ColumnSet", "columns": cols, "spacing": "Small"}
    nums = [_cell(c).get("num") for c in sec["rows"][0]]
    return body + [row([{"text": c, "num": n} for c, n in zip(sec["cols"], nums)], True)] + [row(r) for r in sec["rows"]]


def notify_event(title, intro, facts, link=None, link_title="Open pipeline", code=None, sections=None,
                 stats=None, headline=None):
    """Send to every enabled channel (Teams, email); errors only go to the log."""
    if teams_cfg()["enabled"]:
        try:
            send_teams(title, intro, facts, link, link_title, code, sections)
            log(f"Teams message sent: {title}")
        except Exception as e:
            log(f"Teams message failed ({title}): {e}")
    if email_cfg()["enabled"]:
        try:
            send_mail("[T3 Watchdock] " + title, _mail_text(intro, facts, sections, link, code, stats),
                      html_body=_mail_html(title, intro, facts, sections, link, link_title, code, stats, headline))
            log(f"Email sent: {title}")
        except Exception as e:
            log(f"Email failed ({title}): {e}")
