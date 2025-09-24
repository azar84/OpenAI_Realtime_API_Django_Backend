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
        
        # Parse routing parameters from query string
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        query_params = {}
        if query_string:
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value
        
        # Get agent configuration based on routing parameters
        agent_config = await self.get_routed_agent_config(query_params)
        
        # Create or get call session in database
        await self.initialize_database_session(agent_config)
        
        # Get the realtime session from session manager
        self.realtime_session = session_manager.get_session(self.session_id, agent_config)
        
        # Initialize conversation tracking
        if self.call_session:
            await self.realtime_session.initialize_conversation_tracking(self.call_session)
        
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
        """Update call session status and calculate duration if ending"""
        if self.call_session:
            self.call_session.status = status
            
            # Calculate duration if call is ending
            if status == 'ended' and self.call_session.call_start_time:
                from django.utils import timezone
                end_time = timezone.now()
                duration = (end_time - self.call_session.call_start_time).total_seconds()
                self.call_session.call_end_time = end_time
                self.call_session.call_duration_seconds = int(duration)
                self.call_session.save(update_fields=['status', 'call_end_time', 'call_duration_seconds'])
            else:
                self.call_session.save(update_fields=['status'])
    
    @database_sync_to_async
    def get_routed_agent_config(self, query_params):
        """Get agent configuration based on routing parameters"""
        try:
            # First try to get agent by ID from routing
            agent_id = query_params.get('agent_id')
            if agent_id:
                try:
                    agent = AgentConfiguration.objects.get(id=int(agent_id), is_active=True)
                    logger.info(f"Using routed agent: {agent.name} (ID: {agent.id})")
                    return agent
                except (AgentConfiguration.DoesNotExist, ValueError):
                    logger.warning(f"Routed agent ID {agent_id} not found or inactive")
            
            # Try to get agent by phone number
            phone_id = query_params.get('phone_id')
            if phone_id:
                try:
                    from .models import PhoneNumber
                    phone_number = PhoneNumber.objects.get(id=int(phone_id), is_active=True)
                    agent = phone_number.get_agent_config()
                    if agent:
                        logger.info(f"Using phone-routed agent: {agent.name} for {phone_number.phone_number}")
                        return agent
                except (PhoneNumber.DoesNotExist, ValueError):
                    logger.warning(f"Phone number ID {phone_id} not found or inactive")
            
            # NEW: Try to lookup by session's call data
            try:
                call_session = CallSession.objects.get(session_id=self.session_id)
                if call_session.called_number:
                    from .models import PhoneNumber
                    phone_number = PhoneNumber.objects.select_related('user', 'agent_config__user').get(
                        phone_number=call_session.called_number,
                        is_active=True
                    )
                    agent = phone_number.get_agent_config()
                    if agent:
                        # Test the API key right here
                        test_api_key = agent.get_user_api_key()
                        logger.info(f"🔑 CONSUMER: Agent {agent.name} API key: {test_api_key[:20]}...")
                        logger.info(f"Using session-routed agent: {agent.name} for {phone_number.phone_number}")
                        return agent
            except Exception as e:
                logger.debug(f"Could not route by session data: {e}")
            
            # Fallback to first active agent
            agent = AgentConfiguration.objects.filter(is_active=True).first()
            if agent:
                logger.info(f"Using fallback agent: {agent.name}")
            else:
                logger.warning("No active agents available")
            return agent
            
        except Exception as e:
            logger.error(f"Error getting routed agent config: {e}")
            return None
            
    async def initialize_database_session(self, agent_config=None):
        """Initialize the database call session"""
        self.call_session = await self.get_or_create_session()
        if agent_config:
            # Update the call session with the correct agent
            await self.update_call_session_agent(agent_config)
        await self.update_session_status('connected')
    
    @database_sync_to_async
    def update_call_session_agent(self, agent_config):
        """Update the call session with the correct agent"""
        if self.call_session:
            self.call_session.agent_config = agent_config
            self.call_session.save(update_fields=['agent_config'])
    
    @database_sync_to_async
    def get_call_session_agent_id(self):
        """Get the agent ID from call session safely"""
        if self.call_session and self.call_session.agent_config:
            return self.call_session.agent_config.id
        return None
            
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
