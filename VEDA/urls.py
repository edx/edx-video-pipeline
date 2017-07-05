import sys
import os

sys.path.append(os.path.abspath(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

from django.conf import settings
from rest_framework.routers import DefaultRouter
from django.conf.urls import patterns, include, url
from django.contrib import admin

from VEDA_OS01 import views

router = DefaultRouter()
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
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    # Cheap auth server
    url(r'^veda_auth/', views.token_auth)
]
