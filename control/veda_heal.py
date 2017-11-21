"""
Heal Process

Roll through videos, check for completion
    - reencode endpoints
    - fix data (if wrong), including on VAL
    - reschedule self

"""
import datetime
from datetime import timedelta
import logging
import os
import sys
import uuid
import yaml

from django.utils.timezone import utc

from VEDA_OS01.models import Encode, URL, Video
from VEDA_OS01.utils import VAL_TRANSCRIPT_STATUS_MAP

import celeryapp
from control_env import WORK_DIRECTORY
from veda_encode import VedaEncode
from veda_val import VALAPICall
from VEDA.utils import get_config

time_safetygap = datetime.datetime.utcnow().replace(tzinfo=utc) - timedelta(days=1)

LOGGER = logging.getLogger(__name__)
# TODO: Remove this temporary logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


class VedaHeal(object):
    """
    Maintenance process for finding and repairing failed encodes

    """
    def __init__(self, **kwargs):
        self.current_time = datetime.datetime.utcnow().replace(tzinfo=utc)
        self.auth_dict = get_config()
        # for individuals
        self.video_query = kwargs.get('video_query', None)
        self.freezing_bug = kwargs.get('freezing_bug', True)
        self.val_status = None
        self.retry_barrier_hours = 24

    def discovery(self):
        self.video_query = Video.objects.filter(
            video_trans_start__lt=self.current_time - timedelta(
                hours=self.auth_dict['heal_start']
            ),
            video_trans_start__gt=self.current_time - timedelta(
                hours=self.auth_dict['heal_end']
            )
        )

        self.send_encodes()

    def send_encodes(self):
        for v in self.video_query:
            encode_list = self.determine_fault(video_object=v)
            # Using the 'Video Proto' Model
            if self.val_status is not None:
                # Update to VAL is also happening for those videos which are already marked complete,
                # All these retries are for the data-parity between VAL and VEDA, as calls to VAL api are
                # unreliable and times out. For a completed Video, VEDA heal will keep doing this unless
                # the Video is old enough and escapes from the time-span that HEAL is picking up on.
                # cc Greg Martin
                VAC = VALAPICall(
                    video_proto=None,
                    video_object=v,
                    val_status=self.val_status,
                )
                VAC.call()
            self.val_status = None

            # Enqueue
            if self.auth_dict['rabbitmq_broker'] is not None:
                for e in encode_list:
                    veda_id = v.edx_id
                    encode_profile = e
                    jobid = uuid.uuid1().hex[0:10]
                    celeryapp.worker_task_fire.apply_async(
                        (veda_id, encode_profile, jobid),
                        queue=self.auth_dict['celery_worker_queue'].split(',')[0]
                    )

    def determine_fault(self, video_object):
        """
        Determine expected and completed encodes
        """
        LOGGER.info('[HEAL] : {id}'.format(id=video_object.edx_id))
        if self.freezing_bug is True:
            if video_object.video_trans_status == 'Corrupt File':
                self.val_status = 'file_corrupt'
                return []

        if video_object.video_trans_status == 'Review Reject' or video_object.video_trans_status == 'Review Hold' or \
            video_object.video_trans_status == 'Review Hold':
            return []

        if video_object.video_trans_status == 'Youtube Duplicate':
            self.val_status = 'duplicate'
            return []

        """
        Finally, determine encodes
        """
        uncompleted_encodes = VedaEncode(
            course_object=video_object.inst_class,
            veda_id=video_object.edx_id
        ).determine_encodes()
        expected_encodes = VedaEncode(
            course_object=video_object.inst_class,
        ).determine_encodes()
        try:
            if uncompleted_encodes:
                uncompleted_encodes.remove('review')
        except KeyError:
            pass

        requeued_encodes = self.differentiate_encodes(uncompleted_encodes, expected_encodes, video_object)
        LOGGER.info(
            '[HEAL] : Status: {status}, Encodes: {encodes}'.format(status=self.val_status, encodes=requeued_encodes)
        )
        return requeued_encodes

    def differentiate_encodes(self, uncompleted_encodes, expected_encodes, video_object):
        """
        Update video status if complete
        """
        # Video Status Updating
        check_list = []
        if uncompleted_encodes is not None:
            for e in uncompleted_encodes:
                # These encodes don't count towards 'file_complete'
                if e != 'mobile_high' and e != 'audio_mp3' and e != 'review':
                    check_list.append(e)

        # See if VEDA's Video data model is already having transcript status which corresponds
        # to any of Val's Video transcript statuses. If its True, set `val_status` to that status
        # instead of `file_complete` as transcription phase comes after encoding phase of a Video,
        # and `file_complete` shows that a Video's encodes are complete, while there may be possibility
        # that the Video has gone through transcription phase as well after the encodes were ready.
        val_transcription_status = VAL_TRANSCRIPT_STATUS_MAP.get(video_object.transcript_status, None)
        if check_list is None or len(check_list) == 0:
            if val_transcription_status:
                self.val_status = val_transcription_status
            else:
                self.val_status = 'file_complete'

            # File is complete!
            # Check for data parity, and call done
            if video_object.video_trans_status != 'Complete':
                Video.objects.filter(
                    edx_id=video_object.edx_id
                ).update(
                    video_trans_status='Complete',
                    video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc)
                )
        if not uncompleted_encodes or len(uncompleted_encodes) == 0:
            return []

        if self.freezing_bug:
            if self.determine_longterm_corrupt(uncompleted_encodes, expected_encodes, video_object):
                return []

        complete_statuses = ['file_complete']
        if val_transcription_status:
            complete_statuses.append(val_transcription_status)

        if self.val_status not in complete_statuses:
            self.val_status = 'transcode_queue'
        return uncompleted_encodes

    def determine_longterm_corrupt(self, uncompleted_encodes, expected_encodes, video_object):
        """
        get baseline // if there are == encodes and baseline,
        mark file corrupt -- just run the query again with
        no veda_id
        """

        try:
            expected_encodes.remove('hls')
        except ValueError:
            pass
        # Mark File Corrupt, accounting for migrated URLs
        if len(expected_encodes) == len(uncompleted_encodes) - 1 and len(expected_encodes) > 1:
            try:
                url_test = URL.objects.filter(
                    videoID=Video.objects.filter(
                        edx_id=video_object.edx_id
                    ).latest()
                ).exclude(
                    encode_profile=Encode.objects.get(
                        product_spec='hls'
                    )
                )
            except AttributeError:
                url_test = []
            retry_barrier = datetime.datetime.utcnow().replace(tzinfo=utc) - timedelta(hours=self.retry_barrier_hours)

            if video_object.video_trans_start < retry_barrier:
                if len(url_test) < 1:
                    try:
                        Video.objects.filter(
                            edx_id=video_object.edx_id
                        ).update(
                            video_trans_status='Corrupt File',
                            video_trans_end=datetime.datetime.utcnow().replace(tzinfo=utc)
                        )
                    except AttributeError:
                        pass
                    self.val_status = 'file_corrupt'
                    return True
        return False

    def purge(self):
        """
        Purge Work Directory

        """
        for file in os.listdir(WORK_DIRECTORY):
            full_filepath = os.path.join(WORK_DIRECTORY, file)
            filetime = datetime.datetime.utcfromtimestamp(
                os.path.getmtime(
                    full_filepath
                )
            ).replace(tzinfo=utc)
            if filetime < time_safetygap:
                print file + " : WORK PURGE"
                os.remove(full_filepath)


def main():
    VH = VedaHeal()
    VH.discovery()

if __name__ == '__main__':
    sys.exit(main())
