# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncio
import os
import traceback2
import uuid

from sys import exit as start_shuttle
from concurrent.futures import CancelledError

from web_keepaliver.common import AppSeed, KafkaClientConfigurator

KEEPALIVER_KAFKA_CONSUMER_CONFIG = '/etc/web-keepaliver/kafka-consumer.yaml'
KEEPALIVER_KAFKA_CONSUMER_DEF_NAME = 'web-keepaliver-kafka-consumer'
KEEPALIVER_KAFKA_CONSUMER_DESC = """
Copyright (c) 2021 Daniele Rondina

Web Keepaliver Kafka Consumer.
"""


class KeepaliverKafkaConsumer(AppSeed, KafkaClientConfigurator):

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

    def signal_handler(self, signame):
        self.in_shutdown = True

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
                for tp, messages in data.items():
                    for message in messages:
                        self.msgs_counter += 1
                        self.logger.info(
                            "[%s/%d/%d] [%s] Received message '%s'",
                            tp.topic, tp.partition,
                            message.offset,
                            str(uuid.UUID(bytes=message.key)),
                            str(message.value.decode('ascii')),
                        )

        except CancelledError:
            pass

        await self.kafka_consumer.commit()

        # TODO: Verify why with the unsubscribe i receive error on stop
        #  consumer.
        # Error: Commit offset before unsubscribe to avoid
        # UnknownMemberIdError
        # self.kafka_consumer.unsubscribe()

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
        self.loop.run_until_complete(self.kafka_consumer.stop())

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
