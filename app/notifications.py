import logging

import httpx
from adaptive_cards import card_types as ct
from adaptive_cards.actions import ActionOpenUrl
from adaptive_cards.card import AdaptiveCard
from adaptive_cards.elements import TextBlock

from app.conf import get_settings

logger = logging.getLogger(__name__)


async def send_notification(
    title: str,
    text: str,
    title_color: ct.Colors = ct.Colors.DEFAULT,
    open_url: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.msteams_notifications_webhook_url:  # pragma: no cover
        logger.warning("MSTeams notifications are disabled.")
        return

    card_items = [
        TextBlock(
            text=title,
            size=ct.FontSize.LARGE,
            weight=ct.FontWeight.BOLDER,
            color=title_color,
        ),
        TextBlock(
            text=text,
            wrap=True,
            size=ct.FontSize.SMALL,
            color=ct.Colors.DEFAULT,
        ),
    ]
    if open_url:
        card_items.append(
            ActionOpenUrl(
                title="Open",
                url=open_url,
            )
        )

    version: str = "1.4"
    card: AdaptiveCard = AdaptiveCard.new().version(version).add_items(card_items).create()
    message = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card.to_dict(),
            }
        ],
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.msteams_notifications_webhook_url,
            json=message,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 202:
            logger.error(
                f"Failed to send notification to MSTeams: {response.status_code} - {response.text}"
            )


async def send_info(
    title: str,
    text: str,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f44d {title}",
        text,
        title_color=ct.Colors.ACCENT,
        open_url=open_url,
    )


async def send_warning(
    title: str,
    text: str,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\u2622 {title}",
        text,
        title_color=ct.Colors.WARNING,
        open_url=open_url,
    )


async def send_error(
    title: str,
    text: str,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f4a3 {title}",
        text,
        title_color=ct.Colors.ATTENTION,
        open_url=open_url,
    )


async def send_exception(
    title: str,
    text: str,
    open_url: str | None = None,
) -> None:
    await send_notification(
        f"\U0001f525 {title}", text, title_color=ct.Colors.ATTENTION, open_url=open_url
    )
