import BaseHTTPServer
import SocketServer
import logging
import time
import contextlib
from urlparse import urlparse, parse_qs
import hashlib

import requests
import memcache

TIMEOUT = 24 * 3600
PORT = 8080
HOST = '127.0.0.1'
REQUEST_ADDRESS = "https://vast-eyrie-4711.herokuapp.com/?key="
REQUEST_TIMEOUT = 1
ATTEMPTS_TIMEOUT = 0.1
MEMCAHCE_PORT = 11211


logging.basicConfig(filename="log.txt", level=logging.DEBUG)
logger = logging.getLogger(__name__)

mc = memcache.Client([str(HOST)+":"+str(MEMCAHCE_PORT)])

@contextlib.contextmanager
def cache_lock(key):
    locked_key = 'namelock::%s' % hashlib.md5(key.encode('utf-8')).hexdigest()
    if mc.get(locked_key) is not None:
        logger.debug("Key is locked, waiting")
        while mc.get(locked_key):
            time.sleep(ATTEMPTS_TIMEOUT)
    try:
        logger.debug("Locking key %s", locked_key)
        mc.add(locked_key, True, time=ATTEMPTS_TIMEOUT*10)
        yield
    finally:
        logger.debug("Releasing key %s", locked_key)
        mc.delete(locked_key)

class CacheHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        self.from_cache()

    def from_cache(self):
        params = parse_qs(urlparse(self.path).query)
        value = self.get_key(params["key"][0])
        print ("Returned value from address is %s", value)
        return value

    def get_key(self, key):
        value = mc.get(key)
        if value is None:
            with cache_lock(key) as lock:
                value = mc.get(key)
                if value is None:
                    value = self.calculate_value(key)
        return value

    def calculate_value(self, key):
        start = time.time()
        while (time.time() - start) < REQUEST_TIMEOUT:
            try:
                result = requests.get(REQUEST_ADDRESS + key)
            except requests.RequestException, exception:
                log.info("Exception %s", exception)
            time.sleep(ATTEMPTS_TIMEOUT)
            if result.ok:
                mc.set(key, result.content, time=TIMEOUT)
                logger.debug("New value %s for %s key calculated", result.content, key)
                return result.content
            else:
                logger.error("Exception occured %s", result.status_code)
                return
        logger.error("Request timeout exceeded")


def run(host=HOST, port=PORT):
   logger.info("Starting server on host %s, port %s", HOST, PORT)
   httpd = BaseHTTPServer.HTTPServer((host, port), CacheHandler)
   httpd.serve_forever()

if __name__ == "__main__":
   run()
