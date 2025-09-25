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
from channels.db import database_sync_to_async
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
        
        # Enhanced debug logging
        self.logger.info(f"🔧 TOOL CALL: ===== TOOL EXECUTION START =====")
        self.logger.info(f"🔧 TOOL CALL: Function Name: {function_name}")
        self.logger.info(f"🔧 TOOL CALL: Call ID: {call_id}")
        self.logger.info(f"🔧 TOOL CALL: Raw Arguments: {arguments}")
        self.logger.info(f"🔧 TOOL CALL: Timestamp: {datetime.now().isoformat()}")
        
        # Check if this is an MCP tool call
        if self._is_mcp_tool(function_name):
            self.logger.info(f"🔗 MCP TOOL CALL: MCP function detected: {function_name}")
            self.logger.info(f"🔗 MCP TOOL CALL: This will be handled by MCP server")
        
        try:
            # Send holding message to avoid dead air
            await self._send_holding_message()
            
            # Parse and execute tool with enhanced error handling
            try:
                args = json.loads(arguments)
                self.logger.info(f"🔧 TOOL CALL: Parsed Arguments: {json.dumps(args, indent=2)}")
            except json.JSONDecodeError as json_err:
                self.logger.error(f"🔧 TOOL CALL: JSON Parse Error: {json_err}")
                self.logger.error(f"🔧 TOOL CALL: Invalid JSON: {arguments}")
                raise
            
            self.logger.info(f"🔧 TOOL CALL: Starting execution of {function_name}...")
            result = await execute_tool(function_name, args)
            
            # Enhanced result logging
            self.logger.info(f"🔧 TOOL CALL: ===== TOOL EXECUTION COMPLETED =====")
            self.logger.info(f"🔧 TOOL CALL: Function: {function_name}")
            self.logger.info(f"🔧 TOOL CALL: Success: True")
            if isinstance(result, dict):
                self.logger.info(f"🔧 TOOL CALL: Result Type: Dict")
                self.logger.info(f"🔧 TOOL CALL: Result Keys: {list(result.keys())}")
                if 'error' in result:
                    self.logger.error(f"🔧 TOOL CALL: Tool returned error: {result['error']}")
                else:
                    self.logger.info(f"🔧 TOOL CALL: Result: {json.dumps(result, indent=2)}")
            else:
                self.logger.info(f"🔧 TOOL CALL: Result Type: {type(result).__name__}")
                self.logger.info(f"🔧 TOOL CALL: Result: {str(result)}")
            
            # Send tool result and trigger response
            await self._send_tool_result_and_trigger_response(call_id, result)
            
        except Exception as e:
            # Enhanced error logging
            self.logger.error(f"🔧 TOOL CALL: ===== TOOL EXECUTION FAILED =====")
            self.logger.error(f"🔧 TOOL CALL: Function: {function_name}")
            self.logger.error(f"🔧 TOOL CALL: Call ID: {call_id}")
            self.logger.error(f"🔧 TOOL CALL: Error Type: {type(e).__name__}")
            self.logger.error(f"🔧 TOOL CALL: Error Message: {str(e)}")
            self.logger.error(f"🔧 TOOL CALL: Arguments: {arguments}")
            self.logger.error(f"🔧 TOOL CALL: Timestamp: {datetime.now().isoformat()}")
            
            # Send error result to model
            error_result = {
                "error": f"Tool execution failed: {str(e)}",
                "function_name": function_name,
                "call_id": call_id
            }
            await self._send_tool_result_and_trigger_response(call_id, error_result)
    
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
        self.logger.info(f"🔧 TOOL CALL: ===== SENDING TOOL RESULT =====")
        self.logger.info(f"🔧 TOOL CALL: Call ID: {call_id}")
        self.logger.info(f"🔧 TOOL CALL: Result Type: {type(result).__name__}")
        
        # Step 1: Attach tool result to conversation
        function_output = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result) if not isinstance(result, str) else result
            }
        }
        
        self.logger.info(f"🔧 TOOL CALL: Step 1 - Attaching tool result to conversation...")
        self.logger.info(f"🔧 TOOL CALL: Function output: {json.dumps(function_output, indent=2)}")
        
        try:
            await self.session.send_to_model(function_output)
            self.logger.info(f"🔧 TOOL CALL: Step 1 - Tool result attached to conversation successfully")
        except Exception as e:
            self.logger.error(f"🔧 TOOL CALL: Step 1 - Failed to attach tool result: {e}")
            return
        
        # Step 2: Trigger generation with audio
        response_create = {
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "Briefly explain the tool result to the caller and offer a follow-up question or next step. Do not wait for the user to ask what happened."
            }
        }
        
        self.logger.info(f"🔧 TOOL CALL: Step 2 - Triggering response generation...")
        self.logger.info(f"🔧 TOOL CALL: Response create: {json.dumps(response_create, indent=2)}")
        
        try:
            await self.session.send_to_model(response_create)
            self.logger.info(f"🔧 TOOL CALL: Step 2 - Response generation triggered with audio successfully")
            self.logger.info(f"🔧 TOOL CALL: Agent will now speak the tool result to the caller")
        except Exception as e:
            self.logger.error(f"🔧 TOOL CALL: Step 2 - Failed to trigger response: {e}")


