"""
Conversation History Tracking for OpenAI Realtime API
====================================================

This module handles the ingestion and reconstruction of conversation turns
from the OpenAI Realtime API event stream.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from asgiref.sync import sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class TurnBuilder:
    """Builds complete conversation turns from streaming events"""
    
    def __init__(self):
        self.assistant_buffers: Dict[str, List[str]] = {}  # response_id -> list[text_deltas]
        self.user_buffers: Dict[str, List[str]] = {}       # item_id -> list[transcript_parts]
        self.response_metadata: Dict[str, dict] = {}       # response_id -> metadata
        self.user_metadata: Dict[str, dict] = {}           # item_id -> metadata

    def add_assistant_delta(self, response_id: str, text_delta: str, metadata: dict = None):
        """Add a text delta to an assistant response"""
        self.assistant_buffers.setdefault(response_id, []).append(text_delta)
        if metadata:
            self.response_metadata[response_id] = metadata

    def add_user_transcript_delta(self, item_id: str, text: str, metadata: dict = None):
        """Add transcript text for a user message"""
        self.user_buffers.setdefault(item_id, []).append(text)
        if metadata:
            self.user_metadata[item_id] = metadata

    @sync_to_async
    def finalize_assistant_turn(self, conversation, response_id: str):
        """Create a complete assistant turn from accumulated deltas"""
        from .models import Turn
        
        text_parts = self.assistant_buffers.pop(response_id, [])
        metadata = self.response_metadata.pop(response_id, {})
        
        if not text_parts:
            logger.warning(f"No text deltas found for response {response_id}")
            return None
        
        complete_text = "".join(text_parts)
        
        turn = Turn.objects.create(
            conversation=conversation,
            role="assistant",
            text=complete_text,
            meta=metadata,
            completed_at=timezone.now()
        )
        
        logger.info(f"🤖 Finalized assistant turn: {complete_text[:50]}...")
        return turn

    @sync_to_async
    def finalize_user_turn(self, conversation, item_id: str):
        """Create a complete user turn from transcript"""
        from .models import Turn
        
        text_parts = self.user_buffers.pop(item_id, [])
        metadata = self.user_metadata.pop(item_id, {})
        
        if not text_parts:
            logger.warning(f"No transcript found for item {item_id}")
            return None
        
        complete_text = "".join(text_parts)
        
        turn = Turn.objects.create(
            conversation=conversation,
            role="user", 
            text=complete_text,
            meta=metadata,
            completed_at=timezone.now()
        )
        
        logger.info(f"👤 Finalized user turn: {complete_text[:50]}...")
        return turn

    @sync_to_async
    def create_error_turn(self, conversation, item_id: str, error_message: str):
        """Create a turn for failed transcription"""
        from .models import Turn
        
        turn = Turn.objects.create(
            conversation=conversation,
            role="user",
            text="",
            meta={
                "item_id": item_id,
                "error": error_message,
                "transcription_failed": True
            },
            completed_at=timezone.now()
        )
        
        logger.warning(f"❌ Created error turn for failed transcription: {error_message}")
        return turn


class ConversationTracker:
    """Tracks and persists OpenAI Realtime API events and conversations"""
    
    def __init__(self):
        self.turn_builder = TurnBuilder()
        self.conversations: Dict[str, int] = {}  # session_id -> conversation_id

    @sync_to_async
    def get_or_create_conversation(self, call_session):
        """Get or create a conversation for the call session"""
        from .models import Conversation
        
        conversation, created = Conversation.objects.get_or_create(
            call_session=call_session,
            defaults={
                'metadata': {
                    'agent_name': call_session.agent_config.name if call_session.agent_config else None,
                    'phone_number': call_session.called_number,
                    'caller_number': call_session.caller_number
                }
            }
        )
        
        if created:
            logger.info(f"📝 Created new conversation {conversation.id} for session {call_session.session_id[:8]}...")
        
        return conversation

    @sync_to_async
    def save_event(self, conversation, event_data: dict):
        """Save a raw OpenAI event to the database"""
        from .models import Event
        
        # Extract key fields from event
        event_type = event_data.get("type", "")
        event_id = event_data.get("id", "")
        item_id = ""
        response_id = ""
        role = ""
        text_delta = ""
        error_msg = ""
        
        # Extract item_id from various event structures
        if "item" in event_data:
            if isinstance(event_data["item"], dict):
                item_id = event_data["item"].get("id", "")
                role = event_data["item"].get("role", "")
            else:
                item_id = str(event_data["item"])
        
        # Extract response_id
        if "response" in event_data:
            if isinstance(event_data["response"], dict):
                response_id = event_data["response"].get("id", "")
                role = role or event_data["response"].get("role", "")
            else:
                response_id = str(event_data["response"])
        
        response_id = response_id or event_data.get("response_id", "")
        
        # Extract text content
        text_delta = event_data.get("delta", "") or event_data.get("text", "") or event_data.get("transcript", "")
        
        # Extract error information
        if "error" in event_data:
            error_info = event_data["error"]
            if isinstance(error_info, dict):
                error_msg = error_info.get("message", str(error_info))
            else:
                error_msg = str(error_info)
        
        event = Event.objects.create(
            conversation=conversation,
            event_type=event_type,
            event_id=event_id,
            item_id=item_id,
            response_id=response_id,
            role=role,
            payload=event_data,
            text_delta=text_delta,
            error=error_msg
        )
        
        return event

    async def handle_realtime_event(self, conversation, event_data: dict):
        """Process a single OpenAI Realtime API event"""
        try:
            # Save raw event first
            event = await self.save_event(conversation, event_data)
            
            event_type = event_data.get("type", "")
            
            # Handle different event types
            if event_type == "response.output_text.delta":
                # Assistant text streaming
                response_id = event_data.get("response", {}).get("id", "")
                delta = event_data.get("delta", "")
                if response_id and delta:
                    self.turn_builder.add_assistant_delta(
                        response_id, 
                        delta, 
                        {"response": event_data.get("response", {})}
                    )
                    
            elif event_type in ("response.output_text.done", "response.done", "response.completed"):
                # Finalize assistant turn
                response_id = event_data.get("response", {}).get("id", "")
                if response_id:
                    await self.turn_builder.finalize_assistant_turn(conversation, response_id)
                    
            elif event_type == "conversation.item.input_audio_transcription.completed":
                # User speech transcript completed
                item_id = event_data.get("item_id", "")
                transcript = event_data.get("transcript", "")
                if item_id and transcript:
                    self.turn_builder.add_user_transcript_delta(
                        item_id,
                        transcript,
                        {"item": event_data.get("item", {})}
                    )
                    await self.turn_builder.finalize_user_turn(conversation, item_id)
                    
            elif event_type == "conversation.item.input_audio_transcription.failed":
                # Transcript failure
                item_id = event_data.get("item_id", "")
                error_message = event_data.get("error", {}).get("message", "Transcription failed")
                if item_id:
                    await self.turn_builder.create_error_turn(conversation, item_id, error_message)
            
            logger.debug(f"📝 Processed event: {event_type}")
            
        except Exception as e:
            logger.error(f"Error handling realtime event {event_type}: {e}")


# Global conversation tracker instance
conversation_tracker = ConversationTracker()
