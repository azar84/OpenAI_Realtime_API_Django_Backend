"""
Session Management for OpenAI Realtime API
=========================================

This module provides comprehensive session management for OpenAI Realtime API
integrations with Twilio, including MCP support, tool handling, and conversation tracking.

Architecture:
- RealtimeSession: Core session management and OpenAI integration
- SessionManager: Global session lifecycle management
- ToolHandler: Dedicated tool execution and response handling
- MCPIntegration: MCP server connection and configuration
- AudioHandler: Twilio audio stream management
"""

import json
import asyncio
import websockets
import ssl
from typing import Optional, Dict, Any, List
from datetime import datetime
from django.conf import settings
import logging

from .conversation_tracker import conversation_tracker

logger = logging.getLogger(__name__)


class MCPIntegration:
    """Handles MCP server integration and configuration"""
    
    def __init__(self, agent_config):
        self.agent_config = agent_config
        self.is_enabled = agent_config and agent_config.has_mcp_integration()
    
    def get_mcp_tool_config(self) -> Optional[Dict[str, Any]]:
        """Get MCP tool configuration for session setup"""
        if not self.is_enabled:
            return None
            
        return {
            "type": "mcp",
            "server_label": f"mcp-{self.agent_config.mcp_tenant_id}",
            "server_url": settings.MCP_SERVER_URL,
            "authorization": self.agent_config.mcp_auth_token,
            "require_approval": "never"
        }
    
    def log_connection_attempt(self):
        """Log MCP connection details"""
        if not self.is_enabled:
            logger.info("🔗 MCP TOOL: No MCP integration configured for this agent")
            return
            
        logger.info(f"🔗 MCP CONNECTION: Starting MCP-enabled connection for agent {self.agent_config.name}")
        logger.info(f"🔗 MCP CONNECTION: Agent MCP tenant ID: {self.agent_config.mcp_tenant_id}")
        logger.info(f"🔗 MCP CONNECTION: MCP server URL: {self.agent_config.get_mcp_config().get('server_url', 'Not configured')}")
        logger.info(f"🔗 MCP CONNECTION: MCP auth token: {self.agent_config.mcp_auth_token[:20] if self.agent_config.mcp_auth_token else 'Not configured'}...")


class ToolHandler:
    """Handles tool execution and response management"""
    
    def __init__(self, session):
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.ToolHandler")
    
    async def execute_tool_call(self, item: Dict[str, Any]) -> None:
        """Execute a tool call with proper response handling"""
        from .tools import execute_tool
        
        function_name = item.get('name', '')
        arguments = item.get('arguments', '{}')
        call_id = item.get('call_id')
        
        self.logger.info(f"🔧 TOOL CALL: Agent is calling function: {function_name}")
        self.logger.info(f"🔧 TOOL CALL: Call ID: {call_id}")
        self.logger.info(f"🔧 TOOL CALL: Arguments: {arguments}")
        
        # Check if this is an MCP tool call
        if self._is_mcp_tool(function_name):
            self.logger.info(f"🔗 MCP TOOL CALL: MCP function detected: {function_name}")
            self.logger.info(f"🔗 MCP TOOL CALL: This will be handled by MCP server")
        
        try:
            # Send holding message to avoid dead air
            await self._send_holding_message()
            
            # Parse and execute tool
            args = json.loads(arguments)
            self.logger.info(f"🔧 TOOL CALL: Parsed arguments: {args}")
            
            self.logger.info(f"🔧 TOOL CALL: Executing tool {function_name}...")
            result = await execute_tool(function_name, args)
            self.logger.info(f"🔧 TOOL CALL: Tool execution completed")
            self.logger.info(f"🔧 TOOL CALL: Result: {json.dumps(result, indent=2) if isinstance(result, dict) else str(result)}")
            
            # Send tool result and trigger response
            await self._send_tool_result_and_trigger_response(call_id, result)
            
        except Exception as e:
            self.logger.error(f"🔧 TOOL CALL: Error handling function call {function_name}: {e}")
            self.logger.error(f"🔧 TOOL CALL: Call ID: {call_id}, Arguments: {arguments}")
    
    def _is_mcp_tool(self, function_name: str) -> bool:
        """Check if function is an MCP tool"""
        return function_name.startswith('mcp_') or 'mcp' in function_name.lower()
    
    async def _send_holding_message(self) -> None:
        """Send holding message to avoid dead air during tool execution (legacy method)"""
        # Use the improved approach - single response.create without conversation item
        await self.session.send_to_model({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "One moment while I check that for you..."
            }
        })
        self.logger.info(f"🔧 TOOL CALL: Sent holding response to avoid dead air")
    
    async def _send_tool_result_and_trigger_response(self, call_id: str, result: Any) -> None:
        """Send tool result and trigger audio response"""
        # Step 1: Attach tool result to conversation
        function_output = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result)
            }
        }
        
        await self.session.send_to_model(function_output)
        self.logger.info(f"🔧 TOOL CALL: Step 1 - Tool result attached to conversation")
        
        # Step 2: Trigger generation with audio
        response_create = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "Briefly explain the tool result to the caller and offer a follow-up question or next step. Do not wait for the user to ask what happened."
            }
        }
        
        await self.session.send_to_model(response_create)
        self.logger.info(f"🔧 TOOL CALL: Step 2 - Response generation triggered with audio")
        self.logger.info(f"🔧 TOOL CALL: Agent will now speak the tool result to the caller")


