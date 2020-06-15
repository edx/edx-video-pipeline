"""views"""


import json
import logging

import requests
import django_filters.rest_framework
from django.db import connection
from django.db.utils import DatabaseError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import renderers, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .api import token_finisher
from VEDA import utils
from VEDA_OS01.enums import TranscriptionProviderErrorType
from VEDA_OS01.models import (URL, Course, Encode, TranscriptCredentials,
                              TranscriptProvider, Video)
from VEDA_OS01.serializers import (CourseSerializer, EncodeSerializer,
                                   URLSerializer, VideoSerializer)
from VEDA_OS01.transcripts import CIELO24_API_VERSION
from VEDA_OS01.utils import PlainTextParser
from control.http_ingest_celeryapp import ingest_video_and_upload_to_hotstore

LOGGER = logging.getLogger(__name__)


auth_dict = utils.get_config()
CIELO24_LOGIN_URL = utils.build_url(
    auth_dict['cielo24_api_base_url'],
    '/account/login'
)


class CourseViewSet(viewsets.ModelViewSet):

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filter_fields = (
        'institution',
        'edx_classid',
        'proc_loc',
        'course_hold',
        'sg_projID'
    )

    @action(detail=True, renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        course = self.get_object()
        return Response(course.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class VideoViewSet(viewsets.ModelViewSet):

    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filter_fields = ('inst_class', 'edx_id')

    @action(detail=True, renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        video = self.get_object()
        return Response(video.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class EncodeViewSet(viewsets.ModelViewSet):

    queryset = Encode.objects.all()
    serializer_class = EncodeSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filter_fields = ('encode_filetype', 'encode_suffix', 'product_spec')

    @action(detail=True, renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        encode = self.get_object()
        return Response(encode.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class URLViewSet(viewsets.ModelViewSet):

    queryset = URL.objects.all()
    serializer_class = URLSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filter_fields = (
        'videoID__edx_id',
        'encode_profile__encode_suffix',
        'encode_profile__encode_filetype'
    )

    @action(detail=True, renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        url = self.get_object()
        return Response(url.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class TranscriptCredentialsView(APIView):
    """
    A Transcript credentials View, used by platform to create/update transcript credentials.
    """

    def get_cielo_token_response(self, username, api_secure_key):
        """
        Returns Cielo24 api token.

        Arguments:
            username(str): Cielo24 username
            api_securekey(str): Cielo24 api key

        Returns:
            Response : Http response object
        """
        return requests.get(CIELO24_LOGIN_URL, params={
            'v': CIELO24_API_VERSION,
            'username': username,
            'securekey': api_secure_key
        })

    def get_api_token(self, username, api_key):
        """
        Returns api token if valid credentials are provided.
        """
        response = self.get_cielo_token_response(username=username, api_secure_key=api_key)
        if not response.ok:
            api_token = None
            LOGGER.warning(
                '[Transcript Credentials] Unable to get api token --  response %s --  status %s.',
                response.text,
                response.status_code,
            )
        else:
            api_token = json.loads(response.content)['ApiToken']

        return api_token

    def validate_missing_attributes(self, provider, attributes, credentials):
        """
        Returns error message if provided attributes are not presents in credentials.
        """
        error_message = None
        missing = [attr for attr in attributes if attr not in credentials]
        if missing:
            error_message = u'{missing} must be specified for {provider}.'.format(
                provider=provider,
                missing=' and '.join(missing)
            )

        return TranscriptionProviderErrorType.MISSING_REQUIRED_ATTRIBUTES, error_message

    def validate_transcript_credentials(self, provider, **credentials):
        """
        Validates transcript credentials.

        Validations:
            Providers must be either 3PlayMedia or Cielo24.
            In case of:
                3PlayMedia - 'api_key' and 'api_secret_key' are required.
                Cielo24 - Valid 'api_key' and 'username' are required.
        """
        error_type, error_message, validated_credentials = None, '', {}
        if provider in [TranscriptProvider.CIELO24, TranscriptProvider.THREE_PLAY]:
            if provider == TranscriptProvider.CIELO24:
                must_have_props = ('org', 'api_key', 'username')
                error_type, error_message = self.validate_missing_attributes(provider, must_have_props, credentials)

                if not error_message:
                    # Get cielo api token and store it in api_key.
                    api_token = self.get_api_token(credentials['username'], credentials['api_key'])
                    if api_token:
                        validated_credentials.update({
                            'org': credentials['org'],
                            'api_key': api_token
                        })
                    else:
                        error_message = u'Invalid credentials supplied.'
                        error_type = TranscriptionProviderErrorType.INVALID_CREDENTIALS
            else:
                must_have_props = ('org', 'api_key', 'api_secret_key')
                error_type, error_message = self.validate_missing_attributes(provider, must_have_props, credentials)
                if not error_message:
                    validated_credentials.update({
                        'org': credentials['org'],
                        'api_key': credentials['api_key'],
                        'api_secret': credentials['api_secret_key']
                    })
        else:
            error_message = u'Invalid provider {provider}.'.format(provider=provider)
            error_type = TranscriptionProviderErrorType.INVALID_PROVIDER

        return error_type, error_message, validated_credentials

    def post(self, request):
        """
        Creates or updates the org-specific transcript credentials with the given information.

        Arguments:
            request: A WSGI request.

        **Example Request**

            POST /api/transcript_credentials {
                "provider": "3PlayMedia",
                "org": "test.x",
                "api_key": "test-api-key",
                "api_secret_key": "test-api-secret-key"
            }

        **POST Parameters**

            A POST request can include the following parameters.

            * provider: A string representation of provider.

            * org: A string representing the organizaton code.

            * api_key: A string representing the provider api key.

            * api_secret_key: (Required for 3Play only). A string representing the api secret key.

            * username: (Required for Cielo only). A string representing the cielo username.

            **Example POST Response**

            In case of success:
                Returns an empty response with 201 status code (HTTP 201 Created).

            In case of error:
                Return response with error message and 400 status code (HTTP 400 Bad Request).
                {
                    "error_type": INVALID_CREDENTIALS
                    "message": "Error message."
                }
        """
        # Validate credentials
        provider = request.data.pop('provider', None)
        error_type, error_message, validated_credentials = self.validate_transcript_credentials(
            provider=provider, **request.data
        )
        if error_message:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=dict(error_type=error_type, message=error_message)
            )

        TranscriptCredentials.objects.update_or_create(
            org=validated_credentials.pop('org'), provider=provider, defaults=validated_credentials
        )

        return Response(status=status.HTTP_201_CREATED)


@permission_classes([AllowAny])
class IngestFromS3View(APIView):
    """
    Endpoint called by Amazon SNS/SQS to ingest video from the s3 bucket.
    """
    parser_classes = (JSONParser, PlainTextParser,)

    def _manage_aws_sns_subscription(self, request_body, subscription_type_url):
        """
        Manage HTTP endpoint subscription to SNS. There are two subscription_type_urls:
            1. subscribeURL
            2. unsubscribeURL
        Upon receiving a request to subscribe or unsunscribe an SNS to an HTTP endpoint,
        the endpoint must visit the URL provided by Amazon to confirm.
        """

        url = request_body.get(subscription_type_url)
        if not url:
            return 400, 'Subscribe/unsubscribe URL not in request body'

        requests.get(url)
        return 200, ''

    def _ingest_from_s3_bucket(self, request_body):
        """
        Handle ingest from s3 bucket.
        """
        status = 400
        reason = ''
        request_message = request_body.get('Message')
        try:
            message_json = json.loads(request_message)
            s3_object = message_json.get('Records')[0].get('s3')
            video_s3_key = s3_object.get('object').get('key')
        except TypeError:
            reason = 'Request message body does not contain expected output'
            LOGGER.error('[HTTP INGEST] {reason}'.format(reason=reason))
            return status, reason

        if not video_s3_key:
            reason = 'Video does not contain s3 key'
            LOGGER.error('[HTTP INGEST] {reason}'.format(reason=reason))
            return status, reason
        ingest_video_and_upload_to_hotstore.apply_async(args=[video_s3_key],
                                                        queue=auth_dict['celery_http_ingest_queue'])
        status = 200
        return status, reason

    @csrf_exempt
    def post(self, request):
        """
        Endpoint to handle requests from SNS.
        Three types of messages can be sent:
            1. A SubscriptionConfirmation - a subscription from SNS to this endpoint
            2. A UnsubscribeConfirmation - unsubscribing SNS from this endpoint
            3. A Notification - a request to ingest a video
        """
        amazon_message_type = request.META.get('HTTP_X_AMZ_SNS_MESSAGE_TYPE')

        if not amazon_message_type:
            return JsonResponse(
                {'Reason': 'Malformed header'},
                status=400
            )

        if not request.data:
            return JsonResponse(
                {'Reason': 'Empty request body'},
                status=400
            )

        json_data = json.loads(request.data)

        if amazon_message_type == 'SubscriptionConfirmation':
            status, reason = self._manage_aws_sns_subscription(json_data, 'SubscribeURL')
            if status == 200:
                LOGGER.info('[HTTP INGEST] SNS subscribed to HTTP endpoint')
        elif amazon_message_type == 'UnsubscribeConfirmation':
            status, reason = self._manage_aws_sns_subscription(json_data, 'UnsubscribeURL')
            if status == 200:
                LOGGER.info('[HTTP INGEST] SNS unsubscribed to HTTP endpoint')
        elif amazon_message_type == 'Notification':
            status, reason = self._ingest_from_s3_bucket(json_data)
            if status == 200:
                LOGGER.info('[HTTP INGEST] Video ingested through HTTP endpoint. Request body = {body}'.format(
                    body=request.data
                ))
            else:
                LOGGER.error('[HTTP INGEST] Video failed ingest through HTTP endpoint. Request body = {body}'.format(
                    body=request.data
                ))
        else:
            status = 400
            reason = 'Unsupported or invalid amazon message type'

        return JsonResponse(
            {'Reason': reason},
            status=status
        )


@csrf_exempt
def token_auth(request):
    """

    This is a hack to override the "Authorize" step in token generation

    """
    if request.method == 'POST':
        complete = token_finisher(request.POST['data'])
        return HttpResponse(complete)
    else:
        return HttpResponse(status=404)


def user_login(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(request.path)
    else:
        return HttpResponseRedirect('../admin')  # settings.LOGIN_REDIRECT_URL)


@api_view(['GET'])
@permission_classes([AllowAny])
def heartbeat(request):  # pylint: disable=unused-argument
    """
    View to check if database is reachable and ready to handle requests.
    """
    try:
        db_status()
    except DatabaseError:
        return JsonResponse(
            {'OK': False},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return JsonResponse(
        {'OK': True},
        status=status.HTTP_200_OK
    )


def db_status():
    """
    Return database status.
    """
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
