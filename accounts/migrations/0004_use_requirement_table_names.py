from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_passwordresetattempt_identifier_fingerprint"),
    ]

    operations = [
        migrations.AlterModelTable(name="accesstoken", table="access_tokens"),
        migrations.AlterModelTable(name="refreshtoken", table="refresh_tokens"),
        migrations.AlterModelTable(name="passwordhistory", table="password_histories"),
        migrations.AlterModelTable(name="passwordresetrequest", table="password_reset_requests"),
        migrations.AlterModelTable(name="passwordresetattempt", table="password_reset_attempts"),
        migrations.AlterModelTable(name="activitylog", table="activity_logs"),
    ]