class AudioHandler:
    """Handles Twilio audio stream management"""
    
    def __init__(self, session):
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.AudioHandler")
    
    async def handle_audio_response(self, event: Dict[str, Any]) -> None:
        """Handle audio response from OpenAI and send to Twilio"""
        if not self.session.twilio_conn or not self.session.stream_sid:
            return
            
        delta = event.get('delta', '')
        item_id = event.get('item_id')
        
        if self.session.response_start_timestamp is None:
            self.session.response_start_timestamp = self.session.latest_media_timestamp or 0
            
        if item_id:
            self.session.last_assistant_item = item_id
        
        # Send audio to Twilio
        media_message = {
            "event": "media",
            "streamSid": self.session.stream_sid,
            "media": {"payload": delta}
        }
        
        await self.session.send_to_twilio(media_message)
        
        # Send mark for synchronization
        mark_message = {
            "event": "mark",
            "streamSid": self.session.stream_sid
        }
        
        await self.session.send_to_twilio(mark_message)
    
    async def handle_speech_interruption(self) -> None:
        """Handle user speech interruption"""
        if not self.session.last_assistant_item or self.session.response_start_timestamp is None:
            return
        
        elapsed_ms = (self.session.latest_media_timestamp or 0) - (self.session.response_start_timestamp or 0)
        audio_end_ms = max(elapsed_ms, 0)
        
        # Truncate the current response
        if self.session.is_model_connected():
            truncate_message = {
                "type": "conversation.item.truncate",
                "item_id": self.session.last_assistant_item,
                "content_index": 0,
                "audio_end_ms": audio_end_ms
            }
            await self.session.send_to_model(truncate_message)
        
        # Clear Twilio's audio buffer
        if self.session.twilio_conn and self.session.stream_sid:
            clear_message = {
                "event": "clear",
                "streamSid": self.session.stream_sid
            }
            await self.session.send_to_twilio(clear_message)
        
        self.session.last_assistant_item = None
        self.session.response_start_timestamp = None


