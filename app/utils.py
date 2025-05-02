import contextlib
import logging
import multiprocessing
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx
from fastapi import HTTPException, status
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.conf import Settings

logger = logging.getLogger(__name__)


def dateformat(date_obj: datetime | None) -> str:
    return date_obj.strftime("%-d %B %Y") if date_obj else ""


env = Environment(
    loader=FileSystemLoader(
        os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "templates",
            "emails",
        ),
    ),
    autoescape=select_autoescape(),
)

env.filters["dateformat"] = dateformat


@contextlib.contextmanager
def wrap_http_error_in_502(base_msg: str = "Error in FinOps for Cloud"):
    try:
        yield
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{base_msg}: {e.response.status_code} - {e.response.text}.",
        ) from e


@contextlib.contextmanager
def wrap_exc_in_http_response(
    exc_cls: type[Exception],
    error_msg: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
):
    try:
        yield
    except exc_cls as e:
        if error_msg is None:
            error_msg = str(e)

        logger.exception(
            f"{exc_cls.__name__} error was raised during an operation, "
            f"returning a {status_code} HTTP response: {error_msg}"
        )
        raise HTTPException(status_code=status_code, detail=error_msg) from e


def send_email(
    settings: Settings, recipient_email: str, recipient_name: str, subject: str, message: str
) -> None:
    sender_email = settings.smtp_sender_email
    sender_name = settings.smtp_sender_name

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender_email))
    msg["To"] = formataddr((recipient_name, recipient_email))

    html_part = MIMEText(message, "html")
    msg.attach(html_part)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())


def generate_invitation_email(id: str, name: str, token: str, expires: datetime):
    template = env.get_template("invitation.html.j2")
    return template.render(
        id=id,
        name=name,
        token=token,
        expires=expires,
    )


def get_default_number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1
