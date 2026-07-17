from django.conf import settings
from django.db import migrations, models


def update_chinese_language_codes(apps, schema_editor):
    Language = apps.get_model("rdrf", "Language")
    Language.objects.filter(language_code="zh-CN").update(language_code="zh-hans")
    Language.objects.filter(language_code="zh-TW").update(language_code="zh-hant")

    CustomUser = apps.get_model("groups", "CustomUser")
    CustomUser.objects.filter(preferred_language="zh-CN").update(
        preferred_language="zh-hans"
    )
    CustomUser.objects.filter(preferred_language="zh-TW").update(
        preferred_language="zh-hant"
    )

    EmailTemplate = apps.get_model("rdrf", "EmailTemplate")
    EmailTemplate.objects.filter(language="zh-CN").update(language="zh-hans")
    EmailTemplate.objects.filter(language="zh-TW").update(language="zh-hant")

    EmailNotificationHistory = apps.get_model("rdrf", "EmailNotificationHistory")
    EmailNotificationHistory.objects.filter(language="zh-CN").update(
        language="zh-hans"
    )
    EmailNotificationHistory.objects.filter(language="zh-TW").update(
        language="zh-hant"
    )


def reverse_chinese_language_codes(apps, schema_editor):
    Language = apps.get_model("rdrf", "Language")
    Language.objects.filter(language_code="zh-hans").update(language_code="zh-CN")
    Language.objects.filter(language_code="zh-hant").update(language_code="zh-TW")

    CustomUser = apps.get_model("groups", "CustomUser")
    CustomUser.objects.filter(preferred_language="zh-hans").update(
        preferred_language="zh-CN"
    )
    CustomUser.objects.filter(preferred_language="zh-hant").update(
        preferred_language="zh-TW"
    )

    EmailTemplate = apps.get_model("rdrf", "EmailTemplate")
    EmailTemplate.objects.filter(language="zh-hans").update(language="zh-CN")
    EmailTemplate.objects.filter(language="zh-hant").update(language="zh-TW")

    EmailNotificationHistory = apps.get_model("rdrf", "EmailNotificationHistory")
    EmailNotificationHistory.objects.filter(language="zh-hans").update(language="zh-CN")
    EmailNotificationHistory.objects.filter(language="zh-hant").update(language="zh-TW")


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
        migrations.RunPython(
            update_chinese_language_codes,
            reverse_chinese_language_codes,
        ),
    ]
