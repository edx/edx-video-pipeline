
from django.test import TestCase

from VEDA_OS01.models import Course, Destination, Encode, URL, Video
from VEDA_OS01.serializers import CourseSerializer, EncodeSerializer, URLSerializer, VideoSerializer
import six


class TestCourseSerializer(TestCase):
    """
    Tests for `CourseSerializer`.
    """
    def setUp(self):
        self.course_props = dict(
            course_name=u'Intro to VEDA',
            institution=u'MAx',
            edx_classid=u'123',
            semesterid=u'2017',
        )

    def test_create_course(self):
        """
        Tests that `CourseSerializer.create` works as expected.
        """
        course_serializer = CourseSerializer(data=self.course_props)
        course_serializer.is_valid(raise_exception=True)
        course_serializer.save()
        # Now, get the created course record.
        serialized_course = CourseSerializer(
            instance=Course.objects.get(**self.course_props)
        ).data
        self.assertDictEqual(serialized_course, course_serializer.data)

    def test_update_course(self):
        """
        Tests that `CourseSerializer.update` works as expected.
        """
        course = Course.objects.create(**self.course_props)
        # Perform the update via serializer.
        updated_course_props = dict(self.course_props, course_name=u'Intro to edx-video-pipeline')
        course_serializer = CourseSerializer(instance=course, data=updated_course_props, partial=True)
        course_serializer.is_valid(raise_exception=True)
        course_serializer.save()
        # Now, see if its updated
        serialized_course = CourseSerializer(
            instance=Course.objects.first()
        ).data
        self.assertDictEqual(serialized_course, course_serializer.data)


class TestVideoSerializer(TestCase):
    """
    Tests for `VideoSerializer`.
    """
    def setUp(self):
        self.course = Course.objects.create(
            course_name=u'Intro to VEDA',
            institution=u'MAx',
            edx_classid=u'123',
            semesterid=u'2017',
            local_storedir='course_id1, course_id2',
        )

        self.video_props = dict(
            inst_class=self.course.pk,
            client_title=u'Intro to video',
            edx_id=u'12345678',
            studio_id=u'43211234',
            video_active=True,
            process_transcription=True,
            source_language=u'fr',
        )

    def test_create_video(self):
        """
        Tests that `VideoSerializer.create` works as expected.
        """
        video_serializer = VideoSerializer(data=self.video_props)
        video_serializer.is_valid(raise_exception=True)
        video_serializer.save()
        # Now, get the created video record.
        serialized_video = VideoSerializer(
            instance=Video.objects.get(**self.video_props)
        ).data
        self.assertDictEqual(serialized_video, video_serializer.data)

    def test_update_video(self):
        """
        Tests that `VideoSerializer.update` works as expected.
        """
        video = Video.objects.create(**dict(self.video_props, inst_class=self.course))
        # Perform the update via serializer.
        updated_video_props = dict(self.video_props, client_title=u'Intro to new Video')
        video_serializer = VideoSerializer(instance=video, data=updated_video_props, partial=True)
        video_serializer.is_valid(raise_exception=True)
        video_serializer.save()
        # Now, see if its updated
        serialized_video = VideoSerializer(
            instance=Video.objects.first()
        ).data
        self.assertDictEqual(serialized_video, video_serializer.data)


class TestURLSerializer(TestCase):
    """
    Tests for `URLSerializer`.
    """
    def setUp(self):
        # Setup an encode
        destination = Destination.objects.create(
            destination_name='test_destination',
            destination_nick='des',
            destination_active=True
        )
        encode = Encode.objects.create(
            encode_destination=destination,
            encode_name='desktop_mp4',
            profile_active=True,
        )

        # Setup a video
        course = Course.objects.create(
            course_name=u'Intro to VEDA',
            institution=u'MAx',
            edx_classid=u'123',
            semesterid=u'2017',
            local_storedir='course_id1, course_id2',
        )
        video = Video.objects.create(
            inst_class=course,
            client_title=u'Intro to video',
            edx_id=u'12345678',
            studio_id=u'43211234'
        )

        # Setup URL properties
        self.url_props = dict(
            encode_profile=encode.pk,
            videoID=video.pk,
            encode_url='https://www.s3.amazon.com/123.mp4'
        )

    def test_create_url(self):
        """
        Tests that `URLSerializer.create` works as expected.
        """
        url_serializer = URLSerializer(data=self.url_props)
        url_serializer.is_valid(raise_exception=True)
        url_serializer.save()
        # Now, get the created URL record.
        serialized_url = URLSerializer(
            instance=URL.objects.first()
        ).data
        self.assertDictEqual(serialized_url, url_serializer.data)


class TestEncodeSerializer(TestCase):
    """
    Tests for `EncodeSerializer`.
    """
    def test_serialized_encode(self):
        """
        Tests that serializing/de-serializing 'Encode' works as expected.
        """
        destination = Destination.objects.create(
            destination_name='test_destination',
            destination_nick='des',
            destination_active=True
        )
        encode = Encode.objects.create(
            encode_destination=destination,
            encode_name='desktop_mp4',
            profile_active=True,
        )
        self.assertEqual(Encode.objects.count(), 1)

        actual_serialized_encode = EncodeSerializer(encode).data
        for attr, actual_value in six.iteritems(actual_serialized_encode):
            expected_value = getattr(encode, attr)
            self.assertEqual(actual_value, expected_value)
