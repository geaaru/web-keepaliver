# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import unittest

from web_keepaliver.common import AppSeed


class AppDummy(AppSeed):

    def __init__(self):
        AppSeed.__init__(
            self,
            config_default_file="../etc/keepaliver-producer.yaml"
        )

        self.configuration = {
            'probe_interval_sec': 10,
            'kafka': {
                'bootstrap_servers': [
                    "kafka1.mottainai.local:9092"
                ],
                "enable_idempotence": True,
            },
            "limit_sim_conn": 3,
            "websites": [
                {
                    "name": "google.it",
                    "topic": "web-keepaliver",
                    "verify_ssl": True,
                    "request_timeout_sec": 120,
                    "resources": [
                        {
                            "name": "google-homepage",
                            "url": "https://www.google.it",
                            "method": "GET",
                            "expected_http_code": 200
                        }
                    ]
                }
            ]

        }

    def signal_handler(self, signame):
        pass

    def main(self, parse_cmdline_opts=True):
        pass


class TestAppSeed(unittest.TestCase):

    def test_get_param(self):
        dummy_app = AppDummy()
        self.assertEqual(
            dummy_app.get_config_param(None, "probe_interval_sec", 5),
            10
        )
        self.assertEqual(
            dummy_app.get_config_param("kafka", "bootstrap_servers", []),
            ["kafka1.mottainai.local:9092"],
        )
        self.assertEqual(
            dummy_app.get_config_param("kafka", "enable_idempotence", False),
            True,
        )
        self.assertEqual(
            dummy_app.get_config_category('kafka'),
            {
                'bootstrap_servers': [
                    "kafka1.mottainai.local:9092"
                ],
                "enable_idempotence": True,
            },
        )
        self.assertEqual(
            dummy_app.get_config_category("wrong", default=True),
            True
        )
        self.assertEqual(
            dummy_app.get_config_param("wrong", "field", default=True),
            True
        )


if __name__ == '__main__':
    unittest.main()
