from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdrf", "0173_update_chinese_language_codes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="language",
            name="language_code",
            field=models.CharField(
                choices=settings.ALL_LANGUAGES, max_length=10, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="emailtemplate",
            name="language",
            field=models.CharField(
                choices=settings.ALL_LANGUAGES, max_length=10
            ),
        ),
    ]
