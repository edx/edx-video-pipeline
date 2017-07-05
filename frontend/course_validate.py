'''
Validate Course / Predict Inputs for advanced fields
'''
import os
import uuid
import json
import yaml
import datetime

from django.utils.timezone import utc

from veda_env import *

"""
Import Django Shit
"""
auth_yaml = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'frontend_auth.yaml'
)

with open(auth_yaml, 'r') as stream:
    try:
        auth_dict = yaml.load(stream)
    except yaml.YAMLError as exc:
        print 'AUTH ERROR'


class VEDACat():

    def __init__(self, **kwargs):

        self.model_yaml = kwargs.get(
            'model_yaml',
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'veda_models.yaml'
            )
        )
        self.veda_model = self._READ_HEURISTICS()
        self.inst_code = kwargs.get('inst_code', None)
        self.course_code = kwargs.get('course_code', None)
        self.inst_list = {}
        self.return_fields = {}

    def _READ_HEURISTICS(self):
        """
        Load in the heuristics from the sidecar yaml
        """
        with open(self.model_yaml, 'r') as stream:
            try:
                set_dict = yaml.load(stream)
                return set_dict
            except yaml.YAMLError as exc:
                return None

    def institution_name(self):
        """
        Validate institution input code
        """
        try:
            inst_query = Institution.objects.filter(
                institution_code=self.inst_code
            )
            return inst_query[0].institution_name
        except:
            return 'Error'

    def institution_list(self):
        inst_query = Institution.objects.filter()
        for i in inst_query:
            self.inst_list[i.institution_code] = i.institution_name

    def validate_inst(inst_code):
        """
        check 3 digit institution code
        """
        try:
            i = Institution.objects.filter(
                institution_code=inst_code,
            )
            data = i[0].institution_name
        except:
            """
            If Institution does not Exist // since there are some blank fields
            """
            data = '0'
        return data

    def institution_data(self):
        inst_data = {}
        field_data = {}
        booleans = {}
        dropdowns = {}
        must_haves = {}
        if self.inst_code == 'NEWINST':
            # Just to get the models
            course_query = Course.objects.filter(
                institution='XXX',
                edx_classid='XXXXX'
            )

        else:
            """
            Get courses that match inst_code, active,(TODO?:) within last 6 mos.
            """
            course_query = Course.objects.filter(
                institution=self.inst_code,
                course_hold=True,
            )

        if len(course_query) > 0:
            mod_q = course_query[0]._meta.get_fields()
        else:
            """
            TODO: Build out error here
            """
            return None
        """
        Generate return fields
        """
        for m in mod_q:

            if m.name not in self.veda_model['models_nottoget']:

                field_data[m.name] = m.verbose_name

                if m.name in self.veda_model['bools']:
                    booleans[m.name] = m.verbose_name
                if m.name in self.veda_model['dropdowns']:
                    dropdowns[m.name] = m.verbose_name

                if m.name in self.veda_model['must_haves']:
                    must_haves[m.name] = m.verbose_name

                if m.name not in self.veda_model['must_haves']:
                    if self.inst_code != 'NEWINST':
                        correlation = []
                        for c in course_query:
                            correlation.append(getattr(c, m.name))

                        majority = self.simple_majority(
                            attribute_list=correlation
                        )

                        if majority['majority'] is not False:
                            inst_data[m.name] = majority['field']

        self.return_fields['field_data'] = field_data
        self.return_fields['inst_data'] = inst_data
        self.return_fields['booleans'] = booleans
        self.return_fields['dropdowns'] = dropdowns
        self.return_fields['must_haves'] = must_haves
        self.return_fields['organizational'] = self.veda_model['organizational']

    def validate_code(self, course_code):
        """
        check 5 digit course code
        """
        code_query = Course.objects.filter(
            institution=self.inst_code,
            edx_classid=course_code[0:5]
        )
        if len(code_query) > 0:
            return False

        return True

    def rand_gen(self):
        return uuid.uuid1().hex[0:5]

    def generate_code(self, gen_seed):
        code = ''

        for i in gen_seed:
            if i.isupper() and len(code) < 5:
                code += i.upper()

            if i.isdigit() and len(code) < 5:
                code += i
        if len(code) < 5:
            while len(code) < 5:
                code += 'X'

        truth = self.validate_code(
            course_code=code
        )
        if truth is True:
            return code[0:5]

        else:
            """
            Generate Random ID until it's unique
            """
            while truth is False:
                code = self.rand_gen().upper()
                truth = self.validate_code(
                    course_code=code
                )
            return code[0:5]

    def course_add(self, return_data):
        data = json.loads(return_data)
        c1 = Course(institution=data['institution'])

        if 'institution_name' in data:
            i1 = Institution(
                institution_name=data['institution_name'],
                institution_code=data['institution']
            )
            i1.save()

        '''Checkbox/false doesn't show up'''
        for x in self.veda_model['bools']:
            if x not in [a for a, b in data.iteritems()]:
                setattr(c1, x, False)

        """
        decode undecodable characters
        """
        decode_data = data
        for a, b in decode_data.iteritems():
            if isinstance(b, unicode):
                try:
                    b.encode('ascii')
                except:
                    data[a] = b.encode('ascii', errors='replace')

        """
        Translate fields into django models
        """
        for a, b in data.iteritems():
            if b is not None:

                if a != 'institution' and a != 'class_name' and len(str(b)) > 0:
                    setattr(c1, a, b)

                '''
                AutoGenerate Sometimes
                '''
                # SET RULES
                if a == 'edx_classid' and len(b) == 0:
                    self.inst_code = data['institution']

                    edx_classid = self.generate_code(
                        gen_seed=data['course_name']
                    )
                    setattr(c1, 'edx_classid', edx_classid)

                elif a == 'edx_classid' and len(b) != 0:

                    c2 = Course.objects.filter(
                        institution=data['institution'],
                        edx_classid=b
                    )

                    if len(c2) > 0:
                        self.inst_code = data['institution']

                        edx_classid = self.generate_code(
                            gen_seed=data['course_name']
                        )
                        setattr(c1, 'edx_classid', edx_classid)

                    else:
                        edx_classid = b
                        setattr(c1, 'edx_classid', edx_classid)

                if a == 'yt_channel' and len(b) == 0:
                    setattr(c1, 'yt_proc', False)
                else:
                    setattr(c1, 'yt_proc', True)

                if a == 'tp_username' and len(b) == 0:
                    setattr(c1, 'tp_proc', False)
                if a == 'tp_pass' and len(b) == 0:
                    setattr(c1, 'tp_proc', False)

        """Always Set"""
        setattr(c1, 'xue', True)
        setattr(c1, 'course_hold', True)  # Remember, this is reversed

        # Semester
        c1.semesterid = str(datetime.datetime.now().year)

        # Just in case (probably overengineered)
        c2 = Course.objects.filter(
            institution=data['institution'],
            edx_classid=edx_classid
        )
        if len(c2) > 0:
            return {}

        c1.previous_statechange = datetime.datetime.utcnow().replace(tzinfo=utc)
        c1.save()

        return_dict = {}
        return_dict['course_code'] = c1.institution + c1.edx_classid + c1.semesterid
        return_dict['studio_hex'] = c1.studio_hex

        return return_dict

    def simple_majority(self, attribute_list):
        '''
        Simple Majority Finder
        Dumbly just figures out the field attribute for 'most' of them

        '''

        comparitor = {'None': 0}
        for a in attribute_list:
            in_it = False
            for b, c in comparitor.iteritems():
                if a is None:
                    comparitor['None'] += 1
                if a == b:
                    comparitor[a] += 1
                    in_it = True
                else:
                    pass
            if in_it is False:
                comparitor[a] = 1

        data = {}

        for d, e in comparitor.iteritems():
            if e > len(attribute_list) * 0.5:
                data['majority'] = True
                data['field'] = d

        if len(data) == 0:
            data['majority'] = False

        return data


###############
def main():
    V = VEDACat()
    print V.veda_model


if __name__ == '__main__':
    sys.exit(main())
