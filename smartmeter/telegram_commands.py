import logging
from telegram import Update
from telegram.ext import ContextTypes
from smartmeter.utils import Status

LOG = logging.getLogger("main")


def generate_status_message() -> str:
    """
    Generate the HTLM for the Telegram answer.
    """
    status = Status()
    output_lines = []
    output_lines.append(f"<b>Up since</b>: {status.system['up_since']}")
    output_lines.append("<b>Load status</b>")
    for load, status in status.loads.items():
        output_lines.append(f"{load}: {'on' if status else 'off'}")

    return "\n".join(output_lines)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the status of the application."""
    await update.message.reply_html(generate_status_message())
