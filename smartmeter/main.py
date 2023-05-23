import asyncio
import sys
import os
import logging
from smartmeter.utils import parse_cli, load_config, init_logging, update_log_config
import multiprocessing as mp
import configparser
from typing import Optional
from smartmeter.digimeter import read_serial, fake_serial
from smartmeter.influx import DbInflux
from smartmeter.csv_writer import CSVWriter
from smartmeter.aux import LoadManager, Display, Buttons, StatusLed, CurrentSensors
from telegram.ext import Application, CommandHandler
from smartmeter import telegram_commands
from datetime import datetime
from smartmeter.utils import Status

try:
    import gpiozero as gpio
except ImportError:
    pass

LOG = logging.getLogger("main")


def not_on_a_pi():
    """Report if we are not a Raspberry PI."""
    try:
        if os.environ["GPIOZERO_PIN_FACTORY"] == "mock":
            return True
    except KeyError:
        pass

    return False


def start_serial_reader(
    log_cfg: configparser.SectionProxy, cfg: configparser.SectionProxy, msg_q: mp.Queue
) -> None:
    """Start the serial reader process."""
    new_log_config = update_log_config(log_cfg, cfg)
    log = init_logging(
        filename="digimeter.log",
        logpath=new_log_config.get("logpath"),
        log_to_stdout=new_log_config.getboolean("log_to_stdout"),
        keep=new_log_config.getint("keep"),
        size=new_log_config.get("size"),
        loglevel=new_log_config.get("loglevel"),
        name="digimeter",
    )
    log.info("--- Start ---")
    read_serial(
        msg_q=msg_q,
        port=cfg.get("port"),
        baudrate=cfg.getint("baudrate"),
        bytesize=cfg.getint("bytesize"),
        parity=cfg.get("parity"),
        stopbits=cfg.getint("stopbits"),
    )


async def display() -> None:
    """
    Display data when the info button is pressed,
    """
    disp = Display()
    bttns = Buttons()
    activated = False
    data = Status()

    while True:
        try:
            if bttns.info_button.is_pressed and not activated:
                activated = True
                LOG.debug("Info button is pressed.")
                await disp.cycle(
                    data.sensors["current_car"],
                    0,
                    data.sensors["current_vpp"],
                    0
                )
                activated = False

        except Exception:
            LOG.exception("Uncaught exception in display co routine!")
            activated = False

        await asyncio.sleep(0.1)


async def status_led() -> None:
    """
    Activates the status led.
    """
    led = StatusLed()
    status = Status()
    injected_power = 1.5  # Kw

    while True:

        if not led.status and status.meter.get('actual_total_injection', 0) > injected_power:
            LOG.debug("Switching status led on, injected power > %skW.", injected_power)
            led.on()
        elif led.status and status.meter.get('actual_total_injection', 0) <= injected_power:
            LOG.debug("Switching status led off, injected power <= %skW.", injected_power)
            led.off()

        await asyncio.sleep(0.1)


def read_current_sensors() -> None:
    """
    Update the Status sungleton with current information.
    """
    status = Status()
    cs = CurrentSensors()
    car_value = cs.load_current()
    vpp_value = cs.vpp_current()
    LOG.debug('Reading current sensors - car: %s, vpp: %s', car_value, vpp_value)
    status.sensors["current_car"] = car_value
    status.sensors["current_vvp"] = vpp_value


async def dispatcher(
    msg_q: mp.Queue,
    influx: Optional[DbInflux],
    csv_writer: Optional[CSVWriter],
    load_manager: Optional[LoadManager],
) -> None:
    """
    Dispatcher gets data from the queue and feeds it to
    the different tasks.
    """
    LOG.info("Starting dispatcher.")
    status = Status()

    while True:
        try:
            if not msg_q.empty():
                data = msg_q.get()
                status.meter = data

                if influx:
                    await influx.write(data)

                if csv_writer:
                    csv_writer.write(data)

                if load_manager:
                    load_manager.process(data)

                read_current_sensors()

            else:
                await asyncio.sleep(0.1)

        except Exception:
            LOG.exception("Unexpected error in the dispatcher!")
            await asyncio.sleep(0.1)


