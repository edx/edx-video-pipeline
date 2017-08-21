
import os
import sys
import uuid

import django
import yaml

from control_env import *
from dependencies.shotgun_api3 import Shotgun


"""
Get a list of needed encodes from VEDA

* Protected against extant URLs *

"""


class VedaEncode(object):

    """
    This should create a scrubbed list of encode profiles for processing
    --NOTE: post-review processing should take place on the mediateam node

    """
    def __init__(self, course_object, **kwargs):
        self.course_object = course_object
        self.encode_list = set()
        self.overencode = kwargs.get('overencode', False)
        self.veda_id = kwargs.get('veda_id', None)

        self.auth_yaml = kwargs.get(
            'auth_yaml',
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'instance_config.yaml'
            ),
        )
        self.encode_dict = self._READ_AUTH()['encode_dict']
        self.sg_server_path = self._READ_AUTH()['sg_server_path']
        self.sg_script_name = self._READ_AUTH()['sg_script_name']
        self.sg_script_key = self._READ_AUTH()['sg_script_key']

    def _READ_AUTH(self):
        if self.auth_yaml is None:
            return None
        if not os.path.exists(self.auth_yaml):
            return None

        with open(self.auth_yaml, 'r') as stream:
            try:
                auth_dict = yaml.load(stream)
                return auth_dict
            except yaml.YAMLError as exc:
                return None

    def determine_encodes(self):
        """
        Determine which encodes are needed via course-based workflow for video.
        """
        self.match_profiles()

        for encode in self.encode_list.copy():
            try:
                encode_queryset = Encode.objects.filter(product_spec=encode)
                if encode_queryset.exists():
                    if not encode_queryset.first.profile_active:
                        self.encode_list.remove(encode)
                else:
                    self.encode_list.remove(encode)
            except AttributeError:
                continue

        self.query_urls()

        if len(self.encode_list) <= 0:
            return

        return self.encode_list.copy()

    def match_profiles(self):
        if self.course_object.review_proc is True and self.veda_id is not None:
            """
            Here's where we check if this is review approved
            """
            if self.check_review_approved() is False:
                for e in self.encode_dict['review_proc']:
                    self.encode_list.add(e)
                return None

        if self.course_object.mobile_override is True:
            for e in self.encode_dict['mobile_override']:
                self.encode_list.add(e)
            return None

        for key, entry in self.encode_dict.iteritems():
            if getattr(self.course_object, key) is True:
                if key != 'review_proc':
                    for e in entry:
                        self.encode_list.add(e)

    def query_urls(self):
        """
        To allow the healing process & legacy imports
        protection against double encoding -- will take a kwarg to
        check against this 'overencode' / in case of a total redo
        """
        if self.overencode is True:
            return None
        if self.veda_id is None:
            return None

        for l in self.encode_list.copy():
            try:
                url_query = URL.objects.filter(
                    videoID=Video.objects.filter(edx_id=self.veda_id).latest(),
                    encode_profile=Encode.objects.get(product_spec=l.strip())
                )
                if len(url_query) > 0:
                    self.encode_list.remove(l)
            except AttributeError:
                continue

    def check_review_approved(self):
        if self.sg_script_key is None:
            return True

        """
        ** Mediateam only **
        Check in with SG to see if this video
        is authorized to go to final publishing
        """
        video_object = Video.objects.filter(
            edx_id=self.veda_id
        ).latest()

        if video_object.inst_class.sg_projID is None:
            return False

        sg = Shotgun(
            self.sg_server_path,
            self.sg_script_name,
            self.sg_script_key
        )

        fields = ['project', 'entity', 'sg_status_list']
        filters = [
            ['step', 'is', {'type': 'Step', 'id': 7}],
            ['project', 'is', {
                "type": "Project",
                "id": video_object.inst_class.sg_projID
            }],
        ]
        tasks = sg.find("Task", filters, fields)
        for t in tasks:
            if t['entity']['name'] == self.veda_id.split('-')[-1]:
                if t['sg_status_list'] != 'wtg':
                    return True

        return False


def main():
    pass


if __name__ == '__main__':
    sys.exit(main())
