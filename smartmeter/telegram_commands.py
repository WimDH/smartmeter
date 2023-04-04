import logging
from smartmeter.utils import Status
from telegram import Update
from telegram.ext import ContextTypes

LOG = logging.getLogger("main")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the status of the application."""
    status = Status()
    await update.message.reply_text('Meter: %s\nLoad: %s' % (status.meter, status.load))
