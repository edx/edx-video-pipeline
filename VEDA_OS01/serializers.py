#! usr/bin/env python

from rest_framework import serializers

from VEDA_OS01.models import Course, Video, URL, Encode


class CourseSerializer(serializers.ModelSerializer):

    class Meta:
        model = Course
        fields = (
            'id',
            'course_hold',
            'review_proc',
            'yt_proc',
            's3_proc',
            'course_name',
            'institution',
            'edx_classid',
            'semesterid',
            'last_vid_number',
            'previous_statechange',
            'studio_hex',
            'proc_loc',
            'sg_projID',
            'created',
            'modified',
        )

    def create(self, validated_data, partial=True):
        return Course.objects.create(**validated_data)

    def update(self, instance, validated_data, partial=True):
        instance.course_name = validated_data.get(
            'course_name',
            instance.course_name
        )
        instance.course_hold = validated_data.get(
            'course_hold',
            instance.course_hold
        )
        instance.last_vid_number = validated_data.get(
            'last_vid_number',
            instance.last_vid_number
        )
        instance.previous_statechange = validated_data.get(
            'previous_statechange',
            instance.previous_statechange
        )
        instance.save()
        return instance


class VideoSerializer(serializers.ModelSerializer):

    course_ids = serializers.SerializerMethodField(source='get_course_ids', read_only=True)

    class Meta:
        model = Video
        fields = (
            'id',
            'inst_class',
            'edx_id',
            'studio_id',
            'video_active',
            'client_title',
            'video_orig_duration',
            'video_orig_filesize',
            'video_orig_bitrate',
            'video_orig_extension',
            'video_orig_resolution',
            'video_trans_start',
            'video_trans_end',
            'video_trans_status',
            'transcript_status',
            'video_glacierid',
            'course_ids',
            'process_transcription',
            'source_language',
            'provider',
            'three_play_turnaround',
            'cielo24_turnaround',
            'cielo24_fidelity',
            'preferred_languages',
        )

    def get_course_ids(self, video):
        return [course_id.strip() for course_id in video.inst_class.local_storedir.split(',') if course_id]

    def create(self, validated_data):
        return Video.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """Might be able to pare this down"""
        instance.inst_class = validated_data.get(
            'inst_class',
            instance.inst_class
        )
        instance.edx_id = validated_data.get(
            'edx_id',
            instance.edx_id
        )
        instance.studio_id = validated_data.get(
            'studio_id',
            instance.studio_id
        )
        instance.video_active = validated_data.get(
            'video_active',
            instance.video_active
        )
        instance.client_title = validated_data.get(
            'client_title',
            instance.client_title
        )
        instance.video_orig_duration = validated_data.get(
            'video_orig_duration',
            instance.video_orig_duration
        )
        instance.video_orig_extension = validated_data.get(
            'video_orig_extension',
            instance.video_orig_extension
        )
        instance.video_trans_start = validated_data.get(
            'video_trans_start',
            instance.video_trans_start
        )
        instance.video_trans_end = validated_data.get(
            'video_trans_end',
            instance.video_trans_end
        )
        instance.video_trans_status = validated_data.get(
            'video_trans_status',
            instance.video_trans_status
        )
        instance.transcript_status = validated_data.get(
            'transcript_status',
            instance.transcript_status
        )
        instance.video_glacierid = validated_data.get(
            'video_glacierid',
            instance.video_glacierid
        )
        instance.process_transcription = validated_data.get(
            'process_transcription',
            instance.process_transcription
        )
        instance.source_language = validated_data.get(
            'source_language',
            instance.source_language
        )
        instance.provider = validated_data.get(
            'provider',
            instance.provider
        )
        instance.three_play_turnaround = validated_data.get(
            'three_play_turnaround',
            instance.three_play_turnaround
        )
        instance.cielo24_turnaround = validated_data.get(
            'cielo24_turnaround',
            instance.cielo24_turnaround
        )
        instance.cielo24_fidelity = validated_data.get(
            'cielo24_fidelity',
            instance.cielo24_fidelity
        )
        instance.preferred_languages = validated_data.get(
            'preferred_languages',
            instance.preferred_languages
        )
        instance.save()
        return instance


class EncodeSerializer(serializers.ModelSerializer):
    """
    View only Field
    """
    class Meta:
        model = Encode
        fields = (
            'id',
            'profile_active',
            'encode_suffix',
            'encode_filetype',
            'encode_bitdepth',
            'encode_resolution',
            'product_spec',
            'xuetang_proc',
        )


class URLSerializer(serializers.ModelSerializer):

    class Meta:
        model = URL
        fields = (
            'id',
            'encode_profile',
            'videoID',
            'encode_url',
            'url_date',
            'encode_duration',
            'encode_bitdepth',
            'encode_size',
            'val_input',
            'xuetang_input',
            'md5_sum',
        )

    def create(self, validated_data):
        return URL.objects.create(**validated_data)
