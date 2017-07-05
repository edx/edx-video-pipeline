
import os
import os.path
import sys
import time
import pysftp

"""
Youtube Dynamic Upload

Note: This represents early VEDA work, but is functional

"""
from control_env import *


def printTotals(transferred, toBeTransferred):
    """
    try:
        sys.stdout.write('\r')
        sys.stdout.write("Transferred: {0}\tOut of: {1}\r".format(transferred, toBeTransferred))
        sys.stdout.flush()
    except:
        print 'Callback Failing'
    """
    return None


class DeliverYoutube():

    def __init__(self, veda_id, encode_profile):
        self.veda_id = veda_id
        self.encode_profile = encode_profile

        self.video = None
        self.course = None
        self.file = None

        self.youtubekey = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'dependencies',
            'youtubekey'
        )

    def upload(self):
        self.video = Video.objects.filter(
            edx_id=self.veda_id
        ).latest()

        if self.encode_profile == 'review':
            self.course = Course.objects.get(
                institution='EDX',
                edx_classid='RVW01'
            )
            self.file = self.veda_id + '_RVW.mp4'
        else:
            self.course = self.video.inst_class
            self.file = self.veda_id + '_100.mp4'
        self.csv_metadata()
        self.batch_uploader()

    def csv_metadata(self):
        """
        Generate Youtube CMS CSV metadata sidecar file

        Info: https://support.google.com/youtube/answer/6066171?hl=en (As of 05.2017)
        Supported in favor of deprecated YT-XML

        Fields in CSV are:
            filename,
            channel,
            custom_id,
            add_asset_labels,
            title,
            description,
            keywords,
            spoken_language,
            caption_file,
            caption_language,
            category,
            privacy,
            notify_subscribers,
            start_time,end_time,
            custom_thumbnail,
            ownership,
            block_outside_ownership,
            usage_policy,
            enable_content_id,
            reference_exclusions,
            match_policy,ad_types,
            ad_break_times,
            playlist_id,
            require_paid_subscription

        """
        YOUTUBE_DEFAULT_CSV_COLUMNNAMES = [
            'filename',
            'channel',
            'custom_id',
            'add_asset_labels',
            'title',
            'description',
            'keywords',
            'spoken_language',
            'caption_file',
            'caption_language',
            'category',
            'privacy',
            'notify_subscribers',
            'start_time,end_time',
            'custom_thumbnail',
            'ownership',
            'block_outside_ownership',
            'usage_policy',
            'enable_content_id',
            'reference_exclusions',
            'match_policy,ad_types',
            'ad_break_times',
            'playlist_id',
            'require_paid_subscription'
        ]
        print "%s : %s" % ("Generate CSV", str(self.video.edx_id))

        # TODO: Refactor this into centrally located util for escaping bad chars
        if self.video.client_title is not None:
            try:
                self.video.client_title.decode('ascii')
                client_title = self.video.client_title
            except:
                client_title = ''
                while len(self.video.client_title) > len(client_title):
                    try:
                        char = self.video.client_title[s1].decode('ascii')
                    except:
                        char = '-'
                    client_title += char
        else:
            client_title = self.file

        """
        This is where we can add or subtract file attributes as needed

        """
        print self.file
        metadata_dict = {
            'filename': self.file,
            'channel': self.course.yt_channel,
            'custom_id': self.video.edx_id,
            'title': client_title.replace(',', ''),
            'privacy': 'unlisted',

        }
        # Header Row
        output = ','.join(([c for c in YOUTUBE_DEFAULT_CSV_COLUMNNAMES])) + '\n'
        # Data Row
        output += ','.join(([metadata_dict.get(c, '') for c in YOUTUBE_DEFAULT_CSV_COLUMNNAMES]))  # + '\n' <--NO

        with open(os.path.join(WORK_DIRECTORY, self.video.edx_id + '_100.csv'), 'w') as c1:
            c1.write('%s %s' % (output, '\n'))

    def batch_uploader(self):
        """
        To successfully upload files to the CMS,
        upload file, upload sidecar metadata (xml)
        THEN upload empty 'delivery.complete' file

        NOTE / TODO:
        this doesn't feel like the right solution,
        -BUT-
        We'll generate a unix timestamp directory,
        then use the timestamp to find it later for the
        youtube ID / status xml

        """
        remote_directory = str(time.time()).split('.')[0]

        if not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'dependencies',
            'delivery.complete'
        )):
            with open(os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'dependencies',
                'delivery.complete'
            ), 'w') as d1:
                d1.write('')
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None

        with pysftp.Connection(
            'partnerupload.google.com',
            username=self.course.yt_logon,
            private_key=self.youtubekey,
            port=19321,
            cnopts=cnopts
        ) as s1:
            print "Go for YT : " + str(self.video.edx_id)

            s1.mkdir(remote_directory, mode=660)
            s1.cwd(remote_directory)
            s1.put(
                os.path.join(WORK_DIRECTORY, self.file),
                callback=printTotals
            )
            print
            s1.put(
                os.path.join(WORK_DIRECTORY, self.video.edx_id + '_100.csv'),
                callback=printTotals
            )
            print
            s1.put(
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'dependencies',
                    'delivery.complete'
                ),
                callback=printTotals,
                confirm=False,
                preserve_mtime=False
            )
            print

        os.remove(os.path.join(
            WORK_DIRECTORY,
            self.video.edx_id + '_100.csv'
        ))


def main():
    pass


if __name__ == "__main__":
    sys.exit(main())
