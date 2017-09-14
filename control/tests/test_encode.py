
import os
import sys
import unittest
from django.test import TestCase

from control.veda_encode import VedaEncode
from VEDA_OS01.models import URL, Course, Destination, Encode, Video

"""
Test encode profiler

"""

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))


VIDEO_DATA = {
    'studio_id': '12345'
}


class TestEncode(TestCase):

    def setUp(self):
        self.veda_id = 'XXXXXXXX2016-V00TEST'
        self.course_object = Course.objects.create(
            institution='XXX',
            edx_classid='XXXXX'
        )

        self.video = Video.objects.create(
            inst_class=self.course_object,
            studio_id='12345',
            edx_id=self.veda_id,
        )

        Encode.objects.create(
            product_spec='mobile_low',
            encode_destination=Destination.objects.create(destination_name='destination_name'),
            profile_active=True
        )

        Encode.objects.create(
            product_spec='desktop_mp4',
            encode_destination=Destination.objects.create(destination_name='destination_name'),
            profile_active=True
        )

        self.E = VedaEncode(
            course_object=self.course_object,
            veda_id=self.veda_id
        )

    def test_encode_url(self):
        """
        gen baseline, gen a url, test against baseline
        """
        URL.objects.filter(
            videoID=Video.objects.filter(edx_id=self.veda_id).latest()
        ).delete()
        encode_list = self.E.determine_encodes()
        baseline = len(encode_list)
        self.assertTrue(isinstance(encode_list, set))

        self.E.encode_list = set()
        url = URL(
            videoID=Video.objects.filter(edx_id=self.veda_id).latest(),
            encode_profile=Encode.objects.get(product_spec='mobile_low'),
            encode_url='THIS Is A TEST'
        )
        url.save()
        encode_list = self.E.determine_encodes()
        self.assertTrue(len(encode_list) == baseline - 1)

        self.E.encode_list = set()
        URL.objects.filter(
            videoID=Video.objects.filter(edx_id=self.veda_id).latest(),
        ).delete()
        encode_list = self.E.determine_encodes()
        self.assertTrue(len(encode_list) == baseline)


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())

    '''
    Save for poss future test

    # import celeryapp

    # co = Course.objects.get(institution='XXX', edx_classid='C93BC')
    # vid = 'XXXC93BC2016-V003500'
    # v = VedaEncode(course_object=co, veda_id=vid)
    # encode_list = v.determine_encodes()
    # for e in encode_list:
    #     veda_id = vid
    #     encode_profile = e
    #     jobid = uuid.uuid1().hex[0:10]
    #     # celeryapp.worker_task_fire.apply_async(
    #     #     (veda_id, encode_profile, jobid),
    #     #     queue='encode_worker'
    #     #     )
    '''
