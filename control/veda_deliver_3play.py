"""
3PlayMedia Transcription Client
"""
from __future__ import absolute_import
import json
import logging
import requests
import urllib3

from requests.packages.urllib3.exceptions import InsecurePlatformWarning
from VEDA_OS01.models import TranscriptProcessMetadata, TranscriptProvider, TranscriptStatus
from VEDA.utils import build_url, scrub_query_params

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)


class ThreePlayMediaError(Exception):
    """
    An error that occurs during 3PlayMedia actions.
    """
    pass


class ThreePlayMediaLanguageNotFoundError(ThreePlayMediaError):
    """
    An error when language is not found in available 3playMedia languages.
    """
    pass


class ThreePlayMediaPerformTranscriptionError(ThreePlayMediaError):
    """
    An error occurred while adding media for transcription.
    """
    pass


class ThreePlayMediaUrlError(ThreePlayMediaError):
    """
    Occurs when the media url is either inaccessible or of invalid content type.
    """
    pass


class ThreePlayMediaLanguagesRetrievalError(ThreePlayMediaError):
    """
    An error Occurred while retrieving available 3PlayMedia languages.
    """
    pass


class ThreePlayMediaClient(object):

    def __init__(
            self,
            org,
            video,
            media_url,
            api_key,
            api_secret,
            callback_url,
            turnaround_level,
            three_play_api_base_url
    ):
        """
        Initialize 3play media client
        """
        self.org = org
        self.video = video
        self.media_url = media_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        self.turnaround_level = turnaround_level
        # default attributes
        self.base_url = three_play_api_base_url
        self.upload_media_file_url = u'files/'
        self.available_languages_url = u'caption_imports/available_languages/'
        self.allowed_content_type = u'video/mp4'
        self.default_dir = 'Default'

    def validate_media_url(self):
        """
        Validates the media URL

        Raises:
            3PlayMediaUrlError: on invalid media url or content type
        """
        if not self.media_url:
            raise ThreePlayMediaUrlError('Invalid media URL "{media_url}".'.format(media_url=self.media_url))

        response = requests.head(url=self.media_url)
        if not response.ok:
            raise ThreePlayMediaUrlError('The URL "{media_url}" is not Accessible.'.format(media_url=self.media_url))
        elif response.headers['Content-Type'] != self.allowed_content_type:
            raise ThreePlayMediaUrlError(
                'Media content-type should be "{allowed_type}". URL was "{media_url}", content-type was "{type}"'.format(  # pylint: disable=line-too-long
                    allowed_type=self.allowed_content_type,
                    media_url=self.media_url,
                    type=response.headers['Content-Type'],
                )
            )

    def get_available_languages(self):
        """
        Gets all the 3Play Media supported languages
        """
        available_languages_url = build_url(self.base_url, self.available_languages_url, apikey=self.api_key)
        response = requests.get(
            url=available_languages_url
        )
        if not response.ok:
            raise ThreePlayMediaLanguagesRetrievalError(
                'Error while retrieving available languages: url={url} -- {response} -- {status}'.format(
                    url=scrub_query_params(available_languages_url, ['apikey']),
                    response=response.text,
                    status=response.status_code
                )
            )

        # A normal response should be a list containing 3Play Media supported languages and if we're getting a dict,
        # there must be an error: https://support.3playmedia.com/hc/en-us/articles/227729968-Captions-Imports-API
        available_languages = json.loads(response.text)
        if isinstance(available_languages, dict):
            raise ThreePlayMediaLanguagesRetrievalError(
                'Expected 3Play Media Supported languages but got: {response}'.format(response=response.text)
            )

        return available_languages

    def get_source_language_id(self, languages, source_language_code):
        """
        Extracts language id for a language that matches `source_language_code`
        from the given 3Play Media languages.

        Arguments:
            languages(list): 3PlayMedia supported languages.
            source_language_code(unicode): A video source language code whose 3Play language id is required.
        """
        for language in languages:
            if language['iso_639_1_code'] == source_language_code:
                return language['language_id']

    def submit_media(self):
        """
        Submits the media to perform transcription.

        Raises:
            ThreePlayMediaPerformTranscriptionError: error while transcription process
        """
        self.validate_media_url()
        # Prepare requests payload
        payload = dict(
            # Mandatory attributes required for transcription
            link=self.media_url,
            apikey=self.api_key,
            api_secret_key=self.api_secret,
            turnaround_level=self.turnaround_level,
            callback_url=self.callback_url,
            batch_name=self.default_dir,
        )

        available_languages = self.get_available_languages()
        source_language_id = self.get_source_language_id(available_languages, self.video.source_language)
        if source_language_id:
            payload['language_id'] = source_language_id

        upload_url = build_url(self.base_url, self.upload_media_file_url)
        response = requests.post(url=upload_url, json=payload)

        if not response.ok:
            raise ThreePlayMediaPerformTranscriptionError(
                'Upload file request failed with: {response} -- {status}'.format(
                    response=response.text, status=response.status_code
                )
            )

        # A normal response should be a text containing file id and if we're getting a deserializable dict, there
        # must be an error: http://support.3playmedia.com/hc/en-us/articles/227729828-Files-API-Methods
        if isinstance(json.loads(response.text), dict):
            raise ThreePlayMediaPerformTranscriptionError(
                'Expected file id but got: {response}'.format(response=response.text)
            )

        return response.text

    def generate_transcripts(self):
        """
        Kicks off transcription process for default language.
        """
        try:
            file_id = self.submit_media()
            # Track progress of transcription process
            TranscriptProcessMetadata.objects.create(
                video=self.video,
                process_id=file_id,
                lang_code=self.video.source_language,
                provider=TranscriptProvider.THREE_PLAY,
                status=TranscriptStatus.IN_PROGRESS,
            )
            # Successfully kicked off transcription process for a video with the given language.
            LOGGER.info(
                '[3PlayMedia] Transcription process has been started for video=%s, source_language=%s.',
                self.video.studio_id,
                self.video.source_language,
            )
        except ThreePlayMediaError:
            LOGGER.exception(
                '[3PlayMedia] Could not process transcripts for video=%s source_language=%s.',
                self.video.studio_id,
                self.video.source_language,
            )
        except Exception:
            LOGGER.exception(
                '[3PlayMedia] Unexpected error while transcription for video=%s source_language=%s.',
                self.video.studio_id,
                self.video.source_language,
            )
            raise
