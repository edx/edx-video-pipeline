import views
from django.conf.urls import *
from django.views.generic import TemplateView
from django.contrib import admin
admin.autodiscover()


urlpatterns = patterns(
    '',
    (r'^$', views.index),
    (r'^robots\.txt$', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    (r'^admin/', include(admin.site.urls)),
    # Input Form
    (r'cat/', views.input_form),
    # Heal form
    (r'heal/', views.heal_form),
    # Data Validation
    (r'institution_validator/', views.institution_name),
    (r'inst_id_validate/', views.inst_id_validate),
    (r'institution_data/', views.institution_data),
    (r'new_institution/', views.new_institution),
    (r'course_id_validate/', views.course_id_validate),
    (r'course_add/', views.course_add),
    # Uploads
    (r'upload/', views.upload_alpha_1),
    (r'upload_success/', views.upload_success),
    (r'about_input/', views.about_input),
)
