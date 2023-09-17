import logging
from telegram import Update
from telegram.ext import ContextTypes
from smartmeter.utils import Status, human_time_duration

LOG = logging.getLogger("main")


def generate_status_message() -> str:
    """
    Generate the HTLM for the Telegram answer.
    TODO: create test
    """
    status = Status()
    output_lines = ["<b>System</b>", f"up since: {status.system['up_since']}"]

    output_lines.append("<b>Load status</b>")

    for load_name, load_data in status.loads.items():
        load_stat = "ON" if load_data["state"] else "OFF"
        time_human = human_time_duration(load_data['current_state_time']) if load_data['current_state_time'] else "(no data)"
        output_lines.append(
            f"{load_name}: {load_stat} for {time_human}"
        )

    output_lines.append("<b>Meter data</b>")
    if status.meter["actual_total_consumption"] > 0:
        output_lines.append(f"Actual consumption: {status.meter['actual_total_consumption']} kW.")
    else:
        output_lines.append(f"Actual injection: {status.meter['actual_total_injection']} kW.")

    output_lines.append(
        f"Actual current L1/L2/L3: {status.meter['l1_current']}A/{status.meter['l2_current']}A/{status.meter['l3_current']}A .",
        "<b>Sensor data</b>",
        f"Current sensors: Car: {status.sensors['current_car']}A, VVP: {status.sensors['cuurent_vvp']}A."
    )

    return "\n".join(output_lines)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the status of the application."""
    LOG.info("Received request to send a status update.")
    await update.message.reply_html(generate_status_message())
