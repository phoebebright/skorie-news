from django import forms
from django.forms import Form
from django_countries.fields import CountryField

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _



class ProfileForm(Form):
    country = CountryField().formfield()
    city = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'update'}),
        max_length=50,  label=_("Nearest City or Town"))

    where_did_you_hear = forms.CharField(max_length=60,  label=_("Where did you hear about us? (Please name any organisation, magazines or websites)"), help_text=_("It really helps us if you tell us the full names of how you found us!"))
    mobile =  forms.CharField(max_length=20,  label=_("Mobile Number"),
                              help_text=_("Optional - Only for Events you are participating in or for support"),
    required=False)
    whatsapp = forms.BooleanField(required=False, label="Whatsapp - Only for Events you are participating in or for support")

class SubscribeForm(Form):

    country = CountryField().formfield(required=True)
    city = forms.CharField(max_length=50,  label=_("Nearest City or Town"), required=True)
    where_did_you_hear = forms.CharField(max_length=60, label=_(
        "Where did you hear about us? (Please name any organisation, magazines or websites)"), help_text=_(
        "It really helps us if you tell us the full names of how you found us!"))

    subscribe = forms.BooleanField(initial=False, required=False)