class SessionConfiguration:
    """Handles session configuration and setup"""
    
    def __init__(self, agent_config):
        self.agent_config = agent_config
        self.logger = logging.getLogger(f"{__name__}.SessionConfiguration")
    
    def get_session_config(self) -> Dict[str, Any]:
        """Get complete session configuration"""
        # Use agent configuration if available, otherwise use defaults
        if self.agent_config and hasattr(self.agent_config, 'to_openai_config'):
            config = self.agent_config.to_openai_config()
            self.logger.info(f"🎯 Using agent config with Twilio audio formats")
        else:
            config = self._get_default_config()
            self.logger.info(f"🎯 Using default config with Twilio audio formats")
        
        # Override audio formats for Twilio compatibility
        config["input_audio_format"] = "g711_ulaw"
        config["output_audio_format"] = "g711_ulaw"
        
        # Add tool handling instructions with agent timezone
        agent_timezone = getattr(self.agent_config, 'agent_timezone', 'UTC') if self.agent_config else 'UTC'
        self._add_tool_instructions(config, agent_timezone)
        
        # Ensure tool_choice is set to auto
        config["tool_choice"] = "auto"
        
        return config
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default session configuration"""
        return {
            "modalities": ["text", "audio"],
            "turn_detection": {"type": "server_vad"},
            "voice": "alloy",
            "input_audio_transcription": {"model": "whisper-1"},
        }
    
    def _add_tool_instructions(self, config: Dict[str, Any], agent_timezone: str = "UTC") -> None:
        """Add tool handling instructions to session config"""
        # Baseline mandatory instructions for all voice agents
        baseline_instructions = f"""📌 Baseline Mandatory Instructions for you to follow:
The initil message you receive is just to put you on the context , not for sharing with the user. 
This include the time zone, don't tell the user youare operatin in this time zone,keepthis for yoursel when you need it.  
You are connected to an MCP server with tools and tenant-scoped resources (documents, KBs, APIs).
Don't assume your time zone is the same as the user's time zone when you plan to use meeting scheduling or availability tools.
You are operating in the {agent_timezone} timezone - use this for all time-related references and awareness.
Always check KB/resources first before saying you don't know. Only after confirming no relevant resource is available may you say you don't know.
Use tools naturally — do not explain the tool itself to the user, only use the result in your answer.
Keep responses natural & concise — speak like a human, not like a script.
Acknowledge the user's input before answering (e.g., "Good question, let me check…").
Avoid hallucinations — never invent details that are not available in KBs or resources.
Respect user interruptions — stop speaking immediately when interrupted and listen.
Maintain session memory — remain consistent with facts mentioned earlier in the conversation.
Stay polite & professional — no slang unless explicitly configured.
Use filler words moderately if your personality config allows (e.g., "Well," "Let's see…").
If a tool call fails, retry once. If it still fails, acknowledge gracefully and continue.
Never expose raw tool call details, API responses, or error messages to the user.
If you are going to use the meeting booking tools please refrin from reading the meeting link to the user, just tell them that the meeting is booked in 
a professional way and that they will receive confoirmation via email. 
When you collect user email spell it out back to the user for the part before the "@" sign., this is to confirm  email is correct , spell it charecter by 
charecter, don't tell the user you are reading the part before the "@" , just tell them you need to conform the email is correct.
If the part after the "@" is not a common email doain like google , yahoo etc.. , spell out the part after "@" sign too. 

