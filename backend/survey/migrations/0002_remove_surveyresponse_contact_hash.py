# SURVEY-R3 (2026-11-07): the optional e-mail, kept as an HMAC, is gone — a hashed address is
# pseudonymous rather than anonymous, and a withdrawal by mail showed the controller the address.
# The one-time key stays. No sheet had been received under version 1, so nothing is lost here.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('survey', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='surveyresponse',
            name='contact_hash',
        ),
    ]
