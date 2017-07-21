
import os
import sys
import unittest

"""
Test heal processor

"""
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
from control.veda_heal import VedaHeal
from VEDA_OS01.models import URL, Video, Encode


class TestEncode(unittest.TestCase):

    def setUp(self):
        U = URL(
            videoID=Video.objects.filter(edx_id='XXXXXXXX2014-V00TES1').latest(),
            encode_profile=Encode.objects.get(product_spec='mobile_low'),
            encode_url='THIS Is A TEST')
        U.save()

    def test_encode_url(self):
        H = VedaHeal()
        H.discovery()


def main():
    unittest.main()


if __name__ == '__main__':
    sys.exit(main())
