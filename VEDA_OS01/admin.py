from django.contrib import admin

from VEDA_OS01.models import (
    Course, Video, Encode, URL, Destination, Institution, VedaUpload,
    TranscriptionPreferences
)


class CourseAdmin(admin.ModelAdmin):
    ordering = ['institution']
    list_display = [
        'course_name',
        'course_hold',
        'institution',
        'edx_classid',
        'last_vid_number',
        'previous_statechange'
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
    model = Video
    list_display = [
        'edx_id',
        'client_title',
        'studio_id',
        'video_trans_start',
        'video_trans_status',
        'video_active'
    ]
    list_filter = ['inst_class__institution']
    search_fields = ['edx_id', 'client_title', 'studio_id']


class EncodeAdmin(admin.ModelAdmin):
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
    model = Destination
    list_display = ['destination_name', 'destination_active']


class InstitutionAdmin(admin.ModelAdmin):
    model = Institution
    list_display = ['institution_name', 'institution_code']


class VideoUploadAdmin(admin.ModelAdmin):
    model = VedaUpload
    list_display = [
        'client_information',
        'upload_filename',
        'status_email',
        'file_complete',
        'youtube_id'
    ]


class TranscriptionPreferencesAdmin(admin.ModelAdmin):
    model = TranscriptionPreferences


admin.site.register(Course, CourseAdmin)
admin.site.register(Video, VideoAdmin)
admin.site.register(Encode, EncodeAdmin)
admin.site.register(URL, URLAdmin)
admin.site.register(Destination, DestinationAdmin)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(VedaUpload, VideoUploadAdmin)
admin.site.register(TranscriptionPreferences, TranscriptionPreferencesAdmin)
