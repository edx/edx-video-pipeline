#!/usr/bin/env python

import os
import sys
import argparse
from django.db import reset_queries
import resource
import time

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.append(project_path)

"""
This is a cheapo way to get a pager (using SES)

"""
from control.veda_file_discovery import FileDiscovery
from youtube_callback.daemon import generate_course_list
from youtube_callback.sftp_id_retrieve import callfunction


class DaemonCli():

    def __init__(self):
        self.args = None
        self.ingest = False
        self.youtube = False
        self.course_list = []

    def get_args(self):
        parser = argparse.ArgumentParser()
        parser.usage = '''
        {cmd} -ingest IngestDaemon
        {cmd} -youtube YoutubeCallbackDaemon
        [-i -y]
        Use --help to see all options.
        '''.format(cmd=sys.argv[0])

        parser.add_argument(
            '-i', '--ingest',
            help='Activate alerted ingest daemon',
            action='store_true'
        )
        parser.add_argument(
            '-y', '--youtube',
            help='Activate alerted youtube callback daemon',
            action='store_true'
        )

        self.args = parser.parse_args()
        self.ingest = self.args.ingest
        self.youtube = self.args.youtube

    def run(self):
        """
        actually run the function
        """
        if self.ingest is True:
            self.ingest_daemon()

        if self.youtube is True:
            self.youtube_daemon()

    def ingest_daemon(self):
        x = 0
        while True:
            node_work_directory = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)
                ))),
                'VEDA_WORKING'
            )
            FD = FileDiscovery(
                node_work_directory=node_work_directory
            )

            FD.studio_s3_ingest()
            FD.about_video_ingest()
            reset_queries()
            x += 1
            if x >= 100:
                print 'Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                x = 0

    def youtube_daemon(self):
        x = 0
        while True:
            self.course_list = generate_course_list()
            for course in self.course_list:
                print "%s%s: Callback" % (course.institution, course.edx_classid)
                callfunction(course)

            x += 1
            if x >= 100:
                print 'Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                x = 0

            reset_queries()
            self.course_list = []
            time.sleep(10)


def main():

    DC = DaemonCli()
    DC.get_args()
    DC.run()


if __name__ == '__main__':
    sys.exit(main())
