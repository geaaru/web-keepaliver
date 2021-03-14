# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncio
import os
import json
import traceback2
import uuid
from kafka.errors import KafkaError

from sys import exit as start_shuttle
from concurrent.futures import CancelledError

from web_keepaliver.common import AppSeed, KafkaClientConfigurator
from web_keepaliver.http.scout import HttpWebSite, HttpScout
from web_keepaliver import LOGGER_NAME

KEEPALIVER_KAFKA_PRODUCER_CONFIG = '/etc/web-keepaliver/kafka-producer.yml'
KEEPALIVER_KAFKA_PRODUCER_DEF_NAME = 'web-keepaliver-kafka-producer'
KEEPALIVER_KAFKA_PRODUCER_DESC = """
Copyright (c) 2021 Daniele Rondina

Web Keepaliver Kafka Producer.
"""


class KeepaliverKafkaProducer(AppSeed, KafkaClientConfigurator):

    def __init__(self):
        self.kafka_brokers = []
        self.kafka_producer = None
        self.msgs_counter = 0

        config_def_file = os.getenv(
            'KEEPALIVER_KAFKA_PRODUCER_CONFIG',
            KEEPALIVER_KAFKA_PRODUCER_CONFIG,
        )

        AppSeed.__init__(self, logger_name=LOGGER_NAME,
                         config_default_file=config_def_file,
                         app_description=KEEPALIVER_KAFKA_PRODUCER_DESC)
        KafkaClientConfigurator.__init__(self)

        self.get_parser().add_argument(
            '--broker',
            action='store',
            default=[],
            nargs='*',
            type=str,
            dest='kafka_brokers',
            help='Override kafka brokers defined in the configuration file.'
        )

    def signal_handler(self, signame):
        pass

    def get_kafka_configuration(self, producer=True, admin=False):
        opts = self.get_config_category('kafka', {})

        if len(self.kafka_brokers) > 0:
            opts['bootstrap_servers'] = self.kafka_brokers

        opts['client_id'] = self.name
        # We sent message in JSON format
        opts['value_serializer'] = lambda x: json.dumps(x).encode('ascii')
        return opts

    async def _init_producer(self):
        self.kafka_producer = self.create_kafka_producer()

        brokers = 'localhost:9092'
        if len(self.kafka_brokers) > 0:
            brokers = self.kafka_brokers
        else:
            brokers = self.get_config_param(
                'kafka', 'bootstrap_servers', brokers
            )

        self.logger.info(
            'Starting instance %s with kafka brokers %s.',
            self.name, brokers
        )

        await self.kafka_producer.start()

    async def _initialize(self):
        self.name = self.get_config_param(
            None, 'name', KEEPALIVER_KAFKA_PRODUCER_DEF_NAME
        )

        # New aiokafka package has deprecated loop argument.
        # It's needed to ensure the is used the right loop object.
        asyncio.set_event_loop(loop=self.loop)

        await self._init_producer()

    async def _send2topic(self, msg, topic='web-keepaliver'):
        key = uuid.uuid4()

        self.logger.info(
            "[%s] Sending message to topic %s: %s",
            key, topic, msg,
        )

        try:
            res = await self.kafka_producer.send_and_wait(
                topic, msg, key.bytes,
            )

            self.logger.info(
                "[%s] Message sent: %s", key, res,
            )

            self.msgs_counter += 1
        except KafkaError as exc:
            self.logger.error(
                "[%s] error on send to topic %s: %s",
                key, topic, exc,
            )

    async def _probe_site(self, site: HttpWebSite):

        self.logger.debug(
            "[%s] Running site probes...", site.name
        )

        scout = HttpScout(
            verify_ssl=site.verify_ssl,
            request_timeout=site.request_timeout,
            limit_sim_conn=self.get_config_param(
                None, 'limit_sim_conn', 5
            ),
            basic_usr=site.basic_user,
            basic_pwd=site.basic_pass
        )

        try:

            self.logger.debug(
                "[%s] Creating session...", site.name
            )
            await scout.create_session()
            futures = []

            # Create the list of future for every resource
            for resource in site.get_resources():
                future = asyncio.ensure_future(
                    scout.probe_resource(site, resource)
                )
                futures.append(future)

            await asyncio.ensure_future(
                asyncio.gather(
                    *futures,
                    return_exceptions=True
                )
            )

            # Create futures of the probe results and send
            # messages to kafka brokers.
            probes = []
            for future in futures:
                probe_result = future.result()
                probes.append(probe_result.pack())

            msg = {
                'site': site.get_name(),
                'probes': probes,
            }

            await self._send2topic(msg, site.topic)

        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                '[%s] Unexpected error: %s\n%s', site.name, exc,
                '\n'.join(traceback2.format_exc().splitlines()) if self.debug
                else ''
            )
        finally:
            await scout.cleanup()

    async def _run_probes(self):

        self.logger.debug(
            "Running sites probes..."
        )
        sites = self.get_config_category('websites')
        futures = []
        for site in sites:
            website = HttpWebSite(site)
            futures.append(
                asyncio.ensure_future(
                    self._probe_site(website),
                    loop=self.loop
                )
            )

        await asyncio.ensure_future(
            asyncio.gather(
                *futures, return_exceptions=True,
                loop=self.loop,
            )
        )

    async def _main(self):
        await self._initialize()

        self.logger.info(
            "Instance %s started.", self.name
        )

        try:
            while True:
                self.logger.debug("Probing services...")

                await asyncio.sleep(self.get_config_param(
                    None, 'probe_interval_sec', 10,
                ))

                asyncio.ensure_future(self._run_probes())

        except CancelledError:
            pass

    def _validate_sites(self):
        sites = self.get_config_category('websites')
        for site in sites:
            _ = HttpWebSite(site)

    def main(self, parse_cmdline_opts=True):
        ans = 0
        if parse_cmdline_opts:
            self.parse_cmd_line()

        try:
            self.init_thread_pool(size=self.get_config_param(
                'general', 'thread_pool_size', 20,
            ))
            self.add_signal_handler()

            # Validate sites
            self._validate_sites()

            self.loop.run_until_complete(
                asyncio.ensure_future(self._main())
            )
        except KeyboardInterrupt:
            pass
        except CancelledError:
            pass
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                'Unexpected error: %s\n%s', exc,
                '\n'.join(traceback2.format_exc().splitlines()) if self.debug
                else ''
            )
            ans = 1

        # Running closing operation of the producer
        self.loop.run_until_complete(self.kafka_producer.stop())

        self.logger.info(
            "Instance %s stopped.", self.name
        )
        self.loop.close()

        return ans


def main():
    in_space = KeepaliverKafkaProducer()
    start_shuttle(in_space.main())


if __name__ == '__main__':
    main()


# vim: ts=4 sw=4 expandtab
