# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2017-10-24 20:03
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('VEDA_OS01', '0002_auto_20171016_1211'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='course',
            name='xuetang_proc',
        ),
        migrations.RemoveField(
            model_name='encode',
            name='xuetang_proc',
        ),
        migrations.RemoveField(
            model_name='url',
            name='md5_sum',
        ),
        migrations.RemoveField(
            model_name='url',
            name='xuetang_input',
        ),
    ]
