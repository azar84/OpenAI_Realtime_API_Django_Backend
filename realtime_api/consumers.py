import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from .models import AgentConfiguration, CallSession
from .session_manager import session_manager
import logging

logger = logging.getLogger(__name__)

class RealtimeConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.realtime_session = None
        self.call_session = None
        
    async def connect(self):
        """Accept WebSocket connection and initialize session"""
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        await self.accept()
        
        logger.info(f"WebSocket connected for session: {self.session_id}")
        
        # Create or get call session in database
        await self.initialize_database_session()
        
        # Get the realtime session from session manager
        self.realtime_session = session_manager.get_session(self.session_id)
        
        # Set this consumer as the Twilio connection
        self.realtime_session.set_twilio_connection(self)
        
        logger.info("Session initialized, ready for Twilio messages")
        
    async def disconnect(self, close_code):
        """Clean up connections when client disconnects"""
        logger.info(f"WebSocket disconnected for session: {self.session_id}")
        
        # Update database session status
        if self.call_session:
            await self.update_session_status('ended')
            
        # Cleanup session manager
        if self.session_id:
            await session_manager.cleanup_session(self.session_id)
            
    @database_sync_to_async
    def get_or_create_session(self):
        """Get or create a call session"""
        call_session, created = CallSession.objects.get_or_create(
            session_id=self.session_id,
            defaults={'status': 'started'}
        )
        return call_session
    
    @database_sync_to_async
    def update_session_status(self, status):
        """Update call session status"""
        if self.call_session:
            self.call_session.status = status
            self.call_session.save(update_fields=['status'])
            
    async def initialize_database_session(self):
        """Initialize the database call session"""
        self.call_session = await self.get_or_create_session()
        await self.update_session_status('connected')
            
    async def receive(self, text_data):
        """Handle incoming messages from client (Twilio)"""
        try:
            data = json.loads(text_data)
            
            # Route messages to session manager
            if self.realtime_session:
                await self.realtime_session.handle_twilio_message(text_data)
            else:
                logger.error("No realtime session available")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
        
    async def send(self, text_data=None, bytes_data=None):
        """Override send to work with session manager"""
        if text_data:
            await super().send(text_data=text_data)
        elif bytes_data:
            await super().send(bytes_data=bytes_data)
