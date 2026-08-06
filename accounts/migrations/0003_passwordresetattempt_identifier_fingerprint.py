from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_refreshtoken_user_identifier_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="passwordresetattempt",
            name="identifier_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
