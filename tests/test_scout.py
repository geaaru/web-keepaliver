# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import unittest
import asyncio
import threading
import time
from aiohttp import web

from web_keepaliver.http.scout import HttpResource, HttpWebSite, HttpScout


class TestHttpResource(unittest.TestCase):
    def test_http_resource1(self):
        data = {
            'name': "url1-get",
            'url': 'https://www.google.it',
            'method': 'GET',
        }

        obj = HttpResource(data)
        self.assertEqual(obj.name, 'url1-get')
        self.assertEqual(obj.url, 'https://www.google.it')
        self.assertEqual(obj.method, 'GET')
        self.assertEqual(obj.expected_http_code, 200)

    def test_http_resource3(self):

        data = {
            'name': "url2-get",
            'url': 'https://www.google.it',
            'expected_http_code': 200,
            'expected_body_pattern': '.*Google.*',
        }

        obj = HttpResource(data)
        self.assertEqual(obj.name, 'url2-get')
        self.assertEqual(obj.url, 'https://www.google.it')
        self.assertEqual(obj.method, 'GET')
        self.assertEqual(obj.expected_http_code, 200)
        self.assertEqual(obj.expected_body_pattern, '.*Google.*')

    def test_http_resource4(self):
        data = {
            'name': "url2-get",
            'url': 'https://www.google.it',
            'expected_http_code': 404,
            'expected_body_pattern': '.*Google.*',
        }

        obj = HttpResource(data)
        self.assertEqual(obj.name, 'url2-get')
        self.assertEqual(obj.url, 'https://www.google.it')
        self.assertEqual(obj.method, 'GET')
        self.assertEqual(obj.expected_http_code, 404)
        self.assertEqual(obj.expected_body_pattern, '.*Google.*')

    def test_http_resource_error1(self):
        data = {}

        with self.assertRaises(Exception):
            HttpResource(data)

    def test_http_resource_error2(self):
        data = {
            'name': 'url1',
        }

        with self.assertRaises(Exception):
            HttpResource(data)

    def test_http_resource_error3(self):
        data = {
            'url': 'https://mottainaici.github.io/lxd-compose-docs/',
        }

        with self.assertRaises(Exception):
            HttpResource(data)


class TestHttpWebSite(unittest.TestCase):

    def test_http_site_resource1(self):

        data = {
            'name': 'lxd-compose',
            'topic': 'topic1',
            'verify_ssl': False,
            'basic_auth': {
                'user': 'xxx',
                'pass': 'yyy'
            },
            'resources': [
                {
                    'name': "url1-get",
                    'url': 'https://mottainaici.github.io/lxd-compose-docs/',
                    'method': 'GET',
                },
            ]
        }

        obj = HttpWebSite(data)
        self.assertEqual(obj.has_auth, True)
        self.assertEqual(obj.basic_user, 'xxx')
        self.assertEqual(obj.basic_pass, 'yyy')
        self.assertEqual(obj.name, 'lxd-compose')
        self.assertEqual(obj.topic, 'topic1')
        self.assertEqual(obj.verify_ssl, False)
        self.assertEqual(len(obj.resources), 1)

    def test_http_site_resource_error1(self):

        data = {
            'topic': 'topic1',
            'verify_ssl': False,
            'resources': [
                {
                    'name': "url1-get",
                    'url': 'https://mottainaici.github.io/lxd-compose-docs/',
                    'method': 'GET',
                },
            ]
        }

        with self.assertRaises(Exception):
            HttpWebSite(data)

    def test_http_site_resource_error2(self):

        data = {
            'name': 'lxd-compose',
            'topic': 'topic1',
            'verify_ssl': False,
        }

        with self.assertRaises(Exception):
            HttpWebSite(data)


