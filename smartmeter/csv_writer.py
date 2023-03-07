import csv
import os
from typing import Optional, Union
from datetime import datetime
from time import monotonic, sleep
from smartmeter.digimeter import FIELDS, convert_timestamp
import logging

LOG = logging.getLogger("main")
FIELDNAMES = ["timestamp", "gas_timestamp"] + [
    f[1] for f in FIELDS if "timestamp" not in f[1]
]
WIP_PREFIX = ".wip__"


class CSVWriter:
    """
    Write the records to CSV files.
    """

    def __init__(
        self,
        prefix: str = "smartmeter",
        path: str = None,
        write_header: bool = True,
        write_every: int = 1,
        max_lines: Optional[int] = 100,
        max_age: Optional[int] = 300,
    ) -> None:
        self.prefix = prefix
        self.path = path
        self.write_header = write_header
        self.write_every: int = write_every
        self.max_lines = max_lines
        self.max_age = max_age
        self.dictwriter = None
        self.filehandler = None
        self.create_time = 0
        self.lines_written = 0
        self.batch = []

    def _generate_filename(self) -> str:
        """
        Generate a unique filename.
        """
        while True:
            filename = os.path.join(
                self.path,
                WIP_PREFIX
                + self.prefix
                + "_"
                + datetime.now().strftime("%Y%m%d%H%M%S")
                + ".csv",
            )
            target_filename = os.path.join(
                self.path, os.path.split(filename)[1][len(WIP_PREFIX):]
            )
            if not os.path.exists(target_filename):
                return filename
            else:
                LOG.warning(
                    "File %s already exists, waiting 1 sec. to generate new name.",
                    filename,
                )
                sleep(1)

    def open(self) -> None:
        """
        Create a DicWriter instance for the file opened, and write the
        CSV header.
        WARNING: If you rotate files within the second, the creation of the
        new file will be postponed with one second.
        """
        if self.filehandler and not self.filehandler.closed:
            return

        LOG.debug("Current CSV file is %s", self.filehandler)
        filename = self._generate_filename()
        LOG.info("Creating CSV file %s", format(filename))
        self.filehandler = open(filename, "w")
        self.dictwriter = csv.DictWriter(
            self.filehandler, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL
        )
        self.dictwriter.writeheader()
        self.lines_written = 0
        self.create_time = monotonic()

    def close(self, flush: bool = False) -> None:
        """
        Close the CSV file.
        """
        if self.filehandler.closed:
            return

        # Write the remainder of the rows.
        if flush is True and len(self.batch) > 0:
            LOG.debug("Writing the remainder of the rows.")
            self.write(flush=True)

        filename = self.filename
        LOG.debug("Closing file {}.".format(self.filename))
        self.filehandler.close()
        self.filehandler = None
        # If no rows have been written to the file, we can remove it.
        if self.lines_written == 0:
            LOG.debug(
                "Removing file {} since no rows were written to it.".format(filename)
            )
            os.unlink(filename)
        else:
            new_filename = os.path.join(
                self.path, os.path.split(filename)[1][len(WIP_PREFIX):]
            )
            LOG.info("Renaming file to {}.".format(new_filename))
            os.rename(filename, new_filename)

    @property
    def filename(self) -> Union[str, None]:
        """
        Returns the filename or None.
        """
        return self.filehandler.name or None

    def write(self, telegram: Optional[dict] = None, flush: bool = False) -> None:
        """
        Write a telegram to the CSV file.
        TODO: Handle disk full/permission denied.
        """
        if telegram:
            # Remove the local timestamp field, as it is not used in the CSV files.
            del telegram["local_timestamp"]
            telegram["timestamp"] = convert_timestamp(
                telegram["timestamp"], format="iso8601"
            )
            telegram["gas_timestamp"] = convert_timestamp(
                telegram["gas_timestamp"], format="iso8601"
            )

            self.batch.append(telegram)

        if len(self.batch) < self.write_every and flush is False:
            return

        self.open()
        while self.batch:
            self.dictwriter.writerow(self.batch.pop())
            self.lines_written += 1

            if (
                self.max_age + self.create_time <= monotonic()
                or self.lines_written == self.max_lines
            ):
                LOG.debug("%s Lines written to CSV file.", self.lines_written)
                self.close()
                break

