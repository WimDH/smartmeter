from crccheck.crc import Crc16Lha
import serial
import re
from typing import Optional
from serial.serialutil import SerialException
from queue import Queue
from datetime import datetime
from time import sleep
import time
from smartmeter.utils import autoformat
from dateutil import parser as dateutil_parser
import logging

LOG = logging.getLogger("digimeter")


START_OF_TELEGRAM = re.compile(r"^\/FLU\d{1}\\")
END_OF_TELEGRAM = re.compile(r"^![A-Z0-9]{4}")
FIELDS = [
    # (Field name, dictionary key, start position, end position)
    ("0-0:1.0.0", "timestamp", 10, 23),
    ("1-0:1.8.1", "total_consumption_day", 10, 20),
    ("1-0:1.8.2", "total_consumption_night", 10, 20),
    ("1-0:2.8.1", "total_injection_day", 10, 20),
    ("1-0:2.8.2", "total_injection_night", 10, 20),
    ("0-0:96.14.0", "actual_tariff", 12, 16),
    ("1-0:1.7.0", "actual_total_consumption", 10, 16),
    ("1-0:2.7.0", "actual_total_injection", 10, 16),
    ("1-0:21.7.0", "actual_l1_consumption", 11, 17),
    ("1-0:41.7.0", "actual_l2_consumption", 11, 17),
    ("1-0:61.7.0", "actual_l3_consumption", 11, 17),
    ("1-0:22.7.0", "actual_l1_injection", 11, 17),
    ("1-0:42.7.0", "actual_l2_injection", 11, 17),
    ("1-0:62.7.0", "actual_l3_injection", 11, 17),
    ("1-0:32.7.0", "l1_voltage", 11, 16),
    ("1-0:52.7.0", "l2_voltage", 11, 16),
    ("1-0:72.7.0", "l3_voltage", 11, 16),
    ("1-0:31.7.0", "l1_current", 11, 17),
    ("1-0:51.7.0", "l2_current", 11, 17),
    ("1-0:71.7.0", "l3_current", 11, 17),
    ("0-1:24.2.3", "total_gas_consumption", 26, 35),
    ("0-1:24.2.3", "gas_timestamp", 11, 24),
]


def calculate_timestamp_drift(ts_type: str, iso_8601_timestamp: str) -> int:
    """
    Calculates the drift between the system time and the telegram timestamp.
    Log a warning message when the drift is more than one minute. (Disabled)
    """
    local_timestamp = datetime.now().astimezone()
    telegram_timestamp = dateutil_parser.parse(iso_8601_timestamp)
    delta_seconds = int((local_timestamp - telegram_timestamp).total_seconds())
    # delta_human_readable = "{:0>8}".format(str(timedelta(seconds=delta_seconds)))
    #
    # log_msg = f"Timestamp for {ts_type} drift is: {delta_human_readable}."
    #
    # if delta_seconds < 60:
    #     LOG.debug(log_msg)
    # else:
    #     LOG.warning(log_msg)

    return delta_seconds


def convert_timestamp(timestamp: str, format: Optional[str] = None) -> str:
    """
    Convert a timestamp in the for of '211024195235S' in iso8601 format or
    CET/CEST format
    YYMMDDHHMMSS[WS]
    Last letter can be a S (summer) or a W (winter).

    format: None | iso8601
    """
    if timestamp == "":
        raise ValueError("Timestamp cannot be empty.")

    tz_hour_map = {"S": "02:00", "W": "01:00"}
    tz_zone_map = {"S": "CEST", "W": "CET"}
    year = "20" + timestamp[0:2]
    month = timestamp[2:4]
    day = timestamp[4:6]
    hour = timestamp[6:8]
    minute = timestamp[8:10]
    second = timestamp[10:12]
    tz_hours = tz_hour_map[timestamp[-1]]
    tz_zone = tz_zone_map[timestamp[-1]]

    if format == "iso8601":
        result = f"{year}-{month}-{day}T{hour}:{minute}:{second}+{tz_hours}"
    else:
        result = f"{year}-{month}-{day} {hour}:{minute}:{second} {tz_zone}"

    LOG.debug("Converted timestamp from %s to %s", timestamp, result)

    return result


def parse(raw_msg):
    """Parse the raw message."""

    LOG.debug("Parsing raw telegram.")

    msg = {"local_timestamp": datetime.now().isoformat()}

    for line in raw_msg.strip().splitlines():
        for code, key, start, end in FIELDS:
            if line.startswith(code):
                msg[key] = autoformat(line[start:end])

    return msg


