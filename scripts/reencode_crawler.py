
import os
import sys
import datetime
import time

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

from control.veda_heal import VedaHeal
from VEDA_OS01.models import URL, Encode, Video

"""
Set your globals here
"""
CRAWL_SUFFIX = 'HLS'
CRAWL_START = datetime.datetime.strptime('Feb 1 2017 00:01', '%b %d %Y %H:%M')
CRAWL_EPOCH = datetime.datetime.strptime('Apr 12 2017 00:01', '%b %d %Y %H:%M')

BATCH_SIZE = 10
SLEEP_TIME = 1200


# NOTE: MSXSBVCP2017-V002600_100

class ReEncodeCrawler:

    def __init__(self):
        self.crawl_start = CRAWL_START
        self.crawl_end = CRAWL_EPOCH
        self.crawl_suffix = CRAWL_SUFFIX
        self.url_query = None

    def crawl(self):
        self._url_query()
        # self._run_reencode()

    def _url_query(self):
        self.url_query = URL.objects.filter(
            url_date__gt=self.crawl_start,
            url_date__lt=self.crawl_end,
            encode_profile=Encode.objects.get(
                encode_suffix=self.crawl_suffix
            )
        )
        print len(self.url_query)


    def _run_reencode(self):
        batching = 0

        for u in self.url_query:
            print u.encode_url
            if batching >= BATCH_SIZE:
                print "%s :: %s" % (
                    "Sleeping", 
                    "BatchSize"
                )   
                time.sleep(SLEEP_TIME)
                batching = 0

            print "%s : %s" % (u.encode_url, u.url_date)
            URL.objects.filter(pk=u.pk).delete()
            """Must be sent to heal as iterable"""
            video_query = Video.objects.filter(pk=u.videoID.pk)
            VH = VedaHeal(
                video_query=video_query
            )
            VH.send_encodes()
            batching += 1


def main():
    REEC = ReEncodeCrawler()
    REEC.crawl()


if __name__ == '__main__':
    sys.exit(main())


'''
Manual HEAL IDs

GEOB3DAE2017-V006300



'''
