import re
import os
import argparse
import configparser
from typing import List, Union, Optional, Dict
import logging
from logging.handlers import RotatingFileHandler
from coloredlogs import ColoredFormatter


def autoformat(value: Union[str, int, float]) -> Union[str, int, float]:
    """Convert to str, int or float, based on the content."""
    if type(value) == str and re.match(r"^\d+$", value):
        return int(value)
    if type(value) == str and re.match(r"\d+\.\d+", value):
        return float(value)
    if type(value) == int or type(value) == float:
        return value

    return str(value)


def convert_from_human_readable(value: Union[str, int]) -> int:
    """
    Converts human readable formats to an integer.
    Supports only filesizes for the moment (1k = 1024 bytes).
    k = kilo
    M = mega
    G = giga
    """
    power = {"k": 1, "M": 2, "G": 3}

    if type(value) == int or (type(value) == str and value.isnumeric()):
        return int(value)
    elif type(value) == str and value[-1] in ["k", "M", "G"]:
        return int(value[:-1]) * (1024 ** power.get(value[-1], 0))
    else:
        raise ValueError(f"'{value}' is an unknown value.")


def parse_cli(cli_args: List) -> argparse.Namespace:
    """Process the CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Read and process data from the digital enery meter."
    )
    parser.add_argument("-c", "--config", dest="configfile", help="The config file.")
    parser.add_argument(
        "-f",
        "--fake",
        dest="fake_serial",
        help="Instead of reading the data from the serial port, you can specify a file with pre recorded data.",
    )
    return parser.parse_args(cli_args)


def load_config(configfile: str) -> configparser.ConfigParser:
    """
    Load the configfile and return the parsed content.
    """
    if os.path.exists(configfile):
        config = configparser.ConfigParser()
        config.read(configfile)

        return config

    else:
        raise FileNotFoundError(f"File '{configfile}'' not found!")


def init_logging(
    filename: str,
    logpath: str,
    log_to_stdout: bool = False,
    keep: int = 2,
    size: str = "1M",
    loglevel: str = "info",
    name: Optional[str] = None,
) -> logging.Logger:
    """
    Setup the logging targets.
    """
    if filename[-4:] != ".log":
        filename = filename + ".log"
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, loglevel.upper()))

    # Log to a file.
    file_handler = RotatingFileHandler(
        filename=os.path.join(logpath, filename),
        maxBytes=convert_from_human_readable(size),
        backupCount=keep,
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)

    # Log to stdout.
    if log_to_stdout:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            ColoredFormatter("%(asctime)s %(levelname)s [%(name)s]- %(message)s")
        )
        logger.addHandler(console_handler)

    return logger


def update_log_config(
    log_cfg: configparser.SectionProxy, cfg_x: configparser.SectionProxy
) -> configparser.SectionProxy:
    """Overwrites the log config with the items from cfg_x"""
    config = configparser.ConfigParser()
    cfg_dict = {}
    for key in log_cfg.keys():
        if key in cfg_x.keys():
            cfg_dict.update({key: cfg_x[key]})
        else:
            cfg_dict.update({key: log_cfg[key]})

    config["merged"] = cfg_dict
    return config["merged"]


class Borg:
    """A Borg Singleton."""

    _shared_state: Dict = {}

    def __init__(self) -> None:
        self.__dict__ = self._shared_state


class Status(Borg):
    """An object to cache the latest meter data, various states and measured values."""

    def __init__(self, load: Dict, meter: Dict) -> None:
        Borg.__init__(self, load, meter)
        self.load = load
        self.meter = meter
