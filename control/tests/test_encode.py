
import os
import sys
import unittest

"""
Test encode profiler

"""

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
from veda_env import *
from veda_encode import VedaEncode


class TestEncode(unittest.TestCase):

    def setUp(self):
        self.course_object = Course.objects.get(
            institution='XXX',
            edx_classid='XXXXX'
        )
        self.veda_id = 'XXXXXXXX2016-V00TEST'
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
        self.assertTrue(isinstance(encode_list, list))

        self.E.encode_list = []
        U = URL(
            videoID=Video.objects.filter(edx_id=self.veda_id).latest(),
            encode_profile=Encode.objects.get(product_spec='mobile_low'),
            encode_url='THIS Is A TEST'
        )
        U.save()
        encode_list = self.E.determine_encodes()
        self.assertTrue(len(encode_list) == baseline - 1)

        self.E.encode_list = []

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
