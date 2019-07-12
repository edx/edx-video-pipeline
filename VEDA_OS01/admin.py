"""
Veda Admin.
"""
from __future__ import absolute_import
from django.contrib import admin
from config_models.admin import ConfigurationModelAdmin

from VEDA_OS01.models import (
    Course, Video, Encode, URL, Destination, Institution, VedaUpload,
    TranscriptCredentials, TranscriptProcessMetadata, EncodeVideosForHlsConfiguration
)


class CourseAdmin(admin.ModelAdmin):
    """
    Course Admin.
    """
    ordering = ['institution']
    list_display = [
        'course_name',
        'course_hold',
        'institution',
        'edx_classid',
        'last_vid_number',
        'previous_statechange',
        'created',
        'modified',
    ]
    list_filter = ['institution']
    search_fields = [
        'course_name',
        'edx_classid',
        'institution',
        'studio_hex'
    ]
    save_as = True


class VideoAdmin(admin.ModelAdmin):
    """
    Admin for Video model.
    """
    model = Video
    list_display = [
        'edx_id',
        'client_title',
        'studio_id',
        'video_trans_start',
        'video_trans_status',
        'transcript_status',
        'video_active',
        'process_transcription',
        'source_language',
        'provider',
        'three_play_turnaround',
        'cielo24_turnaround',
        'cielo24_fidelity',
        'preferred_languages',
    ]
    list_filter = ['inst_class__institution']
    search_fields = ['edx_id', 'client_title', 'studio_id']


class EncodeAdmin(admin.ModelAdmin):
    """
    Admin for Encode model.
    """
    model = Encode
    ordering = ['encode_name']
    list_display = [
        'encode_name',
        'profile_active',
        'encode_filetype',
        'get_destination',
        'encode_suffix',
        'encode_bitdepth',
        'product_spec'
    ]

    def get_destination(self, obj):
        return obj.encode_destination.destination_name

    get_destination.short_description = 'Destination'
    save_as = True


class URLAdmin(admin.ModelAdmin):
    """
    Admin for URL model.
    """
    model = URL
    list_display = [
        'video_id_get',
        'url_date',
        'encode_url',
        'encode_get',
        'val_input'
    ]
    list_filter = ['videoID__inst_class__institution']

    def encode_get(self, obj):
        return obj.encode_profile.encode_name

    def video_id_get(self, obj):
        return obj.videoID.edx_id

    search_fields = [
        'videoID__edx_id',
        'videoID__client_title',
        'encode_url'
    ]


class DestinationAdmin(admin.ModelAdmin):
    """
    Admin for Destination model.
    """
    model = Destination
    list_display = ['destination_name', 'destination_active']


class InstitutionAdmin(admin.ModelAdmin):
    """
    Admin for Institution model.
    """
    model = Institution
    list_display = ['institution_name', 'institution_code']


class VideoUploadAdmin(admin.ModelAdmin):
    """
    Admin for VedaUpload model.
    """
    model = VedaUpload
    list_display = [
        'client_information',
        'upload_filename',
        'status_email',
        'file_complete',
        'youtube_id'
    ]


class TranscriptCredentialsAdmin(admin.ModelAdmin):
    """
    Admin for TranscriptCredentials model.
    """
    model = TranscriptCredentials
    exclude = ('api_key', 'api_secret')


class TranscriptProcessMetadataAdmin(admin.ModelAdmin):
    """
    Admin for TranscriptProcessMetadata model.
    """
    raw_id_fields = ('video', )
    list_display = ('get_video', 'provider', 'process_id', 'translation_id', 'lang_code', 'status')

    def get_video(self, obj):
        return u'"{studio_id}" - "{edx_id}"'.format(
            studio_id=obj.video.studio_id,
            edx_id=obj.video.edx_id
        )

    get_video.admin_order_field = 'video'
    get_video.short_description = 'Transcript Video'

    search_fields = ['video__edx_id', 'video__studio_id', 'process_id', 'translation_id']

    model = TranscriptProcessMetadata


admin.site.register(Course, CourseAdmin)
admin.site.register(Video, VideoAdmin)
admin.site.register(Encode, EncodeAdmin)
admin.site.register(URL, URLAdmin)
admin.site.register(Destination, DestinationAdmin)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(VedaUpload, VideoUploadAdmin)
admin.site.register(TranscriptCredentials, TranscriptCredentialsAdmin)
admin.site.register(TranscriptProcessMetadata, TranscriptProcessMetadataAdmin)
admin.site.register(EncodeVideosForHlsConfiguration, ConfigurationModelAdmin)
