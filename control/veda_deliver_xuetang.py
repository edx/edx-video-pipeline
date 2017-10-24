
import os
import hashlib
import hmac
import base64
import datetime
import requests
import json
import time
from time import strftime
from VEDA.utils import get_config

"""
Authored by Ed Zarecor / edx DevOps

included by request

Some adaptations for VEDA:
    -auth yaml

   **VEDA Note: since this isn't a real CDN, and represents the
    'least effort' response to getting video into china,
    we shan't monitor for success**


"""
auth_dict = get_config()

API_SHARED_SECRET = auth_dict['xuetang_api_shared_secret']
API_ENDPOINT = auth_dict['xuetang_api_url']


# Currently the API support no query arguments so this component of the signature
# will always be an empty string.
API_QUERY_STRING = ""
SEPERATOR = '*' * 10

"""
This script provides a functions for accessing the Xuetang CDN API

It expects that an environment variable name XUETANG_SHARED_SECRET is
available and refers to a valid secret provided by the Xuetang CDN team.

Running this script will cause a video hosted in cloudfront to be
uploaded to the CDN via the API.

The status of the video will be monitored in a loop, exiting when
the terminal status, available, has been reached.

Finally, the video will be deleted from the cache exercising the
delete functionality.
"""


def _pretty_print_request(req):
    """
    Convenience function for pretty printing requests for debugging API
    issues.
    """
    print('\n'.join(
        [SEPERATOR + ' start-request ' + SEPERATOR,
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
         SEPERATOR + ' end-request ' + SEPERATOR]))

def build_message(verb, uri, query_string, date, payload_hash):
    """
    Builds a message conforming to the Xuetang format for mutual authentication.  The
    format is defined in their CDN API specification document.
    """
    return os.linesep.join([verb, uri, query_string, date, payload_hash])

def sign_message(message, secret):
    """
    Returns a hexdigest of HMAC generated using sha256.  The value is included in
    the HTTP headers and used for mutual authentication via a shared secret.
    """
    return hmac.new(bytes(secret), bytes(message), digestmod=hashlib.sha256).hexdigest()

def hex_digest(payload):
    """
    returns the sha256 hexdigest of the request payload, typically JSON.
    """
    return hashlib.sha256(bytes(payload)).hexdigest()

def get_api_date():
    """
    Returns an "RFC8601" date as specified in the Xuetang API specification
    """
    return strftime("%Y-%m-%dT%H:%M:%S") + "-{0:04d}".format((time.timezone / 3600) * 100)

def prepare_create_or_update_video(edx_url, download_urls, md5sum):
    """
    Returns a prepared HTTP request for initially seeding or updating an edX video
    in the Xuetang CDN.
    """
    api_target = "/edxvideo"
    payload = {'edx_url':edx_url, 'download_url': download_urls, 'md5sum':md5sum}
    return _prepare_api_request("POST", api_target, payload)

def prepare_delete_video(edx_url):
    """
    Returns a prepared HTTP request for deleting an edX video in the Xuetang CDN.
    """
    api_target = "/edxvideo"
    payload = {'edx_url':edx_url}
    return _prepare_api_request("DELETE", api_target, payload)

def prepare_check_task_status(edx_url):
    """
    Returns a prepared HTTP request for checking the status of an edX video
    in the Xuetang CDN.
    """
    api_target = "/edxtask"
    payload = {'edx_url':edx_url}
    return _prepare_api_request("POST", api_target, payload)

def _prepare_api_request(http_verb, api_target, payload):
    """
    General convenience function for creating prepared HTTP requests that conform the
    Xuetang API specificiation.
    """
    payload_json = json.dumps(payload)
    payload_sha256_hexdigest = hex_digest(payload_json)

    date = get_api_date()

    message = bytes(build_message(http_verb, api_target, API_QUERY_STRING, date, payload_sha256_hexdigest))
    secret = bytes(API_SHARED_SECRET)
    signature  = sign_message(message, secret)

    headers = {"Authentication": "edx {0}".format(signature), "Content-Type": "application/json", "Date": date}
    req = requests.Request(http_verb, API_ENDPOINT + api_target, headers=headers, data=payload_json)
    return req.prepare()

def _submit_prepared_request(prepared):
    """
    General function for submitting prepared HTTP requests.
    """
    # Suppress InsecurePlatform warning
    requests.packages.urllib3.disable_warnings()
    s = requests.Session()
    # TODO: enable certificate verification after working through
    # certificate issues with Xuetang
    return s.send(prepared, timeout=20, verify=False)


if __name__ == '__main__':

    # Download URL from the LMS
    edx_url = "xxx"
    # edx_url = "http://s3.amazonaws.com/edx-course-videos/ut-takemeds/UTXUT401T313-V000300_DTH.mp4"
    # A list containing the same URL
    download_urls = ["xxx"]
    # The md5sum of the video from the s3 ETAG value
    md5sum =  "xxx"

    #
    # The code below is a simple test harness for the Xuetang API that
    #
    # - pushes a new video to the CDN
    # - checks the status of the video in a loop until it is available
    # - issues a delete request to remove the video from the CDN
    #

    # upload or update
    # prepared = prepare_create_or_update_video(edx_url, download_urls, md5sum)
    # _pretty_print_request(prepared)
    # print os.linesep
    # res = _submit_prepared_request(prepared)
    # print res.text
    # print os.linesep

    # # check status
    # while True:
    #     prepared = prepare_check_task_status(edx_url)
    #     _pretty_print_request(prepared)
    #     res = _submit_prepared_request(prepared)
    #     print res.text

    #     if res.json()['status'] == 'available':
    #         break

    #     time.sleep(5)

    # delete file
    prepared = prepare_delete_video(edx_url)
    _pretty_print_request(prepared)
    res = _submit_prepared_request(prepared)
    print res.text

    # check status
    prepared = prepare_check_task_status(edx_url)
    _pretty_print_request(prepared)
    res = _submit_prepared_request(prepared)
    print res.text
