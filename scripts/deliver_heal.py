
import os
import sys
import datetime
from datetime import timedelta
from django.utils.timezone import utc

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

from control.celeryapp import deliverable_route
from control.veda_heal import VedaHeal
from pipeline.models import Video


def get_videos():
    video_query = Video.objects.filter(
        video_trans_start__lt=(datetime.datetime.now().replace(tzinfo=utc)) - timedelta(days=7)
    )
    for v in video_query:
        print v.edx_id
        VH = VedaHeal()
        encode_list = VH.determine_fault(video_object=v)
        # if len(encode_list) > 0:
        #     for e in encode_list:
        #         deliverable_route(veda_id=v.edx_id, encode_profile=e)
        # print encode_list
        break

if __name__ == '__main__':
    get_videos()
