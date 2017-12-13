"""
Models for Video Pipeline
"""
import json
import uuid
from django.db import models
from fernet_fields import EncryptedTextField
from model_utils.models import TimeStampedModel

from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey


def _createHex():
    return uuid.uuid1().hex


class TranscriptProvider(object):
    """
    3rd party transcript providers.
    """

    THREE_PLAY = '3PlayMedia'
    CIELO24 = 'Cielo24'
    CHOICES = (
        (THREE_PLAY, THREE_PLAY),
        (CIELO24, CIELO24),
    )


class TranscriptStatus(object):
    """
    Transcript statuses.

    Note:
        If this status is 'PENDING' for:
            1. Video, then transcription is applicable to a video but its not started yet.
            2. TranscriptProcessMetadata, then transcript/translation process is created but its not actually
            sent for processing to the 3rd Party Transcription Services.
    """
    NOT_APPLICABLE = 'N/A'
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN PROGRESS'
    FAILED = 'FAILED'
    READY = 'READY'
    CHOICES = (
        (NOT_APPLICABLE, NOT_APPLICABLE),
        (PENDING, PENDING),
        (IN_PROGRESS, IN_PROGRESS),
        (FAILED, FAILED),
        (READY, READY)
    )


class Cielo24Turnaround(object):
    """
    Turnaround Enumeration.
    Its the time taken by Cielo24 transcription process.
    """
    STANDARD = 'STANDARD'
    PRIORITY = 'PRIORITY'
    CHOICES = (
        (STANDARD, 'Standard, 48h'),
        (PRIORITY, 'Priority, 24h'),
    )


class Cielo24Fidelity(object):
    """
    Fidelity Enumeration.
    This decides transcript's accuracy and supported languages.
    """
    MECHANICAL = 'MECHANICAL'
    PREMIUM = 'PREMIUM'
    PROFESSIONAL = 'PROFESSIONAL'
    CHOICES = (
        (MECHANICAL, 'Mechanical, 75% Accuracy'),
        (PREMIUM, 'Premium, 95% Accuracy'),
        (PROFESSIONAL, 'Professional, 99% Accuracy'),
    )


class ThreePlayTurnaround(object):
    """
    Turnaround Enumeration.
    Its the time taken by 3PlayMedia transcription process.
    """
    EXTENDED = 'extended'
    STANDARD = 'standard'
    EXPEDITED = 'expedited'
    RUSH = 'rush'
    SAME_DAY = 'same_day'
    TWO_HOUR = 'two_hour'

    CHOICES = (
        (EXTENDED, '10-Day/Extended'),
        (STANDARD, '4-Day/Standard'),
        (EXPEDITED, '2-Day/Expedited'),
        (RUSH, '24 hour/Rush'),
        (SAME_DAY, 'Same Day'),
        (TWO_HOUR, '2 Hour'),
    )


class VideoStatus(object):
    """
    Video Status Enumeration

    TODO: STATUS REMODEL:
    Change to
    'Ingest',
    'Queued',
    'In Progress',
    'Corrupt',
    'Complete',
    'Error',
    'Duplicate',
    'Review',
    'Reject'

    Possibles:
        'Invalid' (for ingest detected)
        'Retry'
        'Delivery' (for celery states?)
    """
    SI = 'Ingest'
    TQ = 'Transcode Queue'
    AT = 'Active Transcode'
    TR = 'Transcode Retry'
    TC = 'Transcode Complete'
    DU = 'Deliverable Upload'
    FC = 'File Complete'
    TE = 'Transcode Error'
    CF = 'Corrupt File'
    RH = 'Review Hold'
    RR = 'Review Reject'
    RP = 'Final Publish'
    YD = 'Youtube Duplicate'
    QUEUE = 'Queue'
    PROGRESS = 'Progress'
    COMPLETE = 'Complete'

    CHOICES = (
        (SI, 'System Ingest'),
        (TQ, 'Transcode Queue'),
        (AT, 'Active Transcode'),
        (TR, 'Transcode Retry'),
        (TC, 'Transcode Complete'),
        (DU, 'Deliverable Upload'),
        (FC, 'File Complete'),
        (TE, 'Transcode Error'),
        (CF, 'Corrupt File on Ingest'),
        (RH, 'Review Hold'),
        (RR, 'Review Rejected'),
        (RP, 'Review to Final Publish'),
        (YD, 'Youtube Duplicate'),
        (QUEUE, 'In Encode Queue'),
        (PROGRESS, 'In Progress'),
        (COMPLETE, 'Complete'),
    )


