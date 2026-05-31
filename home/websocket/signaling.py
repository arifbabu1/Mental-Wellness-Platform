"""
WebSocket signaling server for video consultations
"""
import json
import asyncio
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from home.models import Consultation

logger = logging.getLogger(__name__)

class SignalingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"consultation_{self.room_name}"
        self.user = self.scope.get('user')

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        if not await self.user_can_access_room(self.user.id, self.room_name):
            await self.close(code=4403)
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accept connection
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.user.id,
                'username': self.user.get_full_name() or self.user.username,
                'role': getattr(self.user, 'role', ''),
            }
        )
        
        logger.info(f"User {self.user.id} joined consultation room {self.room_name}")
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Notify other participants
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.user.id,
                'username': self.user.get_full_name() or self.user.username,
                'role': getattr(self.user, 'role', ''),
            }
        )
        
        logger.info(f"User {self.user.id} left consultation room {self.room_name}")

    @database_sync_to_async
    def user_can_access_room(self, user_id, room_name):
        try:
            consultation = Consultation.objects.select_related(
                'appointment__patient',
                'appointment__doctor__user',
            ).get(room_name=room_name)
        except Consultation.DoesNotExist:
            return False

        appointment = consultation.appointment
        return appointment.patient_id == user_id or appointment.doctor.user_id == user_id
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'offer':
                await self.handle_offer(data)
            elif message_type == 'answer':
                await self.handle_answer(data)
            elif message_type == 'ice_candidate':
                await self.handle_ice_candidate(data)
            elif message_type == 'chat_message':
                await self.handle_chat_message(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def handle_offer(self, data):
        # Forward offer to other participants
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'offer',
                'offer': data['offer'],
                'sender_id': self.user.id,
                'sender_name': self.user.get_full_name() or self.user.username
            }
        )
    
    async def handle_answer(self, data):
        # Forward answer to other participants
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'answer',
                'answer': data['answer'],
                'sender_id': self.user.id,
                'sender_name': self.user.get_full_name() or self.user.username
            }
        )
    
    async def handle_ice_candidate(self, data):
        # Forward ICE candidate to other participants
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'ice_candidate',
                'candidate': data['candidate'],
                'sender_id': self.user.id,
                'sender_name': self.user.get_full_name() or self.user.username
            }
        )
    
    async def handle_chat_message(self, data):
        # Save chat message to database and broadcast
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': data['message'],
                'sender_id': self.user.id,
                'sender_name': self.user.get_full_name() or self.user.username,
                'timestamp': datetime.now().isoformat()
            }
        )

    async def _send_event(self, event):
        if event.get('sender_id') == self.user.id and event.get('type') in {'offer', 'answer', 'ice_candidate'}:
            return
        await self.send(text_data=json.dumps(event))

    async def user_joined(self, event):
        await self._send_event({**event, 'type': 'user_joined'})

    async def user_left(self, event):
        await self._send_event({**event, 'type': 'user_left'})

    async def offer(self, event):
        await self._send_event({**event, 'type': 'offer'})

    async def answer(self, event):
        await self._send_event({**event, 'type': 'answer'})

    async def ice_candidate(self, event):
        await self._send_event({**event, 'type': 'ice_candidate'})

    async def chat_message(self, event):
        await self._send_event({**event, 'type': 'chat_message'})
