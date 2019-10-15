"""
VEDA Intake/Product Final Testing Suite

Should Test for:
0 size
Corrupt Files
image files (which read as 0:00 duration or N/A)
Mismatched Durations (within 5 sec)

"""

from __future__ import absolute_import
import logging
import os
import subprocess
import sys

from control.control_env import FFPROBE
from VEDA_OS01.models import Video

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


class Validation(object):
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

    def validate(self):
        """
        Video validation probe
        """

        # Test #1
        # Assumes file is in 'work' directory of node.
        # Probe for metadata, ditch on common/found errors
        ff_command = ' '.join((
            FFPROBE,
            "\"" + self.videofile + "\""
        ))

        video_duration = None

        if int(os.path.getsize(self.videofile)) == 0:
            LOGGER.info('[VALIDATION] {id} : CORRUPT/File size is zero'.format(id=self.videofile))
            return False

        p = subprocess.Popen(ff_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        for line in iter(p.stdout.readline, b''):
            line = line.decode('utf-8')
            if "Invalid data found when processing input" in line:
                LOGGER.info('[VALIDATION] {id} : CORRUPT/Invalid data on input'.format(id=self.videofile))
                return False

            if "multiple edit list entries, a/v desync might occur, patch welcome" in line:
                LOGGER.info('[VALIDATION] {id} : CORRUPT/Desync error'.format(id=self.videofile))
                return False

            if "command not found" in line:
                LOGGER.info('[VALIDATION] {id} : CORRUPT/Atypical file error'.format(id=self.videofile))
                return False

            if "Duration: " in line:
                if "Duration: 00:00:00.0" in line:
                    LOGGER.info('[VALIDATION] {id} : CORRUPT/Duration is zero'.format(id=self.videofile))
                    return False

                elif "Duration: N/A, " in line:
                    LOGGER.info('[VALIDATION] {id} : CORRUPT/Duration N/A'.format(id=self.videofile))
                    return False
                video_duration = line.split(',')[0][::-1].split(' ')[0][::-1]

        if not video_duration:
            LOGGER.info('[VALIDATION] {id} : CORRUPT/No Duration'.format(id=self.videofile))
            p.kill()
            return False
        p.kill()

        # Test #2
        # Compare Product to DB averages
        # pass is durations within 5 sec or each other
        if self.mezzanine is True:
            # Return if original/source rawfile
            LOGGER.info('[VALIDATION] {id} : VALID/Mezzanine file'.format(id=self.videofile))
            return True

        if self.veda_id is None:
            LOGGER.info('[VALIDATION] {id} : CORRUPT/Validation, No VEDA ID'.format(id=self.videofile))
            return False
        try:
            video_query = Video.objects.filter(edx_id=self.veda_id).latest()
        except:
            LOGGER.info(
                '[VALIDATION] {id} : CORRUPT/Validation, No recorded ID for comparison'.format(id=self.videofile)
            )
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

        if (data_duration - 5) <= product_duration <= (data_duration + 5):
            LOGGER.info('[VALIDATION] {id} : VALID'.format(id=self.videofile))
            return True
        else:
            LOGGER.info('[VALIDATION] {id} : CORRUPT/Duration mismatch'.format(id=self.videofile))
            return False