class ListField(models.TextField):
    """
    A List Field which can be used to store and retrieve pythonic list of strings.
    """
    def get_prep_value(self, value):
        """
        Converts a list to its json representation to store in database as text.
        """
        if value and not isinstance(value, list):
            raise ValueError(u'The given value {} is not a list.'.format(value))

        return json.dumps(self.validate_list(value) or [])

    def from_db_value(self, value, expression, connection, context):
        """
        Converts a json list representation in a database to a python object.
        """
        return self.to_python(value)

    def to_python(self, value):
        """
        Converts the value into a list.
        """
        if not value:
            value = []

        # If a list is set then validated its items
        if isinstance(value, list):
            py_list = self.validate_list(value)
        else:  # try to de-serialize value and expect list and then validate
            try:
                py_list = json.loads(value)
                if not isinstance(py_list, list):
                    raise TypeError

                self.validate_list(py_list)
            except (ValueError, TypeError):
                raise ValueError(u'Must be a valid list of strings.')

        return py_list

    def validate_list(self, value):
        """
        Validate the data before saving into the database.

        Arguments:
            value(list): list to be validated

        Returns:
            A list if validation is successful

        Raises:
            ValidationError
        """
        if all(isinstance(item, basestring) for item in value) is False:
            raise ValueError(u'list must only contain strings.')

        return value


class Institution(models.Model):
    institution_code = models.CharField(max_length=4)
    institution_name = models.CharField(max_length=50)

    def __unicode__(self):
        return u'{institution_name} {institution_code}'.format(
            institution_name=self.institution_name,
            institution_code=self.institution_code,
        )