def check_msg(raw_msg: bytearray) -> bool:
    """
    Check if the message is valid.
    The provided CRC should be the same as the calculated one.
    Return True
    """
    provided_crc: str = ""
    calculated_crc: str = ""

    # Find the end of message character '!'
    LOG.debug("Checking message CRC. Message length is %d.", len(raw_msg))
    pos = raw_msg.find(b"!")
    data = raw_msg[: pos + 1]

    try:
        provided_crc = hex(int(raw_msg[pos + 1 :].strip(), 16))  # noqa: E203
        calculated_crc = hex(Crc16Lha.calc(data))

    except ValueError:
        LOG.warning("Unable to calculate CRC! Provided value: %s.", provided_crc)
        return False

    except Exception:
        LOG.exception("Unexpected error in CRC calculation!")
        return False

    crc_match = calculated_crc == provided_crc
    if crc_match:
        LOG.debug("Telegram has a valid CRC.")
    else:
        LOG.warning(
            "Telegram has an invalid CRC! Provided: %s - Calculated: %s.",
            provided_crc,
            calculated_crc,
        )

    return crc_match


def read_serial(
    msg_q: Queue,
    port: str,
    baudrate: int,
    bytesize: int,
    parity: str,
    stopbits: int,
    _quit_after: Optional[int] = None,
) -> None:
    """
    Read from the serial port until a complete message is detected.
    When the message is complete, add ir to the msg Queue as a sting.
    _quit_after is only used during testing to break the infinite loop while reading from the serial port.
    """
    global log
    telegram_count: int = 0
    telegram_pointer: int = 0
    telegram_last_time = 0
    line: bytes
    start_of_telegram_detected: bool = False
    telegram: bytearray = bytearray()

    LOG.debug(
        "Open serial port '%s' with settings '%d,%d,%s,%d'.",
        port,
        baudrate,
        bytesize,
        parity,
        stopbits,
    )

    with serial.Serial(
        port, baudrate, bytesize, parity, stopbits, timeout=5
    ) as serial_port:
        LOG.debug("Reading from serial port '%s'.", port)
        while True:
            try:
                # Read data from port
                line = serial_port.readline()

                if START_OF_TELEGRAM.search(line.decode("ascii")):  # Start of message
                    LOG.debug("Start of message deteced.")
                    telegram = bytearray()
                    start_of_telegram_detected = True

                if start_of_telegram_detected:
                    telegram += line

                if END_OF_TELEGRAM.search(line.decode("ascii")):  # End of message
                    LOG.debug("End of message deteced.")
                    telegram_count += 1
                    start_of_telegram_detected = False
                    LOG.debug("Recorded a new telegram: %s", telegram.decode("ascii"))

                    if check_msg(telegram):
                        # If the CRC is correct, add it to the queue.
                        queue_data = parse(telegram.decode())
                        calculate_timestamp_drift(
                            "Electricity",
                            convert_timestamp(
                                queue_data.get("timestamp"), format="iso8601"
                            ),
                        )
                        LOG.debug("Adding parsed data to the queue.")
                        msg_q.put(queue_data)

            except SerialException:
                LOG.error("Error while reading serial port!")
                start_of_telegram_detected = False

            except UnicodeDecodeError as e:
                LOG.error("Could not decode line received from the serial port: %s", e)
                start_of_telegram_detected = False

            except Exception:
                LOG.exception("Uncaught exception while reading from the serial port!")
                pass

            if (
                int(time.monotonic()) % 60 == 0
                and int(time.monotonic()) - telegram_last_time > 5
            ):
                LOG.info(
                    "Received %d telegrams from the digital meter in the last minute.",
                    telegram_count - telegram_pointer,
                )
                telegram_pointer = telegram_count
                telegram_last_time = int(time.monotonic())

            if _quit_after and _quit_after == telegram_count:
                break


def fake_serial(
    msg_q: Queue,
    filename: str,
    wait: bool = True,
    run_forever: bool = True,
) -> None:
    """
    Read data from a file and write it to the queue.
    If wait is True, we wait one second between each telegram.
    If run_forever is True, restart when EOF is reached.
    """
    LOG.debug("Faking serial reader...")
    telegram = ""
    forever = True
    while forever:
        forever = forever & run_forever

        with open(filename) as fh:
            for line in fh.readlines():
                if START_OF_TELEGRAM.search(line):
                    telegram = line
                else:
                    telegram += line

                if END_OF_TELEGRAM.search(line):
                    LOG.debug("Creating mocked telegram.")
                    queue_data = parse(telegram)
                    msg_q.put_nowait(queue_data)
                    if wait is True:
                        sleep(1)

    return