async def start_telegram(token: str) -> None:
    """Telegram integration."""
    telegram_bot = Application.builder().token(token).build()
    telegram_bot.add_handler(CommandHandler("status", telegram_commands.status))
    await telegram_bot.initialize()
    await telegram_bot.start()
    await telegram_bot.updater.start_polling()


def run() -> None:
    """Run the app."""
    args = parse_cli(sys.argv[1:])
    config = load_config(args.configfile)
    msg_q = mp.Queue()

    log = init_logging(
        filename="smartmeter.log",
        logpath=config["logging"]["logpath"],
        log_to_stdout=config.getboolean("logging", "log_to_stdout"),
        keep=int(config["logging"]["keep"]),
        size=config["logging"]["size"],
        loglevel=config["logging"]["loglevel"],
        name="main",
    )

    init_logging(
        filename="loadmanager.log",
        logpath=config["logging"]["logpath"],
        log_to_stdout=config.getboolean("logging", "log_to_stdout"),
        keep=int(config["logging"]["keep"]),
        size=config["logging"]["size"],
        loglevel=config["logging"]["loglevel"],
        name="loadmanager",
    )

    eventloop = asyncio.get_event_loop()

    log.info("--- Start ---")
    status = Status()
    status.system["up_since"] = datetime.isoformat(datetime.now())

    if not_on_a_pi():
        log.warning(
            "It seems we are not running on a Raspberry PI! Some data is mocked!"
        )

    LOG.info("Board info: {}".format(str(gpio.pi_info())))

    if not args.fake_serial:
        serial_reader = mp.Process(
            target=start_serial_reader,
            args=(config["logging"], config["digimeter"], msg_q),
        )
    else:
        serial_reader = mp.Process(
            target=fake_serial,
            args=(
                msg_q,
                args.fake_serial,
                True,
            ),
        )
    serial_reader.start()

    influx = None
    cfg = config["influx"]
    if cfg and cfg.getboolean("enabled"):
        LOG.info("InfluxDB is enabled.")
        influx = DbInflux(
            url=cfg.get("url"),
            token=cfg.get("token"),
            org=cfg.get("org"),
            bucket=cfg.get("bucket"),
            ssl_ca_cert=cfg.get("ssl_ca_cert"),
            verify_ssl=cfg.getboolean("verify_ssl", True),
            upload_interval=cfg.getint("upload_interval", 0),
        )

    csv_writer = None
    cfg = config["csv"]
    if cfg and cfg.getboolean("enabled"):
        LOG.info("CSV writer is enabled.")
        csv_writer = CSVWriter(
            prefix=cfg.get("file_prefix", "smartmeter"),
            path=cfg.get("file_path"),
            write_header=cfg.getboolean("write_header"),
            max_lines=cfg.getint("max_lines", 100),
            max_age=cfg.getint("max_age", 300),
            write_every=cfg.getint("write_every", 1),
        )

    # Get all the loads from the configfile.
    # Load sections start with 'load:'
    load_manager = None
    load_cfg = [config[s] for s in config.sections() if s.startswith("load")]
    if load_cfg:
        load_manager = LoadManager()
        LOG.info("Adding the loads to the loadmanager.")
        [load_manager.add_load(lds) for lds in load_cfg]
        LOG.debug("%s load added to the load manager.", load_manager.load_cnt)
    else:
        LOG.warning("No loads found in the config file!")

    # Telegram
    cfg = config['telegram']
    if cfg and cfg.getboolean("enabled"):
        LOG.info("Telegram is enabled.")
        asyncio.ensure_future(start_telegram(cfg.get("token")))

    asyncio.ensure_future(dispatcher(msg_q, influx, csv_writer, load_manager))

    if not not_on_a_pi():
        asyncio.ensure_future(display())

    asyncio.ensure_future(status_led())

    eventloop.run_forever()


if __name__ == "__main__":
    run()
