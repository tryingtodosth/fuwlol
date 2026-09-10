"""Register / login / logout / me. Plain username + password, DRF tokens.
The login field accepts a username or an email; the throttle keys on IP."""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_staff', 'date_joined']
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r'^[a-zA-Z0-9_.-]{3,30}$', error_messages={
        'invalid': 'Nazwa: 3–30 znaków, litery, cyfry, . _ -'})
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate_username(self, v):
        if User.objects.filter(username__iexact=v).exists():
            raise serializers.ValidationError('Ta nazwa jest już zajęta.')
        return v

    def validate_email(self, v):
        if v and User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError('Ten e-mail jest już użyty.')
        return v

    def validate_password(self, v):
        try:
            validate_password(v)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return v

    def create(self, data):
        return User.objects.create_user(data['username'], data.get('email', ''), data['password'])


def _payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': UserSerializer(user).data}


class RegisterView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(_payload(s.save()), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        ident = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        if '@' in ident:
            u = User.objects.filter(email__iexact=ident).first()
            ident = u.username if u else ident
        user = authenticate(request, username=ident, password=password)
        if user is None:
            return Response({'detail': 'Zła nazwa lub hasło.'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
