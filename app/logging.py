import logging.config

from rich.console import Console
from rich.highlighter import ReprHighlighter
from rich.theme import Theme

from app.conf import Settings
from app.db import models


class FFCOpsHighlighter(ReprHighlighter):
    prefixes = (
        models.Account.PK_PREFIX,
        models.Actor.PK_PREFIX,
        models.ChargesFile.PK_PREFIX,
        models.Entitlement.PK_PREFIX,
        models.Organization.PK_PREFIX,
        models.System.PK_PREFIX,
        models.User.PK_PREFIX,
    )
    highlights = ReprHighlighter.highlights + [
        rf"(?P<ffcops_id>(?:{'|'.join(prefixes)})(?:-\d{{4}})*)"
    ]


console = Console(
    highlighter=FFCOpsHighlighter(),
    theme=Theme({"repr.ffcops_id": "bold light_salmon3"}),
)


def get_logging_config(settings: Settings) -> dict:
    log_level = "DEBUG" if settings.debug else "INFO"
    handler = "rich" if settings.cli_rich_logging else "console"
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{asctime} {name} {levelname} (pid: {process}) {message}",
                "style": "{",
            },
            "rich": {
                "format": "{name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
                "stream": "ext://sys.stderr",
            },
            "rich": {
                "class": "rich.logging.RichHandler",
                "level": log_level,
                "formatter": "rich",
                "console": console,
                "log_time_format": lambda x: x.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "rich_tracebacks": True,
                "highlighter": FFCOpsHighlighter(),
            },
        },
        "root": {
            "handlers": ["rich"],
            "level": "WARNING",
        },
        "loggers": {
            "gunicorn.access": {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
            "gunicorn.error": {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
            "app": {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    return logging_config


def setup_logging(settings: Settings) -> None:
    logging_config = get_logging_config(settings)
    logging.config.dictConfig(logging_config)
