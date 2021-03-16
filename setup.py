#!/usr/bin/env python
# Author: Daniele Rondina, geaaru@sabayonlinux.org

from setuptools import setup, find_packages
from web_keepaliver import __version__

setup(
        name='web_keepaliver',
        version=__version__,
        description='Web Monitoring System to Kafka',
        author='Daniele Rondina',
        author_email='%s' % (
            'geaaru@sabayonlinux.org',
        ),
        packages=find_packages(exclude=[
            'etc', 'systemd',
            'dbrm', 'grafana',
            'ci', 'tests'
        ]),
        install_requires=[
            'PyYAML',
            'kafka-python',
            'aiokafka',
            'traceback2',
            'aiohttp',
            'asyncpg',
        ],
        entry_points={
            'console_scripts': [
                'web-keepaliver-producer=web_keepaliver.kafka_producer:main',
                'web-keepaliver-consumer=web_keepaliver.kafka_consumer:main',
            ]
        }
)
