# coding: utf-8
from datetime import timedelta
from typing import Union

from django.conf import settings
from django.contrib.auth.models import User
from django.core.signing import Signer
from django.db import models
from django.db.models import Q, F, Func
from django.utils import timezone


class OneTimeAuthToken(models.Model):

    HEADER = 'X-KOBOCAT-OTA-TOKEN'

    user = models.ForeignKey(
        User, related_name='authenticated_requests', on_delete=models.CASCADE
    )
    token = models.CharField(max_length=50)
    expiration_time = models.DateTimeField()
    method = models.CharField(max_length=6)

    class Meta:
        unique_together = ('user', 'token', 'method')

    @classmethod
    def grant_access(
        cls,
        request: 'rest_framework.request.Request',
        use_referrer: bool = True,
    ):
        token = cls.is_signed_request(request, use_referrer)
        if token is None:
            # No token is detected, the authentication should be
            # delegated to other mechanisms present in permission classes
            return None

        user = request.user
        try:
            auth_token = cls.objects.get(
                user=user, token=token, method=request.method
            )
        except OneTimeAuthToken.DoesNotExist:
            return False

        granted = timezone.now() <= auth_token.expiration_time

        # void token
        auth_token.delete()

        # clean-up expired or already used tokens
        OneTimeAuthToken.objects.filter(
            expiration_time__lt=timezone.now(),
            user=user,
        ).delete()

        return granted

    @classmethod
    def is_signed_request(
        cls,
        request: 'rest_framework.request.Request',
        use_referrer: bool = False,
    ) -> Union[str, None]:
        """
        Search for a OneTimeAuthToken in the request headers.
        If there is a match, it is returned. Otherwise, it returns `None`.

        If `use_referrer` is `True`, the comparison is also made on the
        HTTP referrer.
        """
        try:
            token = request.headers[cls.HEADER]
        except KeyError:
            if not use_referrer:
                return None
        else:
            return token

        try:
            referrer = request.META['HTTP_REFERER']
        except KeyError:
            return None
        else:
            # There is no reason that the referrer could be something else
            # than Enketo Express edit URL.
            edit_url = f'{settings.ENKETO_URL}/edit'
            if not referrer.startswith(edit_url):
                return None

            parts = Signer().sign(referrer).split(':')
            return parts[-1]
