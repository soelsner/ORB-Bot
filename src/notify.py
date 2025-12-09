import logging
from typing import Optional

logger = logging.getLogger(__name__)


def notify_slack(webhook: str, message: str) -> None:
    if not webhook:
        logger.info("Slack webhook not configured; skipping notification")
        return
    # Placeholder for Slack integration
    logger.info("Slack message: %s", message)


def notify_email(to_email: str, from_email: str, message: str) -> None:
    if not to_email:
        logger.info("Email recipient missing; skipping notification")
        return
    logger.info("Email to %s: %s", to_email, message)