class Course(TimeStampedModel):
    """
    Model to contain Studio course runs. Ideally, there should be one entry
    in this Model for all the course runs in Studio.
    """
    course_name = models.CharField('Course Name', help_text='Name of this course', max_length=255)

    # TODO: Change Name (this is reversed)
    course_hold = models.BooleanField(
        'Course Active',
        help_text='Tells whether this course is active.',
        default=True
    )
    institution = models.CharField(
        'Inst. Code',
        help_text='Organization of the course.',
        max_length=50
    )
    edx_classid = models.CharField(
        'Class ID',
        help_text='Course number to identify the course.',
        max_length=255
    )

    # TODO deprecate semesterid.
    semesterid = models.CharField('Semester', max_length=4)
    previous_statechange = models.DateTimeField(
        'Previous Data Statechange',
        null=True, blank=True
    )
    proc_loc = models.BooleanField('Mediateam Export', default=False)
    review_proc = models.BooleanField('Producer Review', default=False)
    last_vid_number = models.IntegerField('Last Video ID', default=0)

    # Youtube
    yt_proc = models.BooleanField('Process for Youtube', default=True)
    yt_logon = models.CharField(
        'Youtube SFTP U/N',
        max_length=50,
        null=True, blank=True
    )
    yt_channel = models.CharField(
        'Youtube Channel ID',
        max_length=150,
        null=True, blank=True
    )

    # 3Play Media (Transcription)
    tp_proc = models.BooleanField('Process for 3Play', default=False)
    tp_username = models.CharField(
        '3Play Username',
        max_length=50,
        null=True, blank=True
    )
    tp_password = models.CharField(
        '3Play Password',
        max_length=50,
        null=True, blank=True
    )
    EX = 'extended_service'
    DF = 'default'
    ES = 'expedited_service'
    RS = 'rush_service'
    SD = 'same_day_service'
    TP_SPEED_CHOICES = (
        (EX, '10-Day/Extended'),
        (DF, '4-Day/Default'),
        (ES, '2-Day/Expedited'),
        (RS, '24 hour/Rush'),
        (SD, 'Same Day'),
    )
    tp_speed = models.CharField(
        '3Play Turnaround',
        max_length=20,
        choices=TP_SPEED_CHOICES,
        default=DF
    )
    tp_apikey = models.CharField(
        '3Play API Key',
        max_length=100,
        null=True, blank=True
    )

    # Cielo24
    c24_proc = models.BooleanField('Process for Cielo24', default=False)
    c24_username = models.CharField(
        'Cielo24 Username',
        max_length=50,
        null=True, blank=True
    )
    c24_password = models.CharField(
        'Cielo24Password',
        max_length=50,
        null=True, blank=True
    )
    STD = 'STANDARD'
    PRT = 'PRIORITY'
    C24_SPEED_CHOICES = (
        (STD, 'Standard, 48h'),
        (PRT, 'Priority, 24h'),
    )
    c24_speed = models.CharField(
        'Cielo24 Turnaround',
        max_length=20,
        choices=C24_SPEED_CHOICES,
        default=STD
    )
    MCH = 'MECHANICAL'
    PRM = 'PREMIUM'
    PRO = 'PROFESSIONAL'
    C24_FIDELITY_CHOICES = (
        (MCH, 'Mechanical, 75%'),
        (PRM, 'Premium, 95%'),
        (PRO, 'Professional, 99%'),
    )

    c24_fidelity = models.CharField(
        'Cielo24 Fidelity',
        max_length=20,
        choices=C24_FIDELITY_CHOICES,
        default=PRO
    )

    c24_hours = models.IntegerField(
        'C24 Turnaround Override',
        null=True, blank=True
    )
    c24_apikey = models.CharField(
        'Cielo24 API Key',
        max_length=100,
        null=True, blank=True
    )

    # TODO: Change field name
    s3_proc = models.BooleanField('Process for AWS S3/Mobile?', default=True)

    # TODO: Change field name
    local_storedir = models.CharField(
        'edX Studio URL (VAL)',
        max_length=5000,
        null=True, blank=True
    )
    sg_projID = models.IntegerField('Shotgun Project ID', default=0)
    studio_hex = models.CharField(
        'Studio Hex ID',
        max_length=50,
        default=_createHex,
        unique=True
    )

    @property
    def org(self):
        """
        Get course organization.
        """
        org = None
        course_runs = self.local_storedir
        if course_runs:
            course_id = course_runs.split(',')[0]
            # Extract course organization.
            try:
                org = CourseKey.from_string(course_id).org
            except InvalidKeyError:
                pass

        return org

    @property
    def course_runs(self):
        """
        Returns the studio course runs associated with this course. Ideally, there should be one entry
        in this Model for all the course runs in Studio.
        """
        course_runs = []
        if self.local_storedir:
            course_runs = [
                course_id.strip()
                for course_id in self.local_storedir.split(',')
                if course_id
            ]

        return course_runs

    def __unicode__(self):
        return u'{institution} {edx_class_id} {course_name}'.format(
            institution=self.institution,
            edx_class_id=self.edx_classid,
            course_name=self.course_name,
        )


