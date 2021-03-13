# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import aiohttp
import logging
import re
from datetime import datetime

from web_keepaliver import LOGGER_NAME


class HttpResource:
    """
        Http Resource to test.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, data):
        if not isinstance(data, dict):
            raise Exception('Invalid data')

        if 'name' not in data:
            raise Exception('Http resource without name')
        if 'url' not in data:
            raise Exception('Http resource without url')

        self.url = data['url']
        self.name = data['name']
        self.method = data['method'] if 'method' in data else 'GET'
        self.headers = data['headers'] if 'headers' in data else []
        if 'expected_http_code' in data:
            self.expected_http_code = data['expected_http_code']
        else:
            self.expected_http_code = 200
        self.expected_body_pattern = None
        if 'expected_body_pattern' in data:
            self.expected_body_pattern = data['expected_body_pattern']

    def get_name(self):
        return self.name

    def get_method(self):
        return self.method


class HttpProbeResult:

    def __init__(self, resource: HttpResource,
                 resp_http_code: int,
                 result: bool,
                 error_desc: str = None,
                 resp_time_ms: int = -1):
        self.resource = resource
        self.resp_http_code = resp_http_code
        self.result = result
        self.error_desc = error_desc
        self.resp_time_ms = resp_time_ms

    def get_resp_http_code(self):
        return self.resp_http_code

    def pack(self):
        ans = {
            'name': self.resource.get_name(),
            'url': self.resource.url,
            'method': self.resource.get_method(),
            'resp_http_code': self.resp_http_code,
            'resp_time_ms': self.resp_time_ms,
            'expected_http_code': self.resource.expected_http_code,
            'result': self.result,

        }

        if self.error_desc is not None and len(self.error_desc) > 0:
            ans['error_desc'] = self.error_desc

        return ans


class HttpWebSite:
    """
        Http web site to check.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, data):
        if not isinstance(data, dict):
            raise Exception('Invalid data')
        if 'name' not in data:
            raise Exception('Http website without name')
        if 'resources' not in data:
            raise Exception('Http website without resources')
        if not isinstance(data['resources'], list):
            raise Exception(
                'Http website %s with invalid resources' % data['name']
            )
        self.has_auth = False
        self.basic_user = None
        self.basic_pass = None
        if 'basic_auth' in data:
            if 'user' in data['basic_auth'] and 'pass' in data['basic_auth']:
                self.has_auth = True
                self.basic_user = data['basic_auth']['user']
                self.basic_pass = data['basic_auth']['pass']
        if 'request_timeout_sec' in data:
            self.request_timeout = data['request_timeout_sec']
        else:
            self.request_timeout = 20
        self.name = data['name']
        self.topic = data['topic'] if 'topic' in data else None
        self.verify_ssl = data['verify_ssl'] if 'verify_ssl' in data else True
        self.resources = []

        for resource in data['resources']:
            self.resources.append(HttpResource(resource))

    def get_name(self):
        return self.name

    def get_resources(self):
        return self.resources

    def get_topic(self):
        return self.topic

    def has_basic_auth(self):
        return self.has_auth


class HttpScout:
    """
        HTTP Scout for generate HTTP requests.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self,
                 request_timeout=120,
                 limit_sim_conn=50,
                 verify_ssl=True,
                 basic_usr=None,
                 basic_pwd=None,
                 logger_name=None):
        if not logger_name:
            logger_name = LOGGER_NAME
        self.logger = logging.getLogger(logger_name)

        self.request_timeout = request_timeout
        self.limit_sim_conn = limit_sim_conn

        self.has_auth = False
        if basic_usr is not None and basic_pwd is not None:
            self.has_auth = True
        self.verify_ssl = verify_ssl
        self.basic_usr = basic_usr
        self.basic_pwd = basic_pwd
        self.session = None

    async def create_session(self):

        if self.has_auth:
            basic_auth = aiohttp.BasicAuth(self.basic_usr, self.basic_pwd)
        else:
            basic_auth = None

        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.verify_ssl,
                                           limit=self.limit_sim_conn),
            auth=basic_auth,
        )

    def get_session(self):
        return self.session

    async def call_http_resource(self,
                                 resource: HttpResource) -> (
            aiohttp.ClientResponse, str
    ):
        """
            Low level function that execute the HTTP request defined
            on input entity.

        :param resource: HttpResource
        :return: return tuple with aiohttp.ClientResponse and the
                 Response body.
        """
        resp_body = None

        self.logger.debug(
            '[%s] Calling URL %s - %s',
            resource.name, resource.url, resource.method,
        )

        resp = await self.get_session().request(
            resource.method, resource.url,
            timeout=self.request_timeout,
        )

        if str(resp.status).startswith('2') \
                or str(resp.status).startswith('5'):
            await resp.read()
            resp_body = await resp.text()

        return resp, resp_body

    async def probe_resource(self, resource: HttpResource) -> HttpProbeResult:
        """
        Proble HTTP request and validate response respect the expected values.

        :param resource: HttpResource to check.
        :return: the result of the probe as HttpProbeResult
        """
        result = False
        resp_http_code = 0
        ms = -1
        error_desc = None
        try:
            start_time = datetime.utcnow()
            resp, resp_body = await self.call_http_resource(resource)
            end_time = datetime.utcnow()
            ms = int((end_time - start_time).seconds * 1000) + round(
                (end_time - start_time).microseconds / 1000,
                2
            )
            # NOTE: ms isn't accurate because depends on the number
            #       of concurrency tasks.

            resp_http_code = resp.status

            if resp.status == resource.expected_http_code:

                if resource.expected_body_pattern:
                    if re.search(resource.expected_body_pattern,
                                 resp_body) is not None:
                        result = True
                    else:
                        self.logger.debug(
                            "[%s] body = \n%s\n", resource.get_name(),
                            resp_body,
                        )
                        error_desc = "Response body doesn't match "\
                                     "expected pattern"

                else:
                    # POST: it's needed check the HTTP response code
                    result = True
            else:
                error_desc = "Response HTTP code doesn't match expected value."
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                '[%s] Error on probe %s (%s): %s.',
                resource.name, resource.url, resource.get_method(), exc,
            )
            error_desc = '%s' % exc

        ans = HttpProbeResult(resource, resp_http_code, result,
                              error_desc=error_desc,
                              resp_time_ms=ms)

        return ans

    async def cleanup(self):
        if self.session:
            await self.session.close()
            self.session = None

# vim: ts=4 sw=4 expandtab