After any tool call, briefly explain the result to the caller and offer a follow-up question or next step. Do not wait for the user to ask what happened. Always speak the tool results out loud."""
        
        if "instructions" in config:
            config["instructions"] = f"{baseline_instructions}\n\n{config['instructions']}"
        else:
            config["instructions"] = baseline_instructions


class RealtimeSession:
    """Manages a single realtime session with OpenAI and Twilio"""
    
    def __init__(self, session_id: str, agent_config=None):
        self.session_id = session_id
        self.agent_config = agent_config
        
        # Connection management
        self.twilio_conn = None
        self.model_conn = None
        self.stream_sid: Optional[str] = None
        
        # Session state
        self.saved_config: Optional[Dict[str, Any]] = None
        self.last_assistant_item: Optional[str] = None
        self.response_start_timestamp: Optional[float] = None
        self.latest_media_timestamp: Optional[float] = None
        self.conversation = None
        
        # Function call argument buffering
        self._fn_arg_buffers = {}  # call_id -> {"name": str, "args": []}
        self._mcp_pending_calls = {}  # item_id -> arguments_json
        
        # Component handlers
        self.mcp_integration = MCPIntegration(agent_config)
        self.tool_handler = ToolHandler(self)
        self.audio_handler = AudioHandler(self)
        self.config_handler = SessionConfiguration(agent_config)
        
        # Initialize session
        self._initialize_session()
    
    def _initialize_session(self) -> None:
        """Initialize session with agent configuration"""
        if self.agent_config:
            try:
                logger.info(f"🤖 Session {self.session_id} initialized with agent: {self.agent_config.name} (ID: {self.agent_config.id})")
                self.saved_config = self.agent_config.to_openai_config()
                logger.info(f"🎯 Agent config loaded: voice={self.agent_config.voice}, instructions={self.agent_config.instructions[:50]}...")
                
                # Log MCP integration status
                if self.agent_config.has_mcp_integration():
                    logger.info(f"🔗 MCP integration enabled for agent {self.agent_config.name} (tenant: {self.agent_config.mcp_tenant_id})")
                else:
                    logger.info(f"🔗 No MCP integration configured for agent {self.agent_config.name}")
                    
            except Exception as e:
                logger.warning(f"🤖 Error loading agent config: {e}")
                logger.info(f"🤖 Session {self.session_id} initialized with agent config")
        else:
            logger.warning(f"🤖 Session {self.session_id} initialized with NO agent config")
        
        self.openai_api_key = self._get_openai_api_key()
    
    def _get_openai_api_key(self) -> str:
        """Get OpenAI API key from agent's user profile or fallback to system default"""
        try:
            if self.agent_config:
                api_key = self.agent_config.get_user_api_key()
                logger.info(f"🔑 Retrieved API key for agent {self.agent_config.name}: {api_key[:20]}...")
                return api_key
            else:
                logger.warning("🔑 No agent_config available, using system default")
        except Exception as e:
            logger.warning(f"🔑 Error getting user API key, using system default: {e}")
        
        logger.warning(f"🔑 Using system API key: {settings.OPENAI_API_KEY[:20]}...")
        return settings.OPENAI_API_KEY
    
    def set_agent_config(self, agent_config) -> None:
        """Set the agent configuration and update API key"""
        self.agent_config = agent_config
        self.openai_api_key = self._get_openai_api_key()
        if agent_config:
            self.saved_config = agent_config.to_openai_config()
            # Log MCP integration status
            if agent_config.has_mcp_integration():
                logger.info(f"🔗 MCP integration enabled for agent {agent_config.name} (tenant: {agent_config.mcp_tenant_id})")
            else:
                logger.info(f"🔗 No MCP integration configured for agent {agent_config.name}")
    
    def set_twilio_connection(self, consumer) -> None:
        """Set the Django Channels consumer as Twilio connection"""
        self.twilio_conn = consumer
        logger.info(f"Twilio connection established for session {self.session_id}")
    
    async def handle_twilio_message(self, data: str) -> None:
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
    
    async def handle_stream_start(self, msg: Dict[str, Any]) -> None:
        """Handle Twilio stream start event"""
        start_data = msg.get('start', {})
        self.stream_sid = start_data.get('streamSid')
        self.latest_media_timestamp = 0
        self.last_assistant_item = None
        self.response_start_timestamp = None
        
        logger.info(f"Stream started: {self.stream_sid}")
        
        # Use MCP-enabled connection if agent has MCP integration
        if self.agent_config and self.agent_config.has_mcp_integration():
            logger.info(f"🔗 Using MCP-enabled connection for agent {self.agent_config.name}")
            await self.try_connect_model_with_mcp()
        else:
            logger.info(f"📡 Using standard connection (no MCP)")
            await self.try_connect_model()
    
    async def handle_media(self, msg: Dict[str, Any]) -> None:
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
    
    async def handle_stream_stop(self, msg: Dict[str, Any]) -> None:
        """Handle Twilio stream stop event"""
        logger.info(f"Stream stopped: {self.stream_sid}")
        await self.cleanup_all_connections()
    
    async def try_connect_model_with_mcp(self) -> None:
        """Connect to OpenAI Realtime API using official client with MCP support"""
        if not self.twilio_conn or not self.stream_sid or not self.openai_api_key:
            logger.warning("Cannot connect to model: missing requirements")
            return
            
        if self.is_model_connected():
            logger.info("Model already connected")
            return
        
        try:
            # Log MCP connection details
            self.mcp_integration.log_connection_attempt()
            
            # Use the standard connection method but ensure MCP tools are added
            await self.try_connect_model()
            
            # Log MCP connection status
            if self.is_model_connected():
                logger.info(f"🔗 MCP CONNECTION: Successfully connected to OpenAI with MCP support")
                logger.info(f"🔗 MCP CONNECTION: MCP tools will be available for agent {self.agent_config.name}")
            else:
                logger.warning(f"🔗 MCP CONNECTION: Failed to establish connection with MCP support")
            
        except Exception as e:
            logger.error(f"🔗 MCP CONNECTION: Failed to connect to OpenAI with MCP: {e}")
            self.model_conn = None

    async def try_connect_model(self) -> None:
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
            
            # Use agent's model if available, otherwise use system default
            model_name = self.agent_config.model if self.agent_config else settings.OPENAI_REALTIME_MODEL
            model_url = f"{settings.OPENAI_REALTIME_URL}?model={model_name}"
            
            # DEBUG: Log connection details
            logger.info(f"Connecting to OpenAI with key: {self.openai_api_key[:20]}...")
            logger.info(f"URL: {model_url}")
            logger.info(f"Headers: {headers}")
            
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
    
    async def configure_session(self) -> None:
        """Configure the OpenAI session"""
        try:
            # Get session configuration
            config = self.config_handler.get_session_config()
            
            # Add MCP tools if agent has MCP integration
            if self.mcp_integration.is_enabled:
                mcp_tool = self.mcp_integration.get_mcp_tool_config()
                if mcp_tool:
                    config.setdefault("tools", []).append(mcp_tool)
                    logger.info(f"🔗 MCP TOOL: Added MCP tool to session configuration")
                    logger.info(f"🔗 MCP TOOL: Server label: {mcp_tool['server_label']}")
                    logger.info(f"🔗 MCP TOOL: Server URL: {mcp_tool['server_url']}")
                    logger.info(f"🔗 MCP TOOL: Auth token: {self.agent_config.mcp_auth_token[:20] if self.agent_config.mcp_auth_token else 'None'}...")
                    logger.info(f"🔗 MCP TOOL: Total tools in config: {len(config.get('tools', []))}")
            else:
                logger.info(f"🔗 MCP TOOL: No MCP integration configured for this agent")
            
            session_config = {
                "type": "session.update",
                "session": config
            }
            
            await self.send_to_model(session_config)
            logger.info(f"🎯 OpenAI session configured with: voice={config.get('voice', 'default')}, instructions={config.get('instructions', 'default')[:50]}...")
            logger.info("OpenAI session configured successfully")
            
            # Send initial greeting message after a brief delay to ensure session is ready
            asyncio.create_task(self.send_delayed_greeting())
            
        except Exception as e:
            logger.error(f"Error configuring OpenAI session: {e}")
            raise
    
    async def send_delayed_greeting(self) -> None:
        """Send greeting after a small delay to ensure session is fully ready"""
        await asyncio.sleep(1.5)  # Wait 1.5 seconds for session to be fully established
        await self.send_initial_greeting()
    
    async def send_initial_greeting(self) -> None:
        """Send an initial message to prompt the agent to greet the caller"""
        try:
            # Check if model connection is still active
            if not self.is_model_connected():
                logger.warning("🎤 Model connection not active, skipping initial greeting")
                return
            
            # Get agent name for personalized greeting prompt
            agent_name = "Assistant"
            if self.agent_config and self.agent_config.name:
                agent_name = self.agent_config.name
            
            # Get agent timezone for initial message
            agent_timezone = getattr(self.agent_config, 'agent_timezone', 'UTC') if self.agent_config else 'UTC'
            
            # Create an initial conversation item to trigger the greeting
            greeting_prompt = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Hello {agent_name}, the call has just connected. You are operating in the {agent_timezone} timezone. Please greet the caller and start the conversation according to your instructions."
                        }
                    ]
                }
            }
            
            # Send the greeting prompt
            await self.send_to_model(greeting_prompt)
            
            # Create a response to the greeting prompt
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"]
                }
            }
            
            await self.send_to_model(response_create)
            logger.info(f"🎤 Sent initial greeting prompt to {agent_name}")
            
        except Exception as e:
            logger.error(f"Error sending initial greeting: {e}")
    
    async def initialize_conversation_tracking(self, call_session) -> None:
        """Initialize conversation tracking for this session"""
        try:
            self.conversation = await conversation_tracker.get_or_create_conversation(call_session)
            logger.info(f"📝 Conversation tracking initialized for session {self.session_id[:8]}...")
        except Exception as e:
            logger.error(f"Error initializing conversation tracking: {e}")
    
    async def listen_to_model(self) -> None:
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
    
    async def handle_model_message(self, data: str) -> None:
        """Handle messages from OpenAI"""
        try:
            event = json.loads(data)
            event_type = event.get('type')
            
            # Log important MCP and tool events
            if event_type and ('mcp' in event_type.lower() or 'function' in event_type.lower() or 'tool' in event_type.lower()):
                if event_type in ['response.mcp_call_arguments.done', 'response.mcp_call.completed', 'response.function_call_arguments.done', 'conversation.item.create']:
                    logger.info(f"🔗 MCP/TOOL EVENT: {event_type}")
                elif event_type in ['response.mcp_call_arguments.delta', 'response.function_call_arguments.delta']:
                    logger.debug(f"🔗 MCP/TOOL STREAMING: {event_type}")
                else:
                    logger.info(f"🔗 MCP/TOOL EVENT: {event_type}")
            
            # Track all events for conversation history
            if self.conversation:
                await conversation_tracker.handle_realtime_event(self.conversation, event)
            
            if event_type == 'input_audio_buffer.speech_started':
                await self.audio_handler.handle_speech_interruption()
            elif event_type == 'response.audio.delta':
                await self.audio_handler.handle_audio_response(event)
            elif event_type == 'response.function_call_arguments.delta':
                # Buffer function call arguments as they stream in
                call_id = event.get('call_id')
                name = event.get('name')
                chunk = event.get('delta', '')
                if call_id:
                    buf = self._fn_arg_buffers.setdefault(call_id, {"name": name, "args": []})
                    if name and not buf.get("name"):
                        buf["name"] = name
                    buf["args"].append(chunk)
                else:
                    logger.warning(f"🔧 TOOL CALL: No call_id in delta event")
            elif event_type == 'response.function_call_arguments.done':
                # Function call arguments are complete - execute the tool
                call_id = event.get('call_id')
                
                if not call_id or call_id not in self._fn_arg_buffers:
                    logger.warning(f"🔧 TOOL CALL: No buffer found for call_id {call_id}")
                    return
                
                name = self._fn_arg_buffers[call_id]["name"] or event.get('name') or ''
                raw_args = ''.join(self._fn_arg_buffers[call_id]["args"])  # JSON text
                
                logger.info(f"🔧 TOOL CALL: Executing {name} with args: {raw_args}")
                logger.info(f"🔧 TOOL CALL: Tool execution started for {name}")
                
                # Clean up buffer early to avoid leaks
                del self._fn_arg_buffers[call_id]
                
                # Hand off to tool execution
                await self._handle_function_call_from_args(name, raw_args, call_id)
            elif event_type == 'response.mcp_call_arguments.delta':
                # Buffer MCP call arguments as they stream in
                item_id = event.get('item_id')
                chunk = event.get('delta', '')
                if item_id:
                    buf = self._fn_arg_buffers.setdefault(item_id, {"name": "mcp_call", "args": []})
                    buf["args"].append(chunk)
                else:
                    logger.warning(f"🔗 MCP TOOL CALL: No item_id in delta event")
            elif event_type == 'response.mcp_call_arguments.done':
                # MCP call arguments are complete - execute the tool
                item_id = event.get('item_id')
                arguments = event.get('arguments', '{}')
                
                # Get the buffered arguments if available
                if item_id and item_id in self._fn_arg_buffers:
                    raw_args = ''.join(self._fn_arg_buffers[item_id]["args"])
                    del self._fn_arg_buffers[item_id]
                else:
                    raw_args = arguments
                
                # For MCP calls, we need to wait for the actual completion event
                # Store the arguments for when the call completes
                self._mcp_pending_calls = getattr(self, '_mcp_pending_calls', {})
                self._mcp_pending_calls[item_id] = raw_args
                logger.info(f"🔗 MCP TOOL CALL: MCP call ready - {item_id}")
                logger.info(f"🔗 MCP TOOL CALL: Waiting for MCP server to process call")
            elif event_type == 'response.mcp_call.completed':
                # MCP call completed - now we can handle the result
                item_id = event.get('item_id')
                
                # Get the stored arguments
                self._mcp_pending_calls = getattr(self, '_mcp_pending_calls', {})
                if item_id in self._mcp_pending_calls:
                    raw_args = self._mcp_pending_calls[item_id]
                    del self._mcp_pending_calls[item_id]
                    logger.info(f"🔗 MCP TOOL CALL: MCP call completed - {item_id}")
                    logger.info(f"🔗 MCP TOOL CALL: MCP server processed call successfully")
                    
                    # For MCP calls, we don't need to execute tools - the MCP server handles it
                    # We just need to trigger a response to speak the result
                    await self._handle_mcp_call_completion(item_id, raw_args)
                else:
                    logger.warning(f"🔗 MCP TOOL CALL: No pending call found for item_id {item_id}")
            elif event_type == 'response.output_item.done':
                # Check if this is a function call item (fallback detection)
                item = event.get('item', {})
                if item.get('type') == 'function_call':
                    logger.warning(f"🔧 TOOL CALL: Function call detected via fallback path (response.output_item.done)")
                    logger.warning(f"🔧 TOOL CALL: This suggests the new event system may not be working")
                    await self.handle_output_item_done(event)
                else:
                    # Keep as fallback for non-function-call items
                    await self.handle_output_item_done(event)
            elif event_type == 'conversation.item.create':
                # Check if this is a tool call item
                item = event.get('item', {})
                if item.get('type') == 'function_call':
                    logger.info(f"🔧 TOOL EVENT: Function call - {item.get('name', 'Unknown')}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from OpenAI: {data}")
        except Exception as e:
            logger.error(f"Error handling model message: {e}")
    
    async def _handle_mcp_call_completion(self, item_id: str, arguments_json: str) -> None:
        """Handle MCP call completion - trigger response to speak the result"""
        # Send a response to make the agent speak about the MCP result
        await self.send_to_model({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": (
                    "The MCP tool call has completed. Please explain the results to the caller "
                    "in a clear and helpful way, and ask if they need anything else."
                )
            }
        })
        logger.info(f"🔗 MCP TOOL CALL: Response triggered for MCP result")

    async def _handle_function_call_from_args(self, function_name: str, arguments_json: str, call_id: str) -> None:
        """Handle function call execution from streamed arguments (recommended approach)"""
        from .tools import execute_tool
        
        logger.info(f"🔧 TOOL CALL: Executing {function_name}")

        # Send a quick "holding" response without injecting an assistant message item
        await self.send_to_model({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "One moment while I check that for you..."
            }
        })

        try:
            # Parse arguments with error handling
            try:
                args = json.loads(arguments_json or "{}")
            except json.JSONDecodeError as e:
                logger.warning(f"🔧 TOOL CALL: Invalid JSON arguments, using empty dict: {e}")
                args = {}
            
            # Execute the tool
            result = await execute_tool(function_name, args)
            logger.info(f"🔧 TOOL CALL: Tool completed - {function_name}")

            # Step 1: Attach tool result to conversation
            await self.send_to_model({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result) if not isinstance(result, str) else result
                }
            })

            # Step 2: Explicitly ask the model to speak about it
            await self.send_to_model({
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": (
                        "Briefly explain the tool result to the caller and offer a next step. "
                        "Avoid jargon and confirm if they'd like you to proceed."
                    )
                }
            })
            logger.info(f"🔧 TOOL CALL: Response triggered for {function_name}")

        except Exception as e:
            logger.error(f"🔧 TOOL CALL: Error executing {function_name}: {e}")

    async def handle_output_item_done(self, event: Dict[str, Any]) -> None:
        """Handle completed output items (fallback for non-function-call items)"""
        item = event.get('item', {})
        
        if item.get('type') == 'function_call':
            # This is a fallback - the main path should be via _handle_function_call_from_args
            logger.warning(f"🔧 TOOL CALL: Function call detected via fallback path - this may indicate timing issues")
            await self.tool_handler.execute_tool_call(item)
    
    async def send_to_model(self, message: Dict[str, Any]) -> None:
        """Send message to OpenAI"""
        if self.is_model_connected():
            await self.model_conn.send(json.dumps(message))
    
    async def send_to_twilio(self, message: Dict[str, Any]) -> None:
        """Send message to Twilio"""
        if self.twilio_conn:
            await self.twilio_conn.send(text_data=json.dumps(message))
    
    def is_model_connected(self) -> bool:
        """Check if model connection is open"""
        return (self.model_conn and 
                self.model_conn.open and 
                not self.model_conn.closed)
    
    async def cleanup_connection(self, conn) -> None:
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
    
    async def close_model(self) -> None:
        """Close model connection"""
        await self.cleanup_connection(self.model_conn)
        self.model_conn = None
    
    async def cleanup_all_connections(self) -> None:
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


class SessionManager:
    """Manages multiple realtime sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, RealtimeSession] = {}
        self.logger = logging.getLogger(f"{__name__}.SessionManager")
    
    def get_session(self, session_id: str, agent_config=None) -> RealtimeSession:
        """Get or create a session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = RealtimeSession(session_id, agent_config)
            self.logger.info(f"Created new session: {session_id[:8]}...")
        elif agent_config and not self.sessions[session_id].agent_config:
            # Set agent config if not already set
            self.sessions[session_id].set_agent_config(agent_config)
            self.logger.info(f"Updated session {session_id[:8]}... with agent config")
        
        return self.sessions[session_id]
    
    def remove_session(self, session_id: str) -> None:
        """Remove a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.info(f"Removed session: {session_id[:8]}...")
    
    async def cleanup_session(self, session_id: str) -> None:
        """Clean up a session"""
        if session_id in self.sessions:
            await self.sessions[session_id].cleanup_all_connections()
            self.remove_session(session_id)
            self.logger.info(f"Cleaned up session: {session_id[:8]}...")


# Global session manager instance
session_manager = SessionManager()