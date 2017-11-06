import sys
import os

sys.path.append(os.path.abspath(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VEDA.settings.local')

from django.conf import settings
from rest_framework import routers
# from rest_framework.routers import DefaultRouter
from django.conf.urls import patterns, include, url
from django.contrib import admin

from VEDA_OS01 import views, transcripts

router = routers.DefaultRouter()
admin.autodiscover()

router.register(r'courses', views.CourseViewSet)
router.register(r'videos', views.VideoViewSet)
router.register(r'encodes', views.EncodeViewSet)
router.register(r'urls', views.URLViewSet)

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^static/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.STATIC_ROOT}),
    # Front End
    url(r'^', include('frontend.urls')),
    # API
    url(r'^login/', views.user_login),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login', ),
    url(r'^accounts/logout/$', 'django.contrib.auth.views.logout'),
    url(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    url(r'^api/', include(router.urls)),
    # Transcript credentials handler view
    url(
        regex=r'^api/transcript_credentials/$',
        view=views.TranscriptCredentialsView.as_view(),
        name='transcript_credentials'
    ),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    # Cheap auth server
    url(r'^veda_auth/', views.token_auth),
    url(
        regex=r'^cielo24/transcript_completed/(?P<token>[\w]+)$',
        view=transcripts.Cielo24CallbackHandlerView.as_view(),
        name='cielo24_transcript_completed'
    ),
    # 3PlayMedia callback handler view
    url(
        regex=r'^3playmedia/transcripts/handle/(?P<token>[\w]+)$',
        view=transcripts.ThreePlayMediaCallbackHandlerView.as_view(),
        name='3play_media_callback'
    ),
    url(
        r'^heartbeat/$',
        view=views.heartbeat,
        name='heartbeat'
    ),
]
