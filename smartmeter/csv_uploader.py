from typing import List
import argparse
import sys
import glob
import os
import logging
from coloredlogs import ColoredFormatter
import minio

LOG = logging.getLogger()


def parse_cli(cli_args: List) -> argparse.Namespace:
    """Process the CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Read and process data from the digital enery meter."
    )
    parser.add_argument(
        "-d",
        "--directory",
        dest="source_dir",
        help="The directory where we look for files.",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        dest="file_pattern",
        help="The file pattern for filtering files.",
    )
    parser.add_argument(
        "-b",
        "--bucket",
        dest="bucket",
        help="Name of the S3 bucket where to upload the files.",
    )
    parser.add_argument("-H", "--hostname", dest="hostname", help="Bucket endpoint.")
    parser.add_argument(
        "-v", dest="verbosity_level", action="count", default=0, help="Verbosity level."
    )

    return parser.parse_args(cli_args)


def init_logging(verbosity_level: int) -> None:
    """Setup the logging to stdout."""
    if verbosity_level > 4:
        verbosity_level = 4
    elif verbosity_level == 0:
        verbosity_level = 1

    level = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]

    logger = logging.getLogger()
    logger.setLevel(level[verbosity_level] - 1)
    console_handler = logging.StreamHandler()
    log_fmt = "%(asctime)s %(levelname)s- %(message)s"

    # If we're in an interactive terminal or not.
    if os.isatty(sys.stdout.fileno()):
        console_handler.setFormatter(ColoredFormatter(log_fmt))
    else:
        console_handler.setFormatter(logging.Formatter(log_fmt))

    logger.addHandler(console_handler)


def copy_file_to_bucket(file: str, endpoint: str, access_key: str, secret_key: str, bucket_name: str) -> None:
    """Copy the file to the bucket."""
    LOG.debug("Copy file %s", file)

    _, filename = os.path.split(file)
    mc = minio.Minio(endpoint, access_key, secret_key, secure=True)

    try:
        mc.fput_object(bucket_name, filename, file)
        LOG.debug("Copy done.")
        os.unlink(file)
        LOG.debug("Deleted local file.")

    except minio.S3Error as err:
        LOG.error("Could not copy %s: %s", filename, err)


def main() -> None:
    """Entrypoint"""
    args = parse_cli(sys.argv[1:])
    init_logging(args.verbosity_level)
    access_key = os.environ.get("SMARTMETER_ACCESS_KEY")
    secret_key = os.environ.get("SMARTMETER_SECRET_KEY")

    if not access_key or not secret_key:
        LOG.error(
            "Set the environment variables SMARTMETER_ACCESS_KEY and SMARTMETER_SECRET_KEY!"
        )
        sys.exit(1)

    LOG.info("-- Start --")

    files = glob.glob(os.path.join(args.source_dir, args.file_pattern))

    for file in files:
        LOG.debug("Copying file %s", file)
        copy_file_to_bucket(file, args.hostname, access_key, secret_key, args.bucket)

    LOG.info("-- Done copying %s file(s) --", len(files))
    print("blah")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
