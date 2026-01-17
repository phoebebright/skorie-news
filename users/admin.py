from django.contrib.auth import admin
from django.contrib.auth.forms import BaseUserCreationForm
from django.apps import apps
from django.contrib import admin
from django_users.admin import (
    UserContactAdminBase,
    CustomUserAdminBase,
    RoleAdminBase,
    CommsChannelAdminBase,
    VerificationCodeAdminBase,

)

from users.models import CustomUser, UserContact, Person, Role, CommsChannel, VerificationCode, PersonOrganisation, Organisation


class PersonRoleInline(admin.TabularInline):
    model = Role
    extra = 0


class PersonOrgInline(admin.TabularInline):
    model = PersonOrganisation
    extra = 0

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):

    class Meta:
        model = Person
    list_display = ('ref','formal_name','friendly_name','user',)
    search_fields = ('formal_name','friendly_name','user__email','ref')
    ordering = ('sortable_name', 'formal_name')
    inlines = [PersonRoleInline,PersonOrgInline]

@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):

    class Meta:
        model = Organisation
    list_display = ('code','name','created','updated',)


class UserCreationForm(BaseUserCreationForm):
    """Project-specific user creation form."""
    class Meta(BaseUserCreationForm.Meta):
        model = CustomUser  # Set the project-specific model

@admin.register(CustomUser)
class CustomUserAdmin(CustomUserAdminBase):
    add_form = UserCreationForm  # Use the extended form for user creation
    search_fields = ["email", "first_name", "last_name"]
    class Meta(CustomUserAdminBase.Meta):
        model = CustomUser  # Set the project-specific model

@admin.register(UserContact)
class UserContactAdmin(UserContactAdminBase):
    """Project-specific customization for UserContact admin."""
    pass



@admin.register(Role)
class RoleAdmin(RoleAdminBase):
    """Project-specific customization for Role admin."""
    pass

@admin.register(CommsChannel)
class CommsChannelAdmin(CommsChannelAdminBase):
    """Project-specific customization for CommsChannel admin."""
    pass

@admin.register(VerificationCode)
class VerificationCodeAdmin(VerificationCodeAdminBase):
    """Project-specific customization for VerificationCode admin."""
    pass
