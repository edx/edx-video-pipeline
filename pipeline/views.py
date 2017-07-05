"""views"""

from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

from rest_framework import renderers
from rest_framework import viewsets
from rest_framework.decorators import detail_route
from rest_framework import filters

from api import token_finisher

from pipeline.models import Course, Video, URL, Encode
from pipeline.serializers import CourseSerializer
from pipeline.serializers import VideoSerializer
from pipeline.serializers import EncodeSerializer
from pipeline.serializers import URLSerializer


class CourseViewSet(viewsets.ModelViewSet):

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = (
        'institution',
        'edx_classid',
        'proc_loc',
        'course_hold',
        'sg_projID'
    )

    @detail_route(renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        course = self.get_object()
        return Response(course.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class VideoViewSet(viewsets.ModelViewSet):

    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('inst_class', 'edx_id')

    @detail_route(renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        video = self.get_object()
        return Response(video.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class EncodeViewSet(viewsets.ModelViewSet):

    queryset = Encode.objects.all()
    serializer_class = EncodeSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('encode_filetype', 'encode_suffix', 'product_spec')

    @detail_route(renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        encode = self.get_object()
        return Response(encode.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


class URLViewSet(viewsets.ModelViewSet):

    queryset = URL.objects.all()
    serializer_class = URLSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = (
        'videoID__edx_id',
        'encode_profile__encode_suffix',
        'encode_profile__encode_filetype'
    )

    @detail_route(renderer_classes=[renderers.StaticHTMLRenderer])
    def highlight(self, request, *args, **kwargs):
        url = self.get_object()
        return Response(url.highlighted)

    @csrf_exempt
    def perform_create(self, serializer):
        serializer.save()


@csrf_exempt
def token_auth(request):
    """

    This is a hack to override the "Authorize" step in token generation

    """
    if request.method == 'POST':
        complete = token_finisher(request.POST['data'])
        return HttpResponse(complete)
    else:
        return HttpResponse(status=404)


def user_login(request):
    if request.user.is_authenticated():
        return HttpResponseRedirect(request.path)
    else:
        return HttpResponseRedirect('../admin')  # settings.LOGIN_REDIRECT_URL)


if __name__ == "__main__":
    course_view()