class AudioHandler:
    """Handles Twilio audio stream management"""
    
    def __init__(self, session):
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.AudioHandler")
    
    async def handle_audio_response(self, event: Dict[str, Any]) -> None:
        """Handle audio response from OpenAI and send to Twilio"""
        if not self.session.twilio_conn or not self.session.stream_sid:
            self.logger.warning(f"🎵 AUDIO RESPONSE: Missing Twilio connection or stream SID")
            return
            
        delta = event.get('delta', '')
        item_id = event.get('item_id')
        
        # Only log when response starts (first delta)
        if self.session.response_start_timestamp is None:
            self.session.response_start_timestamp = self.session.latest_media_timestamp or 0
            self.logger.info(f"🎵 AUDIO RESPONSE: Response started at timestamp: {self.session.response_start_timestamp}")
            
        if item_id:
            self.session.last_assistant_item = item_id
        
        # Send audio to Twilio
        media_message = {
            "event": "media",
            "streamSid": self.session.stream_sid,
            "media": {"payload": delta}
        }
        
        try:
            await self.session.send_to_twilio(media_message)
        except Exception as e:
            self.logger.error(f"🎵 AUDIO RESPONSE: Failed to send audio to Twilio: {e}")
        
        # Send mark for synchronization
        mark_message = {
            "event": "mark",
            "streamSid": self.session.stream_sid
        }
        
        try:
            await self.session.send_to_twilio(mark_message)
        except Exception as e:
            self.logger.error(f"🎵 AUDIO RESPONSE: Failed to send mark to Twilio: {e}")
    
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
        # Get agent name for personalized instructions
        agent_name = "Assistant"
        if self.agent_config and self.agent_config.name:
            agent_name = self.agent_config.name
        
        # Baseline mandatory instructions for all voice agents
        baseline_instructions = f"""📌 Baseline Mandatory Instructions for you to follow:
Your name is {agent_name}.
The initil message you receive is just to put you on the context , not for sharing with the user. 
This include the time zone, don't tell the user youare operatin in this time zone,keepthis for yoursel when you need it.  
You are connected to an MCP server with tools and tenant-scoped resources (documents, KBs, APIs).
Don't assume your time zone is the same as the user's time zone when you plan to use meeting scheduling or availability tools.
You are operating in the {agent_timezone} timezone - use this for all time-related references and awareness.
When using the find staff availability tool or any scheduling tools, don't assume the user timezone is the same as your timezone, always
ask the user about thier timezone or location/city and then find their time zone using the tool available to you.
and use that to schedule the meeting.
Before using the find staff availability tool or schedling tool tell the user gently to hold till you find the best time or 
till you schedule the meeting using the booking system.
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

After any tool call, briefly explain the result to the caller and offer a follow-up question or next step.
Do not wait for the user to ask what happened. Always speak the tool results out loud.
 When you use the end call tool,never return the tools call results to the user, just say you are ending the call."""
        
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
        
        # Idle timeout tracking
        self.last_activity_time = asyncio.get_event_loop().time()
        self.idle_timeout_task = None
        self.idle_timeout_seconds = 300  # Default 5 minutes
        
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
                
                # Set idle timeout from agent config
                self.idle_timeout_seconds = getattr(self.agent_config, 'idle_timeout_seconds', 300)
                logger.info(f"⏰ Idle timeout set to {self.idle_timeout_seconds} seconds")
                
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
        await asyncio.sleep(1.0)  # Wait 1.0 seconds for session to be fully established
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
            
            # Get call information from the call session
            call_direction = "incoming"
            call_sid = ""
            caller_number = ""
            called_number = ""
            
            if hasattr(self, 'call_session') and self.call_session:
                call_sid = self.call_session.twilio_call_sid or ""
                caller_number = self.call_session.caller_number or ""
                called_number = self.call_session.called_number or ""
                
                # Determine call direction based on phone number ownership
                call_direction = "incoming"  # Default assumption
                
                if self.call_session.phone_number:
                    # If the called number matches our phone number, it's incoming
                    if self.call_session.phone_number.phone_number == called_number:
                        call_direction = "incoming"
                    else:
                        call_direction = "outgoing"
                else:
                    # If no phone_number is set, try to determine from our agent's phone numbers
                    if self.agent_config and hasattr(self.agent_config, 'user'):
                        try:
                            # Use async database query to determine call direction
                            call_direction = await self._determine_call_direction_async(caller_number, called_number)
                        except Exception as e:
                            logger.debug(f"Could not determine call direction: {e}")
                            # Keep default "incoming"
            
            # Get welcoming message from agent configuration
            welcoming_message = ""
            if self.agent_config and hasattr(self.agent_config, 'instructions') and self.agent_config.instructions:
                # Extract welcoming message from instructions if available
                instructions = self.agent_config.instructions
                if "welcoming message" in instructions.lower() or "greeting" in instructions.lower():
                    # Try to extract the welcoming message from instructions
                    lines = instructions.split('\n')
                    for line in lines:
                        if 'welcoming' in line.lower() or 'greeting' in line.lower():
                            welcoming_message = line.strip()
                            break
            
            # Create the enhanced greeting prompt
            if call_direction == "incoming":
                target_number = caller_number
                greeting_text = f"""You have an {call_direction} call from {target_number}. Call SID is "{call_sid}". You are operating in the {agent_timezone} timezone. Start using the welcoming message assigned to you."""
            else:
                target_number = called_number
                greeting_text = f"""You have an {call_direction} call to {target_number}. Call SID is "{call_sid}". You are operating in the {agent_timezone} timezone. Start using the welcoming message assigned to you."""
            
            if welcoming_message:
                greeting_text += f"\n\nYour welcoming message: {welcoming_message}"
            
            # Create an initial conversation item to trigger the greeting
            greeting_prompt = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": greeting_text
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
            # Store the call session for use in greeting
            self.call_session = call_session
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
            
            # Enhanced logging for important MCP and tool events
            if event_type and ('mcp' in event_type.lower() or 'function' in event_type.lower() or 'tool' in event_type.lower()):
                if event_type in ['response.mcp_call_arguments.done', 'response.mcp_call.completed', 'response.function_call_arguments.done', 'conversation.item.create']:
                    logger.info(f"🔗 MCP/TOOL EVENT: ===== {event_type} =====")
                    logger.info(f"🔗 MCP/TOOL EVENT: Event: {event_type}")
                    logger.info(f"🔗 MCP/TOOL EVENT: Timestamp: {datetime.now().isoformat()}")
                    if event_type == 'conversation.item.create':
                        item = event.get('item', {})
                        logger.info(f"🔗 MCP/TOOL EVENT: Item Type: {item.get('type', 'unknown')}")
                        if item.get('type') == 'function_call':
                            logger.info(f"🔗 MCP/TOOL EVENT: Function Name: {item.get('name', 'unknown')}")
                elif event_type in ['response.mcp_call_arguments.delta', 'response.function_call_arguments.delta']:
                    logger.debug(f"🔗 MCP/TOOL STREAMING: {event_type} - Delta length: {len(event.get('delta', ''))}")
                else:
                    logger.info(f"🔗 MCP/TOOL EVENT: {event_type}")
                    logger.info(f"🔗 MCP/TOOL EVENT: Event details: {json.dumps(event, indent=2)}")
            
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
                
                logger.debug(f"🔧 TOOL CALL: Function call delta - Call ID: {call_id}, Name: {name}, Chunk length: {len(chunk)}")
                
                if call_id:
                    buf = self._fn_arg_buffers.setdefault(call_id, {"name": name, "args": []})
                    if name and not buf.get("name"):
                        buf["name"] = name
                    buf["args"].append(chunk)
                    logger.debug(f"🔧 TOOL CALL: Buffered chunk for {call_id}, total chunks: {len(buf['args'])}")
                else:
                    logger.warning(f"🔧 TOOL CALL: No call_id in delta event")
                    logger.warning(f"🔧 TOOL CALL: Event: {json.dumps(event, indent=2)}")
            elif event_type == 'response.function_call_arguments.done':
                # Function call arguments are complete - execute the tool
                call_id = event.get('call_id')
                
                logger.info(f"🔧 TOOL CALL: ===== FUNCTION CALL ARGUMENTS COMPLETE =====")
                logger.info(f"🔧 TOOL CALL: Call ID: {call_id}")
                logger.info(f"🔧 TOOL CALL: Event: {event_type}")
                logger.info(f"🔧 TOOL CALL: Available buffers: {list(self._fn_arg_buffers.keys())}")
                
                if not call_id or call_id not in self._fn_arg_buffers:
                    logger.error(f"🔧 TOOL CALL: No buffer found for call_id {call_id}")
                    logger.error(f"🔧 TOOL CALL: Available call_ids: {list(self._fn_arg_buffers.keys())}")
                    return
                
                name = self._fn_arg_buffers[call_id]["name"] or event.get('name') or ''
                raw_args = ''.join(self._fn_arg_buffers[call_id]["args"])  # JSON text
                
                logger.info(f"🔧 TOOL CALL: Function Name: {name}")
                logger.info(f"🔧 TOOL CALL: Raw Arguments: {raw_args}")
                logger.info(f"🔧 TOOL CALL: Buffer Size: {len(self._fn_arg_buffers[call_id]['args'])} chunks")
                
                # Clean up buffer early to avoid leaks
                del self._fn_arg_buffers[call_id]
                logger.info(f"🔧 TOOL CALL: Buffer cleaned up for call_id {call_id}")
                
                # Hand off to tool execution
                logger.info(f"🔧 TOOL CALL: Handing off to tool execution...")
                await self._handle_function_call_from_args(name, raw_args, call_id)
            elif event_type == 'response.mcp_call_arguments.delta':
                # Buffer MCP call arguments as they stream in
                item_id = event.get('item_id')
                chunk = event.get('delta', '')
                
                logger.debug(f"🔗 MCP TOOL CALL: MCP call delta - Item ID: {item_id}, Chunk length: {len(chunk)}")
                
                if item_id:
                    buf = self._fn_arg_buffers.setdefault(item_id, {"name": "mcp_call", "args": []})
                    buf["args"].append(chunk)
                    logger.debug(f"🔗 MCP TOOL CALL: Buffered chunk for {item_id}, total chunks: {len(buf['args'])}")
                    
                    # Log the current accumulated content for debugging
                    current_content = ''.join(buf["args"])
                    if len(current_content) > 0:
                        logger.debug(f"🔗 MCP TOOL CALL: Current accumulated content: {current_content[:200]}...")
                else:
                    logger.warning(f"🔗 MCP TOOL CALL: No item_id in delta event")
                    logger.warning(f"🔗 MCP TOOL CALL: Event: {json.dumps(event, indent=2)}")
            elif event_type == 'response.mcp_call.in_progress':
                # MCP call is in progress
                item_id = event.get('item_id')
                logger.info(f"🔗 MCP TOOL CALL: ===== MCP CALL IN PROGRESS =====")
                logger.info(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
                logger.info(f"🔗 MCP TOOL CALL: Event: {event_type}")
                logger.info(f"🔗 MCP TOOL CALL: MCP server is processing the call...")
                
                # Log any additional progress information
                if 'content' in event:
                    content = event.get('content', [])
                    logger.info(f"🔗 MCP TOOL CALL: Progress content: {json.dumps(content, indent=2)}")
            elif event_type == 'response.mcp_call.failed':
                # MCP call failed
                item_id = event.get('item_id')
                logger.error(f"🔗 MCP TOOL CALL: ===== MCP CALL FAILED =====")
                logger.error(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
                logger.error(f"🔗 MCP TOOL CALL: Event: {event_type}")
                logger.error(f"🔗 MCP TOOL CALL: Full Event: {json.dumps(event, indent=2)}")
                
                # Extract error details from the event
                error_details = event.get('error', {})
                error_message = error_details.get('message', 'Unknown error')
                error_code = error_details.get('code', 'Unknown code')
                
                logger.error(f"🔗 MCP TOOL CALL: Error Code: {error_code}")
                logger.error(f"🔗 MCP TOOL CALL: Error Message: {error_message}")
                
                # Clean up any pending call for this item
                self._mcp_pending_calls = getattr(self, '_mcp_pending_calls', {})
                if item_id in self._mcp_pending_calls:
                    failed_args = self._mcp_pending_calls[item_id]
                    del self._mcp_pending_calls[item_id]
                    logger.error(f"🔗 MCP TOOL CALL: Failed call arguments: {failed_args}")
                    
                    # Send error feedback to the agent
                    await self._send_mcp_error_feedback(item_id, failed_args, error_message, error_code)
                
                logger.error(f"🔗 MCP TOOL CALL: MCP server failed to process the call")
            elif event_type == 'response.mcp_call_arguments.done':
                # MCP call arguments are complete - execute the tool
                item_id = event.get('item_id')
                arguments = event.get('arguments', '{}')
                
                logger.info(f"🔗 MCP TOOL CALL: ===== MCP ARGUMENTS COMPLETE =====")
                logger.info(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
                logger.info(f"🔗 MCP TOOL CALL: Event Arguments: {arguments}")
                logger.info(f"🔗 MCP TOOL CALL: Available Buffers: {list(self._fn_arg_buffers.keys())}")
                
                # Get the buffered arguments if available
                if item_id and item_id in self._fn_arg_buffers:
                    raw_args = ''.join(self._fn_arg_buffers[item_id]["args"])
                    logger.info(f"🔗 MCP TOOL CALL: Using buffered arguments: {raw_args}")
                    logger.info(f"🔗 MCP TOOL CALL: Buffer size: {len(self._fn_arg_buffers[item_id]['args'])} chunks")
                    del self._fn_arg_buffers[item_id]
                    logger.info(f"🔗 MCP TOOL CALL: Buffer cleaned up for item_id {item_id}")
                else:
                    raw_args = arguments
                    logger.info(f"🔗 MCP TOOL CALL: Using event arguments: {raw_args}")
                
                # Parse and log the MCP tool call details
                try:
                    parsed_args = json.loads(raw_args)
                    
                    # Extract tool name and parameters from the parsed arguments
                    if isinstance(parsed_args, dict):
                        # Check if this is a direct parameter object
                        if 'name' in parsed_args:
                            tool_name = parsed_args.get('name', 'Unknown MCP Tool')
                            tool_params = parsed_args.get('arguments', {})
                        else:
                            # This might be the parameters directly
                            tool_name = 'MCP Tool (name not provided)'
                            tool_params = parsed_args
                    else:
                        tool_name = 'MCP Tool (invalid format)'
                        tool_params = {}
                    
                    logger.info(f"🔗 MCP TOOL CALL: ===== MCP TOOL REQUEST =====")
                    logger.info(f"🔗 MCP TOOL CALL: Tool Name: {tool_name}")
                    logger.info(f"🔗 MCP TOOL CALL: Request Parameters:")
                    logger.info(f"🔗 MCP TOOL CALL: {json.dumps(tool_params, indent=2)}")
                    logger.info(f"🔗 MCP TOOL CALL: Raw Arguments: {raw_args}")
                    logger.info(f"🔗 MCP TOOL CALL: ===== END REQUEST =====")
                except json.JSONDecodeError as e:
                    logger.warning(f"🔗 MCP TOOL CALL: Could not parse MCP arguments: {e}")
                    logger.warning(f"🔗 MCP TOOL CALL: Raw arguments: {raw_args}")
                    logger.info(f"🔗 MCP TOOL CALL: ===== MCP TOOL REQUEST =====")
                    logger.info(f"🔗 MCP TOOL CALL: Tool Name: Unknown MCP Tool (JSON Parse Error)")
                    logger.info(f"🔗 MCP TOOL CALL: Request Parameters: {raw_args}")
                    logger.info(f"🔗 MCP TOOL CALL: ===== END REQUEST =====")
                
                # For MCP calls, we need to wait for the actual completion event
                # Store the arguments for when the call completes
                self._mcp_pending_calls = getattr(self, '_mcp_pending_calls', {})
                self._mcp_pending_calls[item_id] = raw_args
                logger.info(f"🔗 MCP TOOL CALL: MCP call ready - {item_id}")
                logger.info(f"🔗 MCP TOOL CALL: Raw arguments stored: {raw_args}")
                logger.info(f"🔗 MCP TOOL CALL: Waiting for MCP server to process call")
                logger.info(f"🔗 MCP TOOL CALL: Pending calls: {list(self._mcp_pending_calls.keys())}")
            elif event_type == 'response.mcp_call.completed':
                # MCP call completed - now we can handle the result
                item_id = event.get('item_id')
                
                logger.info(f"🔗 MCP TOOL CALL: ===== MCP CALL COMPLETED =====")
                logger.info(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
                logger.info(f"🔗 MCP TOOL CALL: Event: {event_type}")
                logger.info(f"🔗 MCP TOOL CALL: Full Event: {json.dumps(event, indent=2)}")
                
                # Get the stored arguments
                self._mcp_pending_calls = getattr(self, '_mcp_pending_calls', {})
                logger.info(f"🔗 MCP TOOL CALL: Pending calls: {list(self._mcp_pending_calls.keys())}")
                
                if item_id in self._mcp_pending_calls:
                    raw_args = self._mcp_pending_calls[item_id]
                    del self._mcp_pending_calls[item_id]
                    logger.info(f"🔗 MCP TOOL CALL: MCP call completed - {item_id}")
                    logger.info(f"🔗 MCP TOOL CALL: Stored arguments: {raw_args}")
                    logger.info(f"🔗 MCP TOOL CALL: MCP server processed call successfully")
                    
                    # Parse and log the original request for context
                    try:
                        parsed_args = json.loads(raw_args)
                        
                        # Extract tool name and parameters from the parsed arguments
                        if isinstance(parsed_args, dict):
                            # Check if this is a direct parameter object
                            if 'name' in parsed_args:
                                tool_name = parsed_args.get('name', 'Unknown MCP Tool')
                                tool_params = parsed_args.get('arguments', {})
                            else:
                                # This might be the parameters directly
                                tool_name = 'MCP Tool (name not provided)'
                                tool_params = parsed_args
                        else:
                            tool_name = 'MCP Tool (invalid format)'
                            tool_params = {}
                        
                        logger.info(f"🔗 MCP TOOL CALL: ===== MCP TOOL RESPONSE =====")
                        logger.info(f"🔗 MCP TOOL CALL: Tool Name: {tool_name}")
                        logger.info(f"🔗 MCP TOOL CALL: Original Request Parameters:")
                        logger.info(f"🔗 MCP TOOL CALL: {json.dumps(tool_params, indent=2)}")
                        logger.info(f"🔗 MCP TOOL CALL: Raw Arguments: {raw_args}")
                        
                        # Extract response content if available
                        response_content = event.get('content', [])
                        if response_content:
                            logger.info(f"🔗 MCP TOOL CALL: Response Content:")
                            for content_item in response_content:
                                if content_item.get('type') == 'text':
                                    logger.info(f"🔗 MCP TOOL CALL: {content_item.get('text', '')}")
                                elif content_item.get('type') == 'resource':
                                    resource = content_item.get('resource', {})
                                    logger.info(f"🔗 MCP TOOL CALL: Resource: {json.dumps(resource, indent=2)}")
                        
                        # Check for any error information in the completion event
                        error_info = event.get('error')
                        if error_info:
                            logger.warning(f"🔗 MCP TOOL CALL: Completion with error info: {json.dumps(error_info, indent=2)}")
                            
                            # Send error feedback to agent even for "completed" calls with errors
                            error_message = error_info.get('message', 'Unknown error')
                            error_code = error_info.get('code', 'Unknown code')
                            await self._send_mcp_error_feedback(item_id, raw_args, error_message, error_code)
                        
                        logger.info(f"🔗 MCP TOOL CALL: ===== END RESPONSE =====")
                    except json.JSONDecodeError as e:
                        logger.warning(f"🔗 MCP TOOL CALL: Could not parse stored arguments: {e}")
                        logger.info(f"🔗 MCP TOOL CALL: ===== MCP TOOL RESPONSE =====")
                        logger.info(f"🔗 MCP TOOL CALL: Tool Name: Unknown MCP Tool (JSON Parse Error)")
                        logger.info(f"🔗 MCP TOOL CALL: Original Request Parameters: {raw_args}")
                        logger.info(f"🔗 MCP TOOL CALL: ===== END RESPONSE =====")
                    
                    logger.info(f"🔗 MCP TOOL CALL: Triggering response generation...")
                    
                    # For MCP calls, we don't need to execute tools - the MCP server handles it
                    # We just need to trigger a response to speak the result
                    await self._handle_mcp_call_completion(item_id, raw_args)
                    logger.info(f"🔗 MCP TOOL CALL: Response generation completed")
                else:
                    logger.error(f"🔗 MCP TOOL CALL: ===== NO PENDING CALL FOUND =====")
                    logger.error(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
                    logger.error(f"🔗 MCP TOOL CALL: Available pending calls: {list(self._mcp_pending_calls.keys())}")
                    logger.error(f"🔗 MCP TOOL CALL: This may indicate a timing issue or lost call")
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
        logger.info(f"🔗 MCP TOOL CALL: ===== HANDLING MCP COMPLETION =====")
        logger.info(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
        logger.info(f"🔗 MCP TOOL CALL: Arguments: {arguments_json}")
        
        try:
            # Send a response to make the agent speak about the MCP result
            response_message = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": (
                        "The MCP tool call has completed. Please explain the results to the caller "
                        "in a clear and helpful way, and ask if they need anything else."
                    )
                }
            }
            
            logger.info(f"🔗 MCP TOOL CALL: Sending response message to model...")
            logger.info(f"🔗 MCP TOOL CALL: Response message: {json.dumps(response_message, indent=2)}")
            
            await self.send_to_model(response_message)
            logger.info(f"🔗 MCP TOOL CALL: Response triggered for MCP result")
            
        except Exception as e:
            logger.error(f"🔗 MCP TOOL CALL: ===== MCP COMPLETION ERROR =====")
            logger.error(f"🔗 MCP TOOL CALL: Error handling MCP completion: {e}")
            logger.error(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
            logger.error(f"🔗 MCP TOOL CALL: Arguments: {arguments_json}")
            logger.error(f"🔗 MCP TOOL CALL: Error Type: {type(e).__name__}")
    
    async def _send_mcp_error_feedback(self, item_id: str, failed_args: str, error_message: str, error_code: str) -> None:
        """Send error feedback to the agent so it can learn from the mistake"""
        logger.info(f"🔗 MCP TOOL CALL: ===== SENDING ERROR FEEDBACK =====")
        logger.info(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
        logger.info(f"🔗 MCP TOOL CALL: Error Message: {error_message}")
        logger.info(f"🔗 MCP TOOL CALL: Error Code: {error_code}")
        
        try:
            # Parse the failed arguments to understand what went wrong
            try:
                parsed_args = json.loads(failed_args)
                if isinstance(parsed_args, dict):
                    if 'name' in parsed_args:
                        tool_name = parsed_args.get('name', 'Unknown Tool')
                        tool_params = parsed_args.get('arguments', {})
                    else:
                        tool_name = 'MCP Tool'
                        tool_params = parsed_args
                else:
                    tool_name = 'MCP Tool'
                    tool_params = {}
            except json.JSONDecodeError:
                tool_name = 'MCP Tool'
                tool_params = {}
            
            # Create a detailed error message for the agent
            error_feedback = f"""The MCP tool call failed with the following error:

Error Code: {error_code}
Error Message: {error_message}

Tool Parameters Used:
{json.dumps(tool_params, indent=2)}

Please review the error and try again with corrected parameters. Common issues include:
- Invalid timezone format (use standard timezone names like "America/New_York")
- Invalid date format (use ISO format like "2025-09-23")
- Missing required parameters
- Invalid parameter values"""
            
            # Send the error feedback to the agent
            error_response = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": (
                        f"I encountered an error with the tool call. {error_message} "
                        f"Please try again with corrected parameters. If this is a timezone issue, "
                        f"use standard timezone names like 'America/New_York' or 'UTC'."
                    )
                }
            }
            
            logger.info(f"🔗 MCP TOOL CALL: Sending error feedback to agent...")
            logger.info(f"🔗 MCP TOOL CALL: Error feedback: {json.dumps(error_response, indent=2)}")
            
            await self.send_to_model(error_response)
            logger.info(f"🔗 MCP TOOL CALL: Error feedback sent to agent")
            
        except Exception as e:
            logger.error(f"🔗 MCP TOOL CALL: ===== ERROR FEEDBACK FAILED =====")
            logger.error(f"🔗 MCP TOOL CALL: Error sending feedback: {e}")
            logger.error(f"🔗 MCP TOOL CALL: Item ID: {item_id}")
            logger.error(f"🔗 MCP TOOL CALL: Error Type: {type(e).__name__}")

    async def _handle_function_call_from_args(self, function_name: str, arguments_json: str, call_id: str) -> None:
        """Handle function call execution from streamed arguments (recommended approach)"""
        from .tools import execute_tool
        
        # Enhanced debug logging
        logger.info(f"🔧 TOOL CALL: ===== STREAMED TOOL EXECUTION START =====")
        logger.info(f"🔧 TOOL CALL: Function: {function_name}")
        logger.info(f"🔧 TOOL CALL: Call ID: {call_id}")
        logger.info(f"🔧 TOOL CALL: Arguments JSON: {arguments_json}")
        logger.info(f"🔧 TOOL CALL: Timestamp: {datetime.now().isoformat()}")

        # Send a quick "holding" response without injecting an assistant message item
        await self.send_to_model({
            "type": "response.create",
            "response": {
                "modalities": ["audio", "text"],
                "instructions": "One moment while I check that for you..."
            }
        })
        logger.info(f"🔧 TOOL CALL: Sent holding response to user")

        try:
            # Parse arguments with enhanced error handling
            try:
                args = json.loads(arguments_json or "{}")
                logger.info(f"🔧 TOOL CALL: Parsed Arguments: {json.dumps(args, indent=2)}")
            except json.JSONDecodeError as e:
                logger.error(f"🔧 TOOL CALL: JSON Parse Error: {e}")
                logger.error(f"🔧 TOOL CALL: Invalid JSON: {arguments_json}")
                args = {}
                logger.warning(f"🔧 TOOL CALL: Using empty dict as fallback")
            
            # Execute the tool with enhanced logging
            logger.info(f"🔧 TOOL CALL: Starting tool execution...")
            result = await execute_tool(function_name, args)
            
            # Enhanced result logging
            logger.info(f"🔧 TOOL CALL: ===== STREAMED TOOL EXECUTION COMPLETED =====")
            logger.info(f"🔧 TOOL CALL: Function: {function_name}")
            logger.info(f"🔧 TOOL CALL: Success: True")
            if isinstance(result, dict):
                logger.info(f"🔧 TOOL CALL: Result Type: Dict")
                logger.info(f"🔧 TOOL CALL: Result Keys: {list(result.keys())}")
                if 'error' in result:
                    logger.error(f"🔧 TOOL CALL: Tool returned error: {result['error']}")
                else:
                    logger.info(f"🔧 TOOL CALL: Result: {json.dumps(result, indent=2)}")
            else:
                logger.info(f"🔧 TOOL CALL: Result Type: {type(result).__name__}")
                logger.info(f"🔧 TOOL CALL: Result: {str(result)}")

            # Step 1: Attach tool result to conversation
            logger.info(f"🔧 TOOL CALL: Attaching result to conversation...")
            await self.send_to_model({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result) if not isinstance(result, str) else result
                }
            })
            logger.info(f"🔧 TOOL CALL: Result attached to conversation")

            # Step 2: Explicitly ask the model to speak about it
            logger.info(f"🔧 TOOL CALL: Triggering response generation...")
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
            logger.info(f"🔧 TOOL CALL: Response generation triggered for {function_name}")

        except Exception as e:
            # Enhanced error logging
            logger.error(f"🔧 TOOL CALL: ===== STREAMED TOOL EXECUTION FAILED =====")
            logger.error(f"🔧 TOOL CALL: Function: {function_name}")
            logger.error(f"🔧 TOOL CALL: Call ID: {call_id}")
            logger.error(f"🔧 TOOL CALL: Error Type: {type(e).__name__}")
            logger.error(f"🔧 TOOL CALL: Error Message: {str(e)}")
            logger.error(f"🔧 TOOL CALL: Arguments JSON: {arguments_json}")
            logger.error(f"🔧 TOOL CALL: Timestamp: {datetime.now().isoformat()}")
            
            # Send error result to model
            error_result = {
                "error": f"Tool execution failed: {str(e)}",
                "function_name": function_name,
                "call_id": call_id
            }
            
            try:
                await self.send_to_model({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(error_result)
                    }
                })
                
                await self.send_to_model({
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": "I encountered an error while processing your request. Please try again or ask something else."
                    }
                })
                logger.info(f"🔧 TOOL CALL: Error response sent to user")
            except Exception as response_error:
                logger.error(f"🔧 TOOL CALL: Failed to send error response: {response_error}")

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
    
    @database_sync_to_async
    def _determine_call_direction_async(self, caller_number: str, called_number: str) -> str:
        """Determine call direction using async database query"""
        from .models import PhoneNumber
        
        # Check if called_number belongs to our user (incoming call)
        user_phone = PhoneNumber.objects.filter(
            phone_number=called_number,
            user=self.agent_config.user,
            is_active=True
        ).first()
        if user_phone:
            logger.info(f"📞 Call direction: INCOMING (customer {caller_number} called our number {called_number})")
            return "incoming"
        
        # Check if caller_number belongs to our user (outgoing call)
        user_phone = PhoneNumber.objects.filter(
            phone_number=caller_number,
            user=self.agent_config.user,
            is_active=True
        ).first()
        if user_phone:
            logger.info(f"📞 Call direction: OUTGOING (we called customer {called_number} from our number {caller_number})")
            return "outgoing"
        
        # Default to incoming if neither number is found
        logger.warning(f"📞 Could not determine call direction for caller {caller_number} and called {called_number}")
        return "incoming"
    
    def update_activity(self) -> None:
        """Update the last activity time"""
        self.last_activity_time = asyncio.get_event_loop().time()
        
        # Cancel existing timeout task and start a new one
        if self.idle_timeout_task:
            self.idle_timeout_task.cancel()
        
        # Start new timeout task if timeout is enabled
        if self.idle_timeout_seconds > 0:
            self.idle_timeout_task = asyncio.create_task(self._idle_timeout_handler())
    
    async def _idle_timeout_handler(self) -> None:
        """Handle idle timeout - disconnect the call after idle period"""
        try:
            await asyncio.sleep(self.idle_timeout_seconds)
            
            # Check if we're still idle
            current_time = asyncio.get_event_loop().time()
            idle_duration = current_time - self.last_activity_time
            
            if idle_duration >= self.idle_timeout_seconds:
                logger.info(f"⏰ Session {self.session_id[:8]}... timed out after {idle_duration:.1f} seconds of inactivity")
                
                # Send timeout message to caller
                await self._send_timeout_message()
                
                # Disconnect the call
                await self._disconnect_call()
                
        except asyncio.CancelledError:
            # Task was cancelled (activity detected), this is normal
            pass
        except Exception as e:
            logger.error(f"Error in idle timeout handler: {e}")
    
    async def _send_timeout_message(self) -> None:
        """Send a timeout message to the caller"""
        try:
            timeout_message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "The call has been idle for too long and will be disconnected."
                        }
                    ]
                }
            }
            
            await self.send_to_model(timeout_message)
            
            # Create a response
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Inform the caller that the call is being disconnected due to inactivity. Be polite and brief."
                }
            }
            
            await self.send_to_model(response_create)
            
        except Exception as e:
            logger.error(f"Error sending timeout message: {e}")
    
    async def _disconnect_call(self) -> None:
        """Disconnect the call"""
        try:
            # Update database session status
            if hasattr(self, 'call_session') and self.call_session:
                from .consumers import RealtimeConsumer
                # We need to access the consumer to update the database
                if self.twilio_conn and hasattr(self.twilio_conn, 'update_session_status'):
                    await self.twilio_conn.update_session_status('ended')
            
            # Clean up connections
            await self.cleanup_all_connections()
            
            # Remove from session manager
            if hasattr(session_manager, 'remove_session'):
                session_manager.remove_session(self.session_id)
                
        except Exception as e:
            logger.error(f"Error disconnecting call: {e}")
    
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