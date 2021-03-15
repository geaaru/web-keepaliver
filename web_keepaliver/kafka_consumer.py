# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncio
import os
import traceback2
import uuid
import json
import datetime
import pytz

from sys import exit as start_shuttle
from concurrent.futures import CancelledError

from web_keepaliver.common import AppSeed, KafkaClientConfigurator
from web_keepaliver.db.postgres import PostgresConnector, PostgresDatabase

KEEPALIVER_KAFKA_CONSUMER_CONFIG = '/etc/web-keepaliver/kafka-consumer.yaml'
KEEPALIVER_KAFKA_CONSUMER_DEF_NAME = 'web-keepaliver-kafka-consumer'
KEEPALIVER_KAFKA_CONSUMER_DESC = """
Copyright (c) 2021 Daniele Rondina

Web Keepaliver Kafka Consumer.
"""


class KeepaliverKafkaConsumer(AppSeed,
                              KafkaClientConfigurator,
                              PostgresConnector):

    def __init__(self):
        self.kafka_brokers = []
        self.kafka_consumer = None
        self.msgs_counter = 0
        self.in_shutdown = False

        config_def_file = os.getenv(
            'KEEPALIVER_KAFKA_CONSUMER_CONFIG',
            KEEPALIVER_KAFKA_CONSUMER_CONFIG,
        )

        AppSeed.__init__(self, logger_name='kafka-consumer',
                         config_default_file=config_def_file,
                         app_description=KEEPALIVER_KAFKA_CONSUMER_DESC)
        KafkaClientConfigurator.__init__(self)
        PostgresConnector.__init__(self)

        # Avoid cancel tasks when kafka consumer is running.
        self._cancel_tasks = False

        self.get_parser().add_argument(
            '--broker',
            action='store',
            default=[],
            nargs='*',
            type=str,
            dest='kafka_brokers',
            help='Override kafka brokers defined in the configuration file.'
        )

    def get_postgres_conn_options(self):
        return self.get_config_category('postgres', {})

    def get_kafka_configuration(self, producer=True, admin=False):
        opts = self.get_config_category('kafka', {})

        if len(self.kafka_brokers) > 0:
            opts['bootstrap_servers'] = self.kafka_brokers

        opts['client_id'] = self.name
        return opts

    async def _init_consumer(self):
        self.kafka_consumer = self.create_kafka_consumer()

        brokers = 'localhost:9092'
        if len(self.kafka_brokers) > 0:
            brokers = self.kafka_brokers
        else:
            brokers = self.get_config_param(
                'kafka', 'bootstrap_servers', brokers
            )

        self.logger.info(
            'Starting instance %s with kafka brokers %s.',
            self.name, brokers,
        )

        await self.kafka_consumer.start()

        # Subscripte topics
        self.kafka_consumer.subscribe(pattern=self.get_config_param(
            None, 'subscription_regex', "web-keepaliver"
        ))

    async def _initialize(self):
        self.name = self.get_config_param(
            None, 'name', KEEPALIVER_KAFKA_CONSUMER_DEF_NAME
        )

        # New aiokafka package has deprecated loop argument.
        # It's needed to ensure the is used the right loop object.
        asyncio.set_event_loop(loop=self.loop)

        await self._init_consumer()
        await self.create_pool()

    def signal_handler(self, signame):
        self.in_shutdown = True

    async def _process_site_events(self, site, topic, messages):
        last_event = messages[len(messages)-1]
        site_probes = []
        status = {}

        self.logger.info(
            "[%s] Processing %d events from topic %s.", site,
            len(messages), topic,
        )

        try:
            for event in messages:
                if 'probes' not in event:
                    self.logger.warning(
                        "[%s] Received invalid event without probes from "
                        "topic %s", site, topic,
                    )
                    continue

                probes = event['probes']

                all_events_ok = True
                for p in probes:
                    if 'resp_ts' in p:
                        ts = datetime.datetime.fromtimestamp(
                            int(p['resp_ts'])/1000.0,
                        )
                    else:
                        # If resp_ts is not present then
                        # we use the kafka message timestamp.
                        ts = datetime.datetime.fromtimestamp(
                            p.timestamp/1000.0,
                        )

                    ts = datetime.datetime(ts.year, ts.month, ts.day,
                                           hour=ts.hour,
                                           minute=ts.minute,
                                           second=ts.second,
                                           tzinfo=pytz.utc)

                    site_probes.append((
                        ts, site,
                        p['resource'],
                        p['method'],
                        p['url'],
                        p['resp_http_code'],
                        p['resp_time_ms'],
                        p['expected_http_code'],
                        p['result'],
                        p['error_desc'] if 'error_desc' in p else None,
                    ))

                    if not p['result']:
                        all_events_ok = False

                if event == last_event:
                    last_update = datetime.datetime.utcnow()
                    # Prepare status entry
                    status = {
                        'site': site,
                        'last_update': last_update,
                        'status': all_events_ok,
                        'n_resources': len(event['probes']),
                        'err_counter': 0 if all_events_ok else False,
                    }
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                'Unexpected error or prepare records on db: %s\n%s', exc,
                '\n'.join(traceback2.format_exc().splitlines())
                if self.debug
                else ''
            )

        con = await self.acquire()
        try:
            # Register probes
            await PostgresDatabase.register_probes(con, site_probes)

            # Update site status
            await PostgresDatabase.register_site_status(con, status)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                'Unexpected error or register records on db: %s\n%s', exc,
                '\n'.join(traceback2.format_exc().splitlines())
                if self.debug
                else ''
            )
        finally:
            await self.release(con)

    async def _parse_topic_messages(self, tp, messages):

        try:
            site_events_map = {}
            for message in messages:

                jmsg = json.loads(str(message.value.decode('ascii')))

                self.msgs_counter += 1
                self.logger.info(
                    "[%s/%d/%d] [%s] Received message %s",
                    tp.topic, tp.partition,
                    message.offset,
                    str(uuid.UUID(bytes=message.key)),
                    str(message.value.decode('ascii')) if self.debug
                    else 'with %d events' % len(jmsg['probes'])
                )

                # Organize messages for site
                if jmsg['site'] not in site_events_map:
                    site_events_map[jmsg['site']] = [jmsg]
                else:
                    site_events_map[jmsg['site']].append(jmsg)

            futures = []
            for site in site_events_map:
                events = site_events_map[site]
                futures.append(asyncio.ensure_future(
                    self._process_site_events(site, tp.topic, events)
                ))

            await asyncio.gather(
                *futures,
                return_exceptions=True
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                'Unexpected error or parse topic messages: %s\n%s', exc,
                '\n'.join(traceback2.format_exc().splitlines())
                if self.debug
                else ''
            )

    async def _async_main(self):
        await self._initialize()

        self.logger.info(
            "Instance %s started.", self.name
        )

        try:
            while True and not self.in_shutdown:
                self.logger.debug("Waiting for messages...")

                data = await self.kafka_consumer.getmany(
                    timeout_ms=self.get_config_param(
                        None, 'timeout_waiting_data',
                        10000,
                    )
                )
                futures = []
                for tp, messages in data.items():
                    future = asyncio.ensure_future(
                        self._parse_topic_messages(
                            tp, messages,
                        )
                    )
                    futures.append(future)

                await asyncio.ensure_future(
                    asyncio.gather(
                        *futures,
                        return_exceptions=True,
                        loop=self.loop,
                    )
                )

        except CancelledError:
            pass

        await self.kafka_consumer.commit()

        # TODO: Verify why with the unsubscribe i receive error on stop
        #  consumer.
        # Error: Commit offset before unsubscribe to avoid
        # UnknownMemberIdError
        # self.kafka_consumer.unsubscribe()

    async def _cleanup(self):
        if self.kafka_consumer:
            await self.kafka_consumer.stop()
        await self.postgres_cleanup()

    def main(self, parse_cmdline_opts=True):
        ans = 0
        if parse_cmdline_opts:
            self.parse_cmd_line()

        try:
            self.init_thread_pool(size=self.get_config_param(
                'general', 'thread_pool_size', 20,
            ))
            self.add_signal_handler()
            self.loop.run_until_complete(
                asyncio.ensure_future(self._async_main())
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
        self.loop.run_until_complete(self._cleanup())

        self.logger.info(
            "Instance %s stopped.", self.name
        )
        self.loop.close()

        return ans


def main():
    in_space = KeepaliverKafkaConsumer()
    start_shuttle(in_space.main())


if __name__ == '__main__':
    main()


# vim: ts=4 sw=4 expandtab
