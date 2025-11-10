from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional

from ..settings import settings


def send_email(subject: str, body: str, to_emails: Iterable[str], cc_emails: Optional[Iterable[str]] = None) -> None:
    to_list = list(dict.fromkeys(to_emails))
    cc_list = list(dict.fromkeys(cc_emails or []))
    if not to_list:
        return

    if not settings.smtp_host:
        print("EMAIL SEND (mock)")
        print(json.dumps({"subject": subject, "body": body, "to": to_list, "cc": cc_list}, indent=2))
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(to_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_username and settings.smtp_password:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
