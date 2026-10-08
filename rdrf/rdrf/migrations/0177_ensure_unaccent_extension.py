from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rdrf", "0176_registrydashboardwidget_provider"),
    ]

    operations = [UnaccentExtension()]