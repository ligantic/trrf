# Generated migration to update Chinese language codes to Django standard format
from django.db import migrations


def update_chinese_language_codes(apps, schema_editor):
    """
    Update Chinese language codes from zh-CN/zh-TW to zh-hans/zh-hant.
    Django expects zh-hans and zh-hant format for Chinese Simplified and Traditional.
    """
    Language = apps.get_model("rdrf", "Language")
    
    # Update zh-CN to zh-hans
    Language.objects.filter(language_code="zh-CN").update(language_code="zh-hans")
    
    # Update zh-TW to zh-hant  
    Language.objects.filter(language_code="zh-TW").update(language_code="zh-hant")
    
    # Also update CustomUser preferred_language
    CustomUser = apps.get_model("groups", "CustomUser")
    CustomUser.objects.filter(preferred_language="zh-CN").update(preferred_language="zh-hans")
    CustomUser.objects.filter(preferred_language="zh-TW").update(preferred_language="zh-hant")
    
    # Update EmailTemplate language
    EmailTemplate = apps.get_model("rdrf", "EmailTemplate")
    EmailTemplate.objects.filter(language="zh-CN").update(language="zh-hans")
    EmailTemplate.objects.filter(language="zh-TW").update(language="zh-hant")
    
    # Update EmailNotificationHistory language
    EmailNotificationHistory = apps.get_model("rdrf", "EmailNotificationHistory")
    EmailNotificationHistory.objects.filter(language="zh-CN").update(language="zh-hans")
    EmailNotificationHistory.objects.filter(language="zh-TW").update(language="zh-hant")


def reverse_chinese_language_codes(apps, schema_editor):
    """Reverse the migration if needed."""
    Language = apps.get_model("rdrf", "Language")
    Language.objects.filter(language_code="zh-hans").update(language_code="zh-CN")
    Language.objects.filter(language_code="zh-hant").update(language_code="zh-TW")
    
    CustomUser = apps.get_model("groups", "CustomUser")
    CustomUser.objects.filter(preferred_language="zh-hans").update(preferred_language="zh-CN")
    CustomUser.objects.filter(preferred_language="zh-hant").update(preferred_language="zh-TW")
    
    EmailTemplate = apps.get_model("rdrf", "EmailTemplate")
    EmailTemplate.objects.filter(language="zh-hans").update(language="zh-CN")
    EmailTemplate.objects.filter(language="zh-hant").update(language="zh-TW")
    
    EmailNotificationHistory = apps.get_model("rdrf", "EmailNotificationHistory")
    EmailNotificationHistory.objects.filter(language="zh-hans").update(language="zh-CN")
    EmailNotificationHistory.objects.filter(language="zh-hant").update(language="zh-TW")


class Migration(migrations.Migration):

    dependencies = [
        ("rdrf", "0172_language_registryformtranslation"),
        ("groups", "0024_customuser_is_locked"),
    ]

    operations = [
        migrations.RunPython(
            update_chinese_language_codes,
            reverse_chinese_language_codes,
        ),
    ]