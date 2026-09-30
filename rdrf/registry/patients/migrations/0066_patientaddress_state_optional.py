from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0065_update_parentguardian_field_labels"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalpatientaddress",
            name="state",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="State"
            ),
        ),
        migrations.AlterField(
            model_name="patientaddress",
            name="state",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="State"
            ),
        ),
    ]