class TestHttpClient(unittest.TestCase):

    @staticmethod
    # noinspection PyUnusedLocal
    async def path_ok(request):
        # pylint: disable=unused-argument
        return web.Response(
            status=200,
            text="All is ok."
        )

    @staticmethod
    # noinspection PyUnusedLocal
    async def path_ko(request):
        # pylint: disable=unused-argument
        return web.Response(
            status=500,
            text="Something goes wrong."
        )

    def _thread_server(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        web.run_app(self.app, port=10000,
                    host="127.0.0.1",
                    reuse_address=True,
                    reuse_port=True,
                    handle_signals=False
                    )

    def setUp(self):
        # Initialize HTTP Server
        self.app = web.Application()
        self.app.router.add_get('/200', self.path_ok)
        self.app.router.add_post('/500', self.path_ko)
        self.app.router.add_get('/500', self.path_ko)
        self.thread = threading.Thread(target=self._thread_server)
        self.thread.daemon = True
        self.thread.start()
        # Wait thread startup
        time.sleep(1)

    @staticmethod
    def get_entity_data():
        return {
            'name': "url1-get",
            'url': 'http://127.0.0.1:10000/',
        }

    @staticmethod
    def get_site_data():
        return HttpWebSite({
            'name': 'site1',
            # Not needed in the test
            'resources': [],
        })

    def _run_request(self, resource, body):
        scout = HttpScout(verify_ssl=False)
        loop = asyncio.new_event_loop()

        try:
            loop.run_until_complete(scout.create_session())
            future = asyncio.ensure_future(
                scout.call_http_resource(resource),
                loop=loop
            )
            loop.run_until_complete(future)
            resp, resp_body = future.result()

            self.assertEqual(resp.status, resource.expected_http_code)
            self.assertEqual(resp_body, body)
        finally:
            loop.run_until_complete(scout.cleanup())

        loop.close()

    def _run_probe(self, resource, result, error_desc):
        scout = HttpScout(verify_ssl=False)
        loop = asyncio.new_event_loop()

        try:
            loop.run_until_complete(scout.create_session())
            future = asyncio.ensure_future(
                scout.probe_resource(self.get_site_data(), resource),
                loop=loop
            )
            loop.run_until_complete(future)
            probe_result = future.result()

            self.assertEqual(probe_result.resource, resource)
            self.assertEqual(probe_result.resp_http_code,
                             resource.expected_http_code)
            self.assertEqual(probe_result.result, result)
            if error_desc is not None:
                self.assertTrue(probe_result.error_desc is not None)
                self.assertTrue(error_desc in probe_result.error_desc)
            else:
                self.assertEqual(probe_result.error_desc, error_desc)

        finally:
            loop.run_until_complete(scout.cleanup())

        loop.close()

    def test_http_client1(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '200')
        data['method'] = 'GET'
        resource = HttpResource(data)
        self._run_request(resource, 'All is ok.')

    def test_http_client2(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '500')
        data['method'] = 'GET'
        data['expected_http_code'] = 500
        resource = HttpResource(data)
        self._run_request(resource, 'Something goes wrong.')

    def test_http_client3(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '500')
        data['method'] = 'POST'
        data['expected_http_code'] = 500
        resource = HttpResource(data)
        self._run_request(resource, 'Something goes wrong.')

    def test_probe_resource1(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '200')
        resource = HttpResource(data)
        self._run_probe(resource, True, None)

    def test_probe_resource2(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '200')
        data['expected_body_pattern'] = '.*All.*'
        resource = HttpResource(data)
        self._run_probe(resource, True, None)

    def test_probe_resource3(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '200')
        data['expected_body_pattern'] = '.*Not match.*'
        resource = HttpResource(data)
        self._run_probe(resource, False,
                        "Response body doesn't match expected pattern")

    def test_probe_resource4(self):
        data = self.get_entity_data()
        data['url'] = "http://127.0.0.1:10001/invalid"
        data['expected_http_code'] = 0
        resource = HttpResource(data)
        self._run_probe(resource, False,
                        "Cannot connect to host 127.0.0.1:10001")

    def test_probe_resource5(self):
        data = self.get_entity_data()
        data['url'] = '%s%s' % (data['url'], '500')
        data['method'] = 'POST'
        data['expected_http_code'] = 500
        resource = HttpResource(data)
        self._run_probe(resource, True, None)


if __name__ == '__main__':
    unittest.main()

# vim: ts=4 sw=4 expandtab
