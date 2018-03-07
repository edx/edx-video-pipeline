from django.conf.urls import url, include
from django.contrib import admin
admin.autodiscover()
from django.views.generic import TemplateView

import views

urlpatterns = [
    # '',
    url(r'^$', views.index),
    url(r'^robots\.txt$', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    # Input Form
    url(r'cat/', views.input_form),
    # Data Validation
    url(r'institution_validator/', views.institution_name),
    url(r'inst_id_validate/', views.inst_id_validate),
    url(r'institution_data/', views.institution_data),
    url(r'new_institution/', views.new_institution),
    url(r'course_id_validate/', views.course_id_validate),
    url(r'course_add/', views.course_add),
    # Uploads
    url(r'upload/', views.upload_alpha_1),
    url(r'upload_success/', views.upload_success),
    url(r'about_input/', views.about_input),
]
