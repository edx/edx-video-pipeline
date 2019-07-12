
"""
Fix resolution 'progressive)' bug

"""
from __future__ import absolute_import
from __future__ import print_function
import os
import sys
import datetime
from datetime import timedelta

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
# import abvid_reporting
from veda_heal import VedaHeal
from VEDA_OS01.models import Video

sick_list = [
    'EDXABVID2014-V148900',
    'MCHCFPXX2016-V006200',
    'PRIMGWXXT315-V011000',
    'PRIMGWXXT315-V011100',
    'MIT143102016-V032100',
    'MIT143102016-V032200',
    'MIT143102016-V032300',
    'MIT15662T115-V014900',
    'MIT15662T115-V015000',
    'MIT15662T115-V015100',
    'MIT15662T115-V015200',
    'HKUHKCGL2016-V017700',
    'HKUHKCGL2016-V017800',
    'HKUHKCGL2016-V017900',
    'MIT21W78T114-V006000',
    'MIT21W78T114-V006100',
    'MIT21W78T114-V006200',
    'MIT21W78T114-V006300',
    'MIT21W78T114-V006400',
    'MIT21W78T114-V006500',
    'MIT21W78T114-V006600',
    'MIT21W78T114-V006700',
    'MIT15662T115-V015300',
    'MIT15662T115-V015400',
    'MIT15662T115-V015600',
    'MIT15662T115-V015900',
    'MIT15662T115-V016200',
    'MIT15662T115-V016500',
    'HKUDEXXX2016-V031200',
    'HKUDEXXX2016-V031300',
    'MIT21W78T114-V006800',
    'MITSCTSX2016-V006000',
    'HKUDEXXX2016-V031400',
    'MIT15662T115-V016600',
    'HKUDEXXX2016-V031500',
    'HARCHEM12016-V006900',
    'HARCHEM12016-V007000',
    'HARCHEM12016-V007100',
    'HARCHEM12016-V007200',
    'HARCHEM12016-V007300',
    'HARCHEM12016-V007400',
    'HARCHEM12016-V007500',
    'HARCHEM12016-V007600',
    'HARCHEM12016-V007700',
    'HARCHEM12016-V007800',
    'HARCHEM12016-V007900',
    'HARCHEM12016-V008000',
    'HARCHEM12016-V008100',
    'HARCHEM12016-V008200',
    'HARCHEM12016-V008300',
    'HARCHEM12016-V008400',
    'HARCHEM12016-V008500',
    'HARCHEM12016-V008600',
    'HARCHEM12016-V008700',
    'HARCHEM12016-V008800',
    'HARCHEM12016-V008900',
    'HARCHEM12016-V009000',
    'HARCHEM12016-V009100',
    'HARCHEM12016-V009200',
    'HARCHEM12016-V009300',
    'HARCHEM12016-V009400',
    'HARCHEM12016-V009500',
    'HARCHEM12016-V009600',
    'HARCHEM12016-V009700',
    'HARCHEM12016-V009800',
    'HARCHEM12016-V009900',
    'MCHLCGBG2016-V004100',
    'MCHLCGBG2016-V004200',
    'MCHLCGBG2016-V004300',
    'MITSCTSX2016-V006200',
]


def get_videos():
    video_q = Video.objects.filter(
        video_trans_start__gt=datetime.datetime.utcnow() - timedelta(days=7)
        # video_orig_resolution='progressive)'
        )

    # video_query =  Video.objects.filter(
        # edx_id='EDXABVID2014-V148900'
        # )
    for v in video_q:
        if ')' in v.video_orig_resolution:
            print(v.edx_id)

        # Video.objects.filter(pk=v.pk).update(video_orig_resolution='1920x1080')
        # print '***'
        # VH = VedaHeal(
        #     video_query=Video.objects.filter(
        #         pk=v.pk
        #         )
        #     )
        # VH.send_encodes()
        # break

if __name__ == '__main__':
    get_videos()
