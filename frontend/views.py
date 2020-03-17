# VEDA F/E Views

from __future__ import absolute_import
import json
import datetime
from datetime import timedelta
import base64
import hmac
import hashlib
import uuid
from control import celeryapp
from django.http import HttpResponse
from django.template import RequestContext, loader
from django.http import HttpResponseRedirect
from django.shortcuts import render
from .frontend_env import *
from .course_validate import VEDACat
from .abvid_validate import validate_incoming, create_record, send_to_pipeline
from VEDA.utils import get_config

"""
Here's the links for the main Page
:::
"""
links = {
    'VEDA_CAT': '../../cat/',
    'Upload Page': '../../upload/',
}


def index(request):
    if not request.user.is_authenticated():
        auth = 'NO'
        linkers = ''
    else:
        auth = 'YES'
        linkers = links
    template = loader.get_template('index.html')

    context = {
        'links': linkers,
        'auth': auth
    }

    return HttpResponse(template.render(context=context, request=request))


def input_form(request):
    """
    Course Addition Tool Endpoints
    """
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/admin/login/?next=%s' % request.path)

    VC1 = VEDACat()
    VC1.institution_list()

    inst_list = json.dumps(VC1.inst_list)

    template = loader.get_template('course_form.html')
    context = {
        'institution_list': inst_list
    }
    return HttpResponse(template.render(context=context, request=request))


def heal_form(request):
    template = loader.get_template("heal.html")
    if request.method == 'POST':
        veda_id = request.POST['veda_id']
        auth_dict = get_config()
        result = celeryapp.web_healer.apply_async(
                    args=[veda_id],
                    queue=auth_dict['celery_online_heal_queue'],
                    connect_timeout=3
                    )
        context = {'result': result}
        return HttpResponse(template.render(context=context, request=request))
    return HttpResponse(template.render(request=request))


def institution_name(request):
    if request.method == 'POST' and request.POST['input_text'] != 'NEWINST':
        inst_code = request.POST['input_text']
        VC1 = VEDACat(inst_code=inst_code)
        institution_name = VC1.institution_name()

    else:
        institution_name = ''

    return HttpResponse(
        json.dumps(institution_name),
        content_type="application/json"
    )


def institution_data(request):
    inst_code = request.POST['inst_code']
    if inst_code != 'NEWINST':
        VC1 = VEDACat(inst_code=inst_code[0:3])

    else:
        VC1 = VEDACat(inst_code=inst_code)

    VC1.institution_data()
    data = VC1.return_fields

    return HttpResponse(
        json.dumps(data),
        content_type="application/json"
    )


def inst_id_validate(request):
    if request.method == 'POST':
        try:
            VC1 = VEDACat(inst_code=request.POST['input_text'])
            data = VC1.validate_inst()
        except:
            data = ''
    else:
        data = ''

    return HttpResponse(
        json.dumps(data),
        content_type="application/json"
    )


def new_institution(request):
    data = ''
    return HttpResponse(
        json.dumps(data),
        content_type="application/json"
    )


def course_id_validate(request):

    if request.method == 'POST' and 'edx_classid' in request.POST:
        inst_code = request.POST['institution']
        course_code = request.POST['edx_classid']

        VC1 = VEDACat(inst_code=inst_code[0:3])
        data = VC1.validate_code(course_code=course_code[0:5])

    else:
        data = False

    return HttpResponse(
        json.dumps(data),
        content_type="application/json"
    )


def course_add(request):
    if request.method == 'POST':
        return_data = request.POST['return_data']

        VC1 = VEDACat()
        course_data = VC1.course_add(
            return_data=return_data
        )
    else:
        course_data = ''

    return HttpResponse(
        json.dumps(course_data),
        content_type="application/json"
    )


###############
# UPLOAD PAGE #
###############
def upload_alpha_1(request):
    """
    TODO:
        Get This to expire in 24h / 1 Time URL
        Generate metadata From Fields
        Auth?
    """
    auth_dict = get_config()

    policy_expiration = datetime.datetime.utcnow() + timedelta(hours=24)
    policy_exp = str(policy_expiration).replace(' ', 'T').split('.')[0] + 'Z'

    policy_document = bytes(' \
    {\"expiration\": \"' + policy_exp + '\", \
    \"conditions\": [ \
    {\"bucket\": \"' + auth_dict['veda_upload_bucket'] + '\"}, \
    [\"starts-with\", \"$key\", \"\"], \
    {\"acl\": \"private\"}, \
    {\"success_action_redirect\": \"../upload_success/\"}, \
    [\"starts-with\", \"$Content-Type\", \"\"], \
    [\"content-length-range\", 0, 500000000000] \
    ] \
    } ', 'utf-8')

    abvid_serial = uuid.uuid1().hex[0:10]
    policy = base64.b64encode(policy_document)

    signature = base64.b64encode(hmac.new(
        auth_dict['veda_secret_access_key'].encode('utf-8'),
        policy,
        hashlib.sha1
    ).digest()).decode('utf-8')
    template = loader.get_template('upload_video.html')

    context = {
            'policy': policy.decode('utf-8'),
            'signature': signature,
            'abvid_serial': abvid_serial,
            'access_key': auth_dict['veda_access_key_id'],
            'upload_bucket': auth_dict['veda_upload_bucket'],
    }

    return HttpResponse(template.render(context=context, request=request))


def upload_success(request):
    template = loader.get_template('upload_success.html')
    return HttpResponse(template.render(request=request))


def about_input(request):

    if request.method == 'POST':
        upload_data = {}

        if 'success' in request.POST:
            upload_data['abvid_serial'] = request.POST['abvid_serial']
            upload_data['success'] = request.POST['success']

            goahead = send_to_pipeline(upload_data)

        elif 'orig_filename' in request.POST:
            upload_data['abvid_serial'] = request.POST['abvid_serial']
            upload_data['orig_filename'] = request.POST['orig_filename']
            upload_data['goahead'] = False

            goahead = validate_incoming(upload_data=upload_data)

        else:
            upload_data['abvid_serial'] = request.POST['abvid_serial']
            upload_data['pm_email'] = request.POST['pm_email']
            upload_data['studio_url'] = request.POST['studio_url']
            upload_data['course_name'] = request.POST['course_name']

            goahead = create_record(upload_data=upload_data)

    else:
        goahead = False

    return HttpResponse(
        json.dumps(goahead),
        content_type="application/json"
    )
