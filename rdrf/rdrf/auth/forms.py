import logging

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.db.models import Q
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# Same as django.contrib.auth.forms.PasswordResetForm but also allows password reset functionality
# for inactive users if the Unlock Account feature is enabled and the user isn't explicitly prevented
# to unlock their account
class RDRFPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        users_query = Q(email__iexact=email, is_active=True)

        if not getattr(settings, "ACCOUNT_SELF_UNLOCK_ENABLED", False):
            users_query &= Q(is_locked=False)

        users = get_user_model()._default_manager.filter(users_query)
        return (u for u in users if u.has_usable_password())


# Same as django.contrib.auth.forms.SetPasswordForm but also reactivates the user if it is inactive
# end ACCOUNT_SELF_UNLOCK_ENABLED is True
class RDRFSetPasswordForm(SetPasswordForm):
    def save(self, commit=True):
        super().save(commit=False)

        if not self.user.is_active:
            logger.warning(
                'User "%s" reset their password but their account is disabled ',
                self.user,
            )
        elif self.user.is_locked:
            if getattr(settings, "ACCOUNT_SELF_UNLOCK_ENABLED", False):
                self.user.is_locked = False
            else:
                logger.warning(
                    'User "%s" resetted their password but their account is locked and self unlock is disabled.',
                )

        if commit:
            self.user.save()

        return self.user


class UserVerificationForm(forms.Form):
    first_name = forms.CharField(label=_("First Name"), max_length=254)
    last_name = forms.CharField(label=_("Surname"), max_length=254)
    date_of_birth = forms.DateField(
        label=_("Date of Birth"), input_formats=["%Y-%m-%d"]
    )

    def __init__(self, user_data, *args, **kwargs):
        self.user_data = user_data
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()

        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")
        date_of_birth = cleaned_data.get("date_of_birth")

        if first_name and last_name and date_of_birth:
            if not self.matches_data(first_name, last_name, date_of_birth):
                raise ValidationError(_("The data you've entered is incorrect"))

    def matches_data(self, first_name, last_name, date_of_birth):
        def laid_back_eql(s1, s2):
            return s1.strip().lower() == s2.strip().lower()

        return (
            laid_back_eql(first_name, self.user_data["first_name"])
            and laid_back_eql(last_name, self.user_data["last_name"])
            and (date_of_birth == self.user_data["date_of_birth"])
        )


class ReactivateAccountForm(SetPasswordForm):
    def __init__(
        self, request, user, is_password_change_required, *args, **kwargs
    ):
        self.request = request
        self.is_password_change_required = is_password_change_required
        super().__init__(user, *args, **kwargs)

    def clean(self):
        if self.is_password_change_required and not self.cleaned_data.get(
            "new_password1"
        ):
            raise ValidationError(
                _("You are required to change your password.")
            )

    def is_valid(self):
        is_valid = super().is_valid()
        if (
            not self.is_password_change_required
            and not self.request.POST.get("new_password1")
            and not self.request.POST.get("new_password2")
        ):
            return True
        return is_valid

    def save(self, commit=True):
        if self.cleaned_data.get("new_password1"):
            super().save(commit=False)
        self.user.is_active = True
        if commit:
            self.user.save()
        return self.user


class LoginAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": _("Please enter a correct username and password."),
        "inactive": _("This account is inactive."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Email Address")
