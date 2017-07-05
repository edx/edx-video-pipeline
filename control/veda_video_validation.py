
import os
import sys
import subprocess
import fnmatch
import django
import newrelic.agent

newrelic.agent.initialize(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'veda_newrelic.ini'
    )
)

"""
VEDA Intake/Product Final Testing Suite

Should Test for:
0 size
Corrupt Files
image files (which read as 0:00 duration or N/A)
Mismatched Durations (within 5 sec)

"""
from veda_env import *


class Validation():
    """
    Expects a full filepath
    """

    def __init__(self, videofile, **kwargs):
        self.videofile = videofile
        self.mezzanine = kwargs.get('mezzanine', True)
        self.veda_id = kwargs.get('veda_id', False)

    def seconds_conversion(self, duration):
        hours = float(duration.split(':')[0])
        minutes = float(duration.split(':')[1])
        seconds = float(duration.split(':')[2])
        seconds_duration = (((hours * 60) + minutes) * 60) + seconds
        return seconds_duration

    @newrelic.agent.background_task()
    def validate(self):
        """
        Test #1 - assumes file is in 'work' directory of node
        """
        ff_command = ' '.join((
            FFPROBE,
            "\"" + self.videofile + "\""
        ))

        """
        Test if size is zero
        """
        if int(os.path.getsize(self.videofile)) == 0:

            print 'Corrupt: Invalid'
            return False

        p = subprocess.Popen(ff_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        for line in iter(p.stdout.readline, b''):
            if "Invalid data found when processing input" in line:
                print 'Corrupt: Invalid'
                return False

            if "multiple edit list entries, a/v desync might occur, patch welcome" in line:
                return False

            if "Duration: " in line:
                if "Duration: 00:00:00.0" in line:
                    return False

                elif "Duration: N/A, " in line:
                    return False
                video_duration = line.split(',')[0][::-1].split(' ')[0][::-1]

        try:
            str(video_duration)
        except:
            return False
        p.kill()

        """
        Compare Product to DB averages - pass within 5 sec

        """
        if self.mezzanine is True:
            return True

        if self.veda_id is None:
            print 'Error: Validation, encoded file no comparison ID'
            return False
        try:
            video_query = Video.objects.filter(edx_id=self.veda_id).latest()
        except:
            return False

        product_duration = float(
            self.seconds_conversion(
                duration=video_duration
            )
        )
        data_duration = float(
            self.seconds_conversion(
                duration=video_query.video_orig_duration
            )
        )
        """
        Final Test
        """
        if (data_duration - 5) <= product_duration <= (data_duration + 5):
            return True
        else:
            return False


def main():
    pass
    # V = Validation(videofile='/Users/ernst/VEDA_WORKING/fecf210f-0e94-4627-8ac3-46c2338e5897.mp4')
    # print V.validate()
    # # def __init__(self, videofile, **kwargs):


if __name__ == '__main__':
    sys.exit(main())