class Video(models.Model):
    """
    Model for Video.
    """
    # TODO: Change field name
    inst_class = models.ForeignKey(Course)
    video_active = models.BooleanField('Video Active?', default=True)
    client_title = models.CharField(
        'Video (Client) Title',
        max_length=180,
        null=True, blank=True
    )
    edx_id = models.CharField('VEDA Video ID', max_length=20)
    studio_id = models.CharField(
        'Studio Upload ID',
        max_length=100,
        null=True, blank=True
    )
    # Master File Properties
    video_orig_filesize = models.BigIntegerField(
        'Master Filesize',
        null=True, blank=True
    )
    video_orig_duration = models.CharField(
        'Duration (Original)',
        max_length=50,
        null=True, blank=True
    )
    video_orig_bitrate = models.CharField(
        'Orig. Bitrate',
        max_length=15,
        null=True, blank=True
    )
    video_orig_extension = models.CharField(
        'Orig. File Extension',
        max_length=5,
        null=True, blank=True
    )
    video_orig_resolution = models.CharField(
        'Orig. Resolution',
        max_length=50,
        null=True, blank=True
    )
    # Status
    video_trans_start = models.DateTimeField('Process Start', null=True, blank=True)
    video_trans_end = models.DateTimeField('Process Complete', null=True, blank=True)

    video_trans_status = models.CharField(
        'Transcode Status',
        max_length=100,
        choices=VideoStatus.CHOICES,
        default=VideoStatus.SI
    )
    transcript_status = models.CharField(
        'Transcription Status',
        max_length=100,
        choices=TranscriptStatus.CHOICES,
        default=TranscriptStatus.NOT_APPLICABLE
    )

    video_glacierid = models.CharField('Glacier Archive ID String', max_length=200, null=True, blank=True)
    abvid_serial = models.CharField('VEDA Upload Process Serial', max_length=20, null=True, blank=True)
    stat_queuetime = models.FloatField('Video Avg. Queuetime (sec)', default=0)

    # 3rd Party Transcription
    process_transcription = models.BooleanField('Process transcripts from Cielo24/3PlayMedia', default=False)
    provider = models.CharField(
        'Transcription provider',
        max_length=20,
        choices=TranscriptProvider.CHOICES,
        null=True,
        blank=True,
    )
    three_play_turnaround = models.CharField(
        '3PlayMedia Turnaround',
        max_length=20,
        choices=ThreePlayTurnaround.CHOICES,
        null=True,
        blank=True,
    )
    cielo24_turnaround = models.CharField(
        'Cielo24 Turnaround', max_length=20,
        choices=Cielo24Turnaround.CHOICES,
        null=True,
        blank=True,
    )
    cielo24_fidelity = models.CharField(
        'Cielo24 Fidelity',
        max_length=20,
        choices=Cielo24Fidelity.CHOICES,
        null=True,
        blank=True,
    )
    source_language = models.CharField(
        'video source language',
        help_text="This is video speech language.",
        max_length=50,
        null=True,
        blank=True,
    )
    preferred_languages = ListField(blank=True, default=[])

    class Meta:
        get_latest_by = 'video_trans_start'

    def __unicode__(self):
        return u'{edx_id}'.format(edx_id=self.edx_id)


class Destination(models.Model):
    """
    Model for Destination.
    """
    destination_name = models.CharField('Destination', max_length=200, null=True, blank=True)
    destination_active = models.BooleanField('Destination Active', default=False)
    destination_nick = models.CharField('Nickname (3 Char.)', max_length=3, null=True, blank=True)

    def __unicode__(self):
        return u'%s'.format(self.destination_name) or u''


class Encode(models.Model):
    """
    Model for Encode.
    """
    encode_destination = models.ForeignKey(Destination)
    encode_name = models.CharField('Encode Name', max_length=100, null=True, blank=True)
    profile_active = models.BooleanField('Encode Profile Active', default=False)
    encode_suffix = models.CharField(
        'Encode Suffix (No underscore)',
        max_length=10,
        null=True, blank=True
    )
    MP4 = 'mp4'
    SRT = 'srt'
    WEBM = 'webm'
    MP3 = 'mp3'
    HLS = 'HLS'
    ProductFiletype = (
        (MP4, "mpeg-4"),
        (SRT, "srt file"),
        (WEBM, "webm"),
        (MP3, "mp3"),
        (HLS, "HLS"),
    )
    encode_filetype = models.CharField(
        'Encode Filetype',
        max_length=50,
        choices=ProductFiletype,
        default=MP4
    )
    encode_bitdepth = models.CharField(
        'Target Bit Depth / Rate Factor',
        max_length=50,
        null=True, blank=True
    )
    encode_resolution = models.CharField(
        'Target Resolution (Vert)',
        max_length=50,
        null=True, blank=True
    )
    # TODO: Change field name
    product_spec = models.CharField(
        'VAL Profile Name',
        max_length=300,
        null=True, blank=True)

    def __unicode__(self):
        return u'{encode_profile}'.format(encode_profile=self.encode_name)


