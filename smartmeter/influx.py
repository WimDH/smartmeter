from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from typing import Dict, List
from smartmeter.digimeter import convert_timestamp
from time import monotonic
import logging

LOG = logging.getLogger("main")


class DbInflux:
    """
    Connect to Influx and write data.
    TODO: if influxdb is unreachable, cache the result and
          write them to the DB when the connection is back up.
    """

    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        bucket: str,
        verify_ssl: bool = True,
        timeout: int = 30 * 1000,  # milliseconds
        ssl_ca_cert: str = None,
        upload_interval: int = 0,
    ) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.ssl_ca_cert = ssl_ca_cert
        self.start_time = monotonic()
        self.batch = []
        self.upload_interval = upload_interval
        self.last_upload_time: int = 0

    async def write(self, data: Dict) -> None:
        """
        Write a telegram to an influx bucket.
        """
        if (
            monotonic() - self.last_upload_time < self.upload_interval
            or len(self.batch) == 0
        ):
            self.batch.append(self.craft_json(data))
            LOG.debug(
                "Adding datapoints to batch (contains %d datapoints).", len(self.batch)
            )
            return

        LOG.info(
            "Writing %d datapoint(s) to InfluxDB at %s", len(self.batch), self.url
        )
        async with InfluxDBClientAsync(
            url=self.url,
            token=self.token,
            org=self.org,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl,
            ssl_ca_cert=self.ssl_ca_cert,
        ) as db:
            write_api = db.write_api()
            await write_api.write(bucket=self.bucket, record=self.batch, org=self.org)
            self.batch = []
            self.last_upload_time = monotonic()

    def craft_json(self, data: Dict) -> List[Dict]:
        """
        Prepare the data to be written to InfluxDB.
        """
        LOG.debug("Crafting Influx datapoints.")

        # Electricity data.
        e_data = {
            "measurement": "electricity",
            "tags": {},
            "time": convert_timestamp(data.get("timestamp", "")),
            "fields": {
                key: value
                for (key, value) in data.items()
                if ("timestamp" not in key and "gas" not in key)
            },
        }
        LOG.debug("Electricity data point: %s", e_data)

        # Gas data.
        g_data = {
            "measurement": "gas",
            "tags": {},
            "time": convert_timestamp(data.get("gas_timestamp", "")),
            "fields": {
                key: value
                for (key, value) in data.items()
                if ("timestamp" not in key and "gas" in key)
            },
        }
        LOG.debug("Gas data point: %s", g_data)

        # Load data.
        l_data = {
            "measurement": "load",
            "tags": {},
            "time": convert_timestamp(data.get("timestamp", "")),
            "fields": {"load_on": data.get("load_status", 0)},
        }
        LOG.debug("Load data point: %s", l_data)

        return [e_data, g_data, l_data]
