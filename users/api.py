from django.contrib.auth import get_user_model
from django_users.api import CheckEmailBase
from django_users.serializers import UserSerializer, EmailExistsSerializer, RoleSerializer
from rest_framework import viewsets, status
from rest_framework.response import Response

from skorie.common.drf_utils import SignedTokenAuthentication
from users.models import Role

User = get_user_model()

class CheckEmail(CheckEmailBase):

    def get_serializer_class(self):
        detailed = self.request.query_params.get('detail', False)
        if detailed:
            return UserSerializer
        else:
            return EmailExistsSerializer



class MyInternalRoles(viewsets.ReadOnlyModelViewSet):
    '''get my sheets where request.user is competitor'''
    permission_classes = ()
    authentication_classes = (SignedTokenAuthentication,)

    serializer_class = RoleSerializer


    def get_queryset(self):

        me = self.request.user
        return Role.objects.active().filter(user=me)



class InternalRoleViewSet(viewsets.ModelViewSet):
    '''Viewset for roles for other skorie systems only
    not fully implemented

    '''

    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = ()
    authentication_classes = (SignedTokenAuthentication,)
    http_method_names = ['get', 'post', ]

    def post(self, request):
        '''
        {'username': 'phoebebright310+13oct@gmail.com', 'email': 'phoebebright310+13oct@gmail.com', 'first_name': 'Phoebe', 'last_name...name': 'Phoebe 13Oct', 'sortable_name': '13Oct Phoebe', 'name': 'Phoebe 13Oct', 'preferred_channel': 'email', 'role_type': 'K'}
        :param request:
        :return:
        '''
        data = request.data

        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            user = User.objects.create_user(email=data['email'], username=data['email'], first_name=data['first_name'], last_name=data['last_name'])
            # add rest of fields
            user.save()
            # probably want to notify user they are registered

        # no double other things to do here
        role = Role.objects.get_or_create(user=user, role_type=data['role_type'])

        # return serialized - we want to start having the same refs across systsmes

        return Response(status=status.HTTP_201_CREATED)
