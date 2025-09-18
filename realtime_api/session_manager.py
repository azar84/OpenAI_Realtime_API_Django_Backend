"""
Session management utilities for OpenAI Realtime API
Similar to the JavaScript sessionManager but adapted for Django/Python
"""

import json
import asyncio
import websockets
import base64
from typing import Optional, Dict, Any
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class RealtimeSession:
    """Manages a single realtime session with OpenAI and Twilio"""
    
    def __init__(self, session_id: str, agent_config=None):
        self.session_id = session_id
        self.twilio_conn = None  # WebSocket connection from Twilio
        self.model_conn = None   # WebSocket connection to OpenAI
        self.stream_sid: Optional[str] = None
        self.saved_config: Optional[Dict[str, Any]] = None
        self.last_assistant_item: Optional[str] = None
        self.response_start_timestamp: Optional[float] = None
        self.latest_media_timestamp: Optional[float] = None
        self.agent_config = agent_config
        
        # DEBUG: Log what agent config we received
        if agent_config:
            try:
                logger.info(f"🤖 Session {session_id} initialized with agent: {agent_config.name} (ID: {agent_config.id})")
                # Set the saved config from agent configuration
                self.saved_config = agent_config.to_openai_config()
                logger.info(f"🎯 Agent config loaded: voice={agent_config.voice}, instructions={agent_config.instructions[:50]}...")
            except Exception as e:
                logger.warning(f"🤖 Error loading agent config: {e}")
                logger.info(f"🤖 Session {session_id} initialized with agent config")
        else:
            logger.warning(f"🤖 Session {session_id} initialized with NO agent config")
            
        self.openai_api_key = self._get_openai_api_key()
    
    def _get_openai_api_key(self):
        """Get OpenAI API key from agent's user profile or fallback to system default"""
        try:
            if self.agent_config:
                # Simple path: Agent → User → Profile → API Key
                api_key = self.agent_config.get_user_api_key()
                logger.info(f"🔑 Retrieved API key for agent {self.agent_config.name}: {api_key[:20]}...")
                return api_key
            else:
                logger.warning("🔑 No agent_config available, using system default")
        except Exception as e:
            logger.warning(f"🔑 Error getting user API key, using system default: {e}")
        
        logger.warning(f"🔑 Using system API key: {settings.OPENAI_API_KEY[:20]}...")
        return settings.OPENAI_API_KEY
    
    def set_agent_config(self, agent_config):
        """Set the agent configuration and update API key"""
        self.agent_config = agent_config
        self.openai_api_key = self._get_openai_api_key()
        if agent_config:
            self.saved_config = agent_config.to_openai_config()
        
    def set_twilio_connection(self, consumer):
        """Set the Django Channels consumer as Twilio connection"""
        self.twilio_conn = consumer
        logger.info(f"Twilio connection established for session {self.session_id}")
    
    async def handle_twilio_message(self, data):
        """Handle messages from Twilio WebSocket"""
        try:
            msg = json.loads(data)
            event_type = msg.get('event')
            
            if event_type == 'start':
                await self.handle_stream_start(msg)
            elif event_type == 'media':
                await self.handle_media(msg)
            elif event_type == 'stop':
                await self.handle_stream_stop(msg)
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from Twilio: {data}")
        except Exception as e:
            logger.error(f"Error handling Twilio message: {e}")
    
    async def handle_stream_start(self, msg):
        """Handle Twilio stream start event"""
        start_data = msg.get('start', {})
        self.stream_sid = start_data.get('streamSid')
        self.latest_media_timestamp = 0
        self.last_assistant_item = None
        self.response_start_timestamp = None
        
        logger.info(f"Stream started: {self.stream_sid}")
        await self.try_connect_model()
    
    async def handle_media(self, msg):
        """Handle Twilio media (audio) data"""
        media_data = msg.get('media', {})
        payload = media_data.get('payload', '')
        timestamp = media_data.get('timestamp', 0)
        
        self.latest_media_timestamp = float(timestamp)
        
        if self.is_model_connected():
            # Send audio to OpenAI
            audio_message = {
                "type": "input_audio_buffer.append",
                "audio": payload  # Twilio sends base64 encoded audio
            }
            await self.send_to_model(audio_message)
    
    async def handle_stream_stop(self, msg):
        """Handle Twilio stream stop event"""
        logger.info(f"Stream stopped: {self.stream_sid}")
        await self.cleanup_all_connections()
    
    async def try_connect_model(self):
        """Connect to OpenAI Realtime API"""
        if not self.twilio_conn or not self.stream_sid or not self.openai_api_key:
            logger.warning("Cannot connect to model: missing requirements")
            return
            
        if self.is_model_connected():
            logger.info("Model already connected")
            return
        
        try:
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            model_url = f"{settings.OPENAI_REALTIME_URL}?model={settings.OPENAI_REALTIME_MODEL}"
            
            # DEBUG: Log connection details
            logger.info(f"Connecting to OpenAI with key: {self.openai_api_key[:20]}...")
            logger.info(f"URL: {model_url}")
            logger.info(f"Headers: {headers}")
            
            import ssl
            # Create SSL context for production
            ssl_context = ssl.create_default_context()
            
            self.model_conn = await websockets.connect(
                model_url,
                extra_headers=headers,
                ssl=ssl_context
            )
            
            logger.info(f"Connected to OpenAI for session {self.session_id}")
            
            # Send initial configuration
            await self.configure_session()
            
            # Start listening for model responses
            asyncio.create_task(self.listen_to_model())
            
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {e}")
            self.model_conn = None
    
    async def configure_session(self):
        """Configure the OpenAI session"""
        try:
            # Use agent configuration if available, otherwise use defaults
            if self.agent_config and self.saved_config:
                config = self.saved_config
                # Override audio formats for Twilio compatibility
                config["input_audio_format"] = "g711_ulaw"  # Twilio sends this format
                config["output_audio_format"] = "g711_ulaw" # Twilio expects this format
                logger.info(f"🎯 Using agent config with Twilio audio formats")
            else:
                config = {
                    "modalities": ["text", "audio"],
                    "turn_detection": {"type": "server_vad"},
                    "voice": "alloy",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "input_audio_format": "g711_ulaw",  # Twilio format
                    "output_audio_format": "g711_ulaw", # Twilio format
                }
                logger.info(f"🎯 Using default config with Twilio audio formats")
            
            session_config = {
                "type": "session.update",
                "session": config
            }
            
            await self.send_to_model(session_config)
            logger.info(f"🎯 OpenAI session configured with: voice={config.get('voice', 'default')}, instructions={config.get('instructions', 'default')[:50]}...")
            logger.info("OpenAI session configured successfully")
            
        except Exception as e:
            logger.error(f"Error configuring OpenAI session: {e}")
            raise
    
    async def listen_to_model(self):
        """Listen for responses from OpenAI"""
        try:
            async for message in self.model_conn:
                await self.handle_model_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"OpenAI connection closed: {e}")
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"OpenAI connection closed with error: {e}")
        except Exception as e:
            logger.error(f"Error listening to model: {e}")
        finally:
            await self.close_model()
    
    async def handle_model_message(self, data):
        """Handle messages from OpenAI"""
        try:
            event = json.loads(data)
            event_type = event.get('type')
            
            if event_type == 'input_audio_buffer.speech_started':
                await self.handle_speech_interruption()
            elif event_type == 'response.audio.delta':
                await self.handle_audio_response(event)
            elif event_type == 'response.output_item.done':
                await self.handle_output_item_done(event)
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from OpenAI: {data}")
        except Exception as e:
            logger.error(f"Error handling model message: {e}")
    
    async def handle_audio_response(self, event):
        """Handle audio response from OpenAI"""
        if not self.twilio_conn or not self.stream_sid:
            return
            
        delta = event.get('delta', '')
        item_id = event.get('item_id')
        
        if self.response_start_timestamp is None:
            self.response_start_timestamp = self.latest_media_timestamp or 0
            
        if item_id:
            self.last_assistant_item = item_id
        
        # Send audio to Twilio
        media_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": delta}
        }
        
        await self.send_to_twilio(media_message)
        
        # Send mark for synchronization
        mark_message = {
            "event": "mark",
            "streamSid": self.stream_sid
        }
        
        await self.send_to_twilio(mark_message)
    
    async def handle_output_item_done(self, event):
        """Handle completed output items (including function calls)"""
        item = event.get('item', {})
        
        if item.get('type') == 'function_call':
            await self.handle_function_call(item)
    
    async def handle_function_call(self, item):
        """Handle function calls from OpenAI"""
        function_name = item.get('name', '')
        arguments = item.get('arguments', '{}')
        call_id = item.get('call_id')
        
        logger.info(f"Function call: {function_name}")
        
        try:
            # Parse arguments
            args = json.loads(arguments)
            
            # Handle different functions
            if function_name == 'get_weather':
                result = await self.get_weather(args.get('location', ''))
            elif function_name == 'get_time':
                result = await self.get_current_time()
            else:
                result = {"error": f"Unknown function: {function_name}"}
            
            # Send result back to OpenAI
            function_output = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result)
                }
            }
            
            await self.send_to_model(function_output)
            await self.send_to_model({"type": "response.create"})
            
        except Exception as e:
            logger.error(f"Error handling function call: {e}")
    
    async def handle_speech_interruption(self):
        """Handle user speech interruption"""
        if not self.last_assistant_item or self.response_start_timestamp is None:
            return
        
        elapsed_ms = (self.latest_media_timestamp or 0) - (self.response_start_timestamp or 0)
        audio_end_ms = max(elapsed_ms, 0)
        
        # Truncate the current response
        if self.is_model_connected():
            truncate_message = {
                "type": "conversation.item.truncate",
                "item_id": self.last_assistant_item,
                "content_index": 0,
                "audio_end_ms": audio_end_ms
            }
            await self.send_to_model(truncate_message)
        
        # Clear Twilio's audio buffer
        if self.twilio_conn and self.stream_sid:
            clear_message = {
                "event": "clear",
                "streamSid": self.stream_sid
            }
            await self.send_to_twilio(clear_message)
        
        self.last_assistant_item = None
        self.response_start_timestamp = None
    
    async def send_to_model(self, message):
        """Send message to OpenAI"""
        if self.is_model_connected():
            await self.model_conn.send(json.dumps(message))
    
    async def send_to_twilio(self, message):
        """Send message to Twilio"""
        if self.twilio_conn:
            await self.twilio_conn.send(text_data=json.dumps(message))
    
    def is_model_connected(self):
        """Check if model connection is open"""
        return (self.model_conn and 
                self.model_conn.open and 
                not self.model_conn.closed)
    
    async def cleanup_connection(self, conn):
        """Clean up a WebSocket connection"""
        if not conn:
            return
            
        try:
            # Handle different connection types
            if hasattr(conn, 'close') and hasattr(conn, 'closed'):
                # This is a websockets connection
                if not conn.closed:
                    await conn.close()
            elif hasattr(conn, 'send'):
                # This is a Django Channels consumer - no need to close
                # The consumer will be cleaned up by Django Channels
                pass
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
    
    async def close_model(self):
        """Close model connection"""
        await self.cleanup_connection(self.model_conn)
        self.model_conn = None
    
    async def cleanup_all_connections(self):
        """Clean up all connections"""
        await self.cleanup_connection(self.twilio_conn)
        await self.cleanup_connection(self.model_conn)
        
        self.twilio_conn = None
        self.model_conn = None
        self.stream_sid = None
        self.last_assistant_item = None
        self.response_start_timestamp = None
        self.latest_media_timestamp = None
        self.saved_config = None
    
    # Function implementations
    async def get_weather(self, location):
        """Mock weather function"""
        return {
            "location": location,
            "temperature": "72°F",
            "condition": "Sunny",
            "humidity": "45%"
        }
    
    async def get_current_time(self):
        """Get current time"""
        from datetime import datetime
        now = datetime.now()
        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": "UTC"
        }


# Global session manager
class SessionManager:
    """Manages multiple realtime sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, RealtimeSession] = {}
    
    def get_session(self, session_id: str, agent_config=None) -> RealtimeSession:
        """Get or create a session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = RealtimeSession(session_id, agent_config)
        elif agent_config and not self.sessions[session_id].agent_config:
            # Set agent config if not already set
            self.sessions[session_id].set_agent_config(agent_config)
        return self.sessions[session_id]
    
    def remove_session(self, session_id: str):
        """Remove a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    async def cleanup_session(self, session_id: str):
        """Clean up a session"""
        if session_id in self.sessions:
            await self.sessions[session_id].cleanup_all_connections()
            self.remove_session(session_id)


# Global session manager instance
session_manager = SessionManager()
