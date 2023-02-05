import asyncio
import sys
import os
import logging
from smartmeter.utils import parse_cli, load_config, init_logging, update_log_config
import multiprocessing as mp
import configparser
from smartmeter.digimeter import read_serial, fake_serial
from smartmeter.influx import DbInflux
from smartmeter.csv_writer import CSVWriter

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


async def dispatcher(
    msg_q: mp.Queue,
    influx: DbInflux,
    csv_writer: CSVWriter
) -> None:
    """
    Dispatcher gets data from the queue and feeds it to
    the different tasks.
    """
    LOG.debug("Starting dispatcher.")

    while True:
        try:
            if not msg_q.empty():
                data = msg_q.get()
                LOG.debug("Got data from the queue: %s", data)

                if influx:
                    await influx.write(data)
                if csv_writer:
                    csv_writer.write(data)

            else:
                await asyncio.sleep(0.1)

        except Exception:
            log.exception("Unexpected error in the dispatcher!")
            await asyncio.sleep(0.1)


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
        name="main"
    )

    log.info("--- Start ---")

    if not_on_a_pi():
        log.warning(
            "It seems we are not running on a Raspberry PI! Some data is mocked!"
        )

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
        LOG.info("CSVWriter is enabled.")
        csv_writer = CSVWriter(
            prefix=cfg.get("file_prefix", "smartmeter"),
            path=cfg.get("file_path"),
            write_header=cfg.getboolean("write_header"),
            max_lines=cfg.getint("max_lines", 100),
            max_age=cfg.getint("max_age", 300),
            write_every=cfg.getint("write_every", 1),
        )

    eventloop = asyncio.get_event_loop()
    asyncio.ensure_future(dispatcher(msg_q, influx, csv_writer))

    # if not not_on_a_pi():
    #     asyncio.ensure_future(display)

    eventloop.run_forever()


if __name__ == "__main__":
    run()