class URL(models.Model):
    """
    Model for URL.
    """
    encode_profile = models.ForeignKey(Encode)
    videoID = models.ForeignKey(Video)
    encode_url = models.CharField('Destination URL', max_length=500, null=True, blank=True)
    url_date = models.DateTimeField('URL Updated', null=True, blank=True)
    encode_duration = models.CharField('Duration (sec)', max_length=50, null=True, blank=True)
    encode_bitdepth = models.CharField(
        'Encoded Avg. Bitdepth',
        max_length=50,
        null=True, blank=True
    )
    encode_size = models.IntegerField('File Size (bytes)', default="0", null=True, blank=True)
    val_input = models.BooleanField('Inputted to EDX-VAL?', default=False)

    class Meta:
        get_latest_by = 'url_date'

    def __unicode__(self):
        return u'{video_id} : {encode_profile} : {date}'.format(
            video_id=self.videoID.edx_id,
            encode_profile=self.encode_profile.encode_name,
            date=self.url_date,
        )


class VedaUpload(models.Model):
    """
    Internal Upload Tool
    """
    video_serial = models.CharField('Upload Process Serial', max_length=20)
    edx_studio_url = models.CharField(
        'edX Studio URL (VAL)',
        max_length=500,
        null=True, blank=True
    )
    client_information = models.CharField(
        'Client Information Field',
        max_length=500,
        null=True, blank=True
    )
    status_email = models.CharField(
        'Status Target Email',
        max_length=100,
        null=True, blank=True
    )
    upload_filename = models.CharField(
        'Video (Client) Title',
        max_length=180,
        null=True, blank=True
    )
    upload_date = models.DateTimeField(
        'Upload Datetime',
        null=True, blank=True
    )

    edx_id = models.CharField('VEDA Video ID', max_length=20)
    file_valid = models.BooleanField('Valid', default=False)
    final_report = models.BooleanField('Reported', default=False)
    file_complete = models.BooleanField('Complete', default=False)
    youtube_id = models.CharField(
        'Youtube ID',
        max_length=100,
        null=True, blank=True
    )
    comment = models.CharField(
        'Comment/Info',
        max_length=500,
        null=True, blank=True
    )

    class Meta:
        get_latest_by = 'upload_date'

    def __unicode__(self):
        return u'{client_information} {upload_filename} {status_email} {file_complete}'.format(
            client_information=self.client_information,
            upload_filename=self.upload_filename,
            status_email=self.status_email,
            file_complete=self.file_complete
        )


class TranscriptCredentials(TimeStampedModel):
    """
    Model to contain third party transcription service provider preferences.
    """
    org = models.CharField(
        'Organization',
        max_length=50,
        help_text='This value must match the value of organization in studio/edx-platform.'
    )
    provider = models.CharField('Transcript provider', max_length=50, choices=TranscriptProvider.CHOICES)
    api_key = EncryptedTextField('API key', max_length=255)
    api_secret = EncryptedTextField('API secret', max_length=255)

    class Meta:
        unique_together = ('org', 'provider')
        verbose_name_plural = 'Transcript Credentials'

    def __unicode__(self):
        return u'{org} - {provider}'.format(org=self.org, provider=self.provider)


class TranscriptProcessMetadata(TimeStampedModel):
    """
    Model to contain third party transcript process metadata.
    """
    video = models.ForeignKey(Video, related_name='transcript_processes')
    provider = models.CharField('Transcript provider', max_length=50, choices=TranscriptProvider.CHOICES)
    process_id = models.CharField('Process id', max_length=255)
    translation_id = models.CharField(
        'Translation id', help_text='Keeps track of 3Play Translations', max_length=255, null=True, blank=True
    )
    lang_code = models.CharField('Language code', max_length=50)
    status = models.CharField(
        'Transcript status',
        max_length=50,
        choices=TranscriptStatus.CHOICES,
        default=TranscriptStatus.PENDING
    )

    class Meta:
        verbose_name_plural = 'Transcript process metadata'
        get_latest_by = 'modified'

    def update(self, **fields):
        """
        Updates a process.

        Keyword Arguments:
            fields(dict): dict containing all the fields to be updated.
        """
        for attr, value in fields.iteritems():
            setattr(self, attr, value)
        self.save()

    def __unicode__(self):
        return u'{video} - {provider} - {lang}'.format(
            video=self.video.edx_id,
            provider=self.provider,
            lang=self.lang_code
        )
