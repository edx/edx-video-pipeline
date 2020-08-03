"""
Urls for VEDA frontend
"""


from django.views.generic import TemplateView
from django.contrib import admin
from django.conf.urls import url, include
from . import views
admin.autodiscover()


urlpatterns = [
    url(r'^$', views.index),
    url(r'^robots\.txt$', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    url(r'^admin/', admin.site.urls),
    # Input Form
    url(r'cat/', views.input_form),
    # Heal form
    url(r'heal/', views.heal_form),
    # Data Validation
    url(r'institution_validator/', views.institution_name),
    url(r'inst_id_validate/', views.inst_id_validate),
    url(r'institution_data/', views.institution_data),
    url(r'new_institution/', views.new_institution),
    url(r'course_id_validate/', views.course_id_validate),
    url(r'course_add/', views.course_add),
    # Uploads
    url(r'upload/', views.upload_page_redirect_view),
    url(r'upload_success/', views.upload_success),
    url(r'about_input/', views.about_input),
]
