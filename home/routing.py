from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/consultation/<str:room_name>/', consumers.SignalingConsumer.as_asgi()),
]
