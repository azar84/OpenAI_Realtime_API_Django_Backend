from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import json

class UserProfile(models.Model):
    """Extended user profile with OpenAI API key"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    openai_api_key = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="Your OpenAI API key (starts with sk-)"
    )
    twilio_account_sid = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Your Twilio Account SID (optional, falls back to system default)"
    )
    twilio_auth_token = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Your Twilio Auth Token (optional, falls back to system default)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def clean(self):
        """Validate API key format"""
        if self.openai_api_key and not self.openai_api_key.startswith('sk-'):
            raise ValidationError({'openai_api_key': 'OpenAI API key must start with "sk-"'})
    
    def has_valid_openai_key(self):
        """Check if user has a valid OpenAI API key"""
        return bool(self.openai_api_key and self.openai_api_key.startswith('sk-'))

class PhoneNumber(models.Model):
    """Maps Twilio phone numbers to users and their agents"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='phone_numbers')
    phone_number = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Twilio phone number (e.g., +1234567890)"
    )
    twilio_phone_number_sid = models.CharField(
        max_length=100,
        unique=True,
        help_text="Twilio Phone Number SID (starts with PN)"
    )
    agent_config = models.ForeignKey(
        'AgentConfiguration', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='phone_numbers',
        help_text="Agent to use for calls to this number (uses user's default if not set)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Phone Number"
        verbose_name_plural = "Phone Numbers"
    
    def __str__(self):
        return f"{self.phone_number} → {self.user.username}"
    
    def clean(self):
        """Validate phone number and SID format"""
        if not self.phone_number.startswith('+'):
            raise ValidationError({'phone_number': 'Phone number must start with "+" (e.g., +1234567890)'})
        
        if self.twilio_phone_number_sid and not self.twilio_phone_number_sid.startswith('PN'):
            raise ValidationError({'twilio_phone_number_sid': 'Twilio Phone Number SID must start with "PN"'})
    
    def get_agent_config(self):
        """Get the agent configuration for this phone number"""
        if self.agent_config:
            return self.agent_config
        
        # Fallback to user's first active agent
        return self.user.agents.filter(is_active=True).first()

class InstructionTemplate(models.Model):
    """Templates for agent instructions that can be reused"""
    name = models.CharField(max_length=100, help_text="Template name (e.g., 'Sales Caller', 'Customer Support')")
    description = models.TextField(blank=True, help_text="Brief description of what this template is for")
    instructions = models.TextField(help_text="Template instructions with {name} placeholders")
    category = models.CharField(
        max_length=50,
        choices=[
            ('sales', 'Sales & Marketing'),
            ('support', 'Customer Support'),
            ('assistant', 'General Assistant'),
            ('custom', 'Custom'),
        ],
        default='custom'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'name']
        
    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"
    
    def get_formatted_instructions(self, agent_name):
        """Format instructions with the given agent name"""
        return self.instructions.format(name=agent_name)


class AgentConfiguration(models.Model):
    """Configuration for AI agents"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agents')
    name = models.CharField(max_length=100)
    instruction_template = models.ForeignKey(
        InstructionTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Select a template for instructions (optional - will use custom instructions if not selected)"
    )
    instructions = models.TextField(
        blank=True,
        default="You are a helpful AI assistant named {name}. You can respond with both text and audio. Keep responses concise and natural.",
        help_text="Instructions for the AI agent. Use {name} as a placeholder for the agent's name. Select a template above to populate this field, then customize as needed."
    )
    voice = models.CharField(
        max_length=20, 
        choices=[
            ('alloy', 'Alloy'),
            ('ash', 'Ash'),
            ('ballad', 'Ballad'),
            ('cedar', 'Cedar'),
            ('coral', 'Coral'),
            ('echo', 'Echo'),
            ('marin', 'Marin'),
            ('sage', 'Sage'),
            ('shimmer', 'Shimmer'),
            ('verse', 'Verse'),
        ],
        default='alloy'
    )
    temperature = models.FloatField(default=0.8, help_text="Temperature for response generation (0.6-1.2)")
    max_response_output_tokens = models.CharField(max_length=10, default="inf")
    
    # Model selection
    model = models.CharField(
        max_length=50,
        choices=[
            ('gpt-4o-realtime-preview', 'gpt-4o-realtime-preview'),
            ('gpt-realtime-2025-08-28', 'gpt-realtime-2025-08-28'),
            ('gpt-realtime', 'gpt-realtime'),
            ('gpt-4o-realtime-preview-2025-06-03', 'gpt-4o-realtime-preview-2025-06-03'),
            ('gpt-4o-realtime-preview-2024-12-17', 'gpt-4o-realtime-preview-2024-12-17'),
            ('gpt-4o-realtime-preview-2024-10-01', 'gpt-4o-realtime-preview-2024-10-01'),
            ('gpt-4o-mini-realtime-preview-2024-12-17', 'gpt-4o-mini-realtime-preview-2024-12-17'),
            ('gpt-4o-mini-realtime-preview', 'gpt-4o-mini-realtime-preview'),
        ],
        default='gpt-realtime',
        help_text="Choose the OpenAI Realtime model for this agent"
    )
    
    # Audio settings
    input_audio_format = models.CharField(max_length=20, default="g711_ulaw")
    output_audio_format = models.CharField(max_length=20, default="g711_ulaw")
    
    # VAD settings
    vad_type = models.CharField(
        max_length=20,
        choices=[
            ('server_vad', 'Server VAD (silence-based)'),
            ('semantic_vad', 'Semantic VAD (context-based)'),
        ],
        default='server_vad',
        help_text="Voice activity detection mode"
    )
    
    # Server VAD settings (used when vad_type = 'server_vad')
    vad_threshold = models.FloatField(
        default=0.5,
        help_text="Activation threshold (0-1). Higher = requires louder audio, better for noisy environments"
    )
    vad_prefix_padding_ms = models.IntegerField(
        default=300,
        help_text="Audio to include before detected speech (milliseconds)"
    )
    vad_silence_duration_ms = models.IntegerField(
        default=500,
        help_text="Silence duration to detect speech stop (milliseconds). Shorter = faster turn detection"
    )
    
    # Semantic VAD settings (used when vad_type = 'semantic_vad')
    vad_eagerness = models.CharField(
        max_length=10,
        choices=[
            ('low', 'Low - Let user take their time'),
            ('medium', 'Medium - Balanced (default)'),
            ('high', 'High - Interrupt as soon as possible'),
            ('auto', 'Auto - Same as medium'),
        ],
        default='auto',
        help_text="How eager the model is to interrupt the user (semantic VAD only)"
    )
    
    # Transcription settings
    enable_input_transcription = models.BooleanField(default=True)
    transcription_model = models.CharField(
        max_length=50, 
        choices=[
            ('whisper-1', 'Whisper-1'),
            ('gpt-4o-mini-transcribe', 'GPT-4o Mini Transcribe'),
            ('gpt-4o-transcribe', 'GPT-4o Transcribe'),
        ],
        default="whisper-1",
        help_text="Choose the transcription model for speech-to-text"
    )
    
    # MCP (Model Context Protocol) Server Integration
    mcp_tenant_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Tenant ID for MCP server authentication (optional)"
    )
    mcp_auth_token = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Authentication token for MCP server (optional, will be encrypted)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    class Meta:
        unique_together = ['user', 'name']
    
    def clean(self):
        """Validate agent configuration fields"""
        super().clean()
        
        # Validate temperature range for OpenAI Realtime API
        if not (0.6 <= self.temperature <= 1.2):
            raise ValidationError({'temperature': 'Temperature must be between 0.6 and 1.2 for OpenAI Realtime API'})  # Each user can have unique agent names
    
    def get_user_api_key(self):
        """Get the user's OpenAI API key from their profile, fallback to system default"""
        from django.conf import settings
        
        # Simple path: User → Profile → API Key
        try:
            user_profile = self.user.profile
            if user_profile.has_valid_openai_key():
                return user_profile.openai_api_key
        except UserProfile.DoesNotExist:
            pass
        except Exception:
            pass
        
        # Fallback to system default
        return settings.OPENAI_API_KEY
    
    def get_formatted_instructions(self):
        """Get instructions with agent name substituted"""
        # Always use the instructions field (which may have been populated from a template)
        return self.instructions.format(name=self.name)
    
    def get_mcp_config(self):
        """Get MCP server configuration if available"""
        if self.mcp_tenant_id and self.mcp_auth_token:
            return {
                "tenant_id": self.mcp_tenant_id,
                "auth_token": self.mcp_auth_token
            }
        return None
    
    def has_mcp_integration(self):
        """Check if this agent has MCP server integration configured"""
        return bool(self.mcp_tenant_id and self.mcp_auth_token)
    
    def to_openai_config(self):
        """Convert to OpenAI session configuration format"""
        config = {
            "modalities": ["text", "audio"],
            "instructions": self.get_formatted_instructions(),
            "voice": self.voice,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "temperature": self.temperature,
            "tools": [],
            "tool_choice": "auto"
        }
        
        # Handle max_response_output_tokens properly
        if self.max_response_output_tokens and self.max_response_output_tokens.lower() != 'inf':
            try:
                # Convert to integer if it's a valid number
                config["max_response_output_tokens"] = int(self.max_response_output_tokens)
            except ValueError:
                # If it's not a valid number, omit the field (unlimited)
                pass
        # If it's "inf" or empty, omit the field to allow unlimited tokens
        
        # Configure turn detection based on VAD type
        if self.vad_type == 'semantic_vad':
            config["turn_detection"] = {
                "type": "semantic_vad",
                "eagerness": self.vad_eagerness,
                "create_response": True,
                "interrupt_response": True
            }
        else:  # server_vad (default)
            config["turn_detection"] = {
                "type": "server_vad",
                "threshold": self.vad_threshold,
                "prefix_padding_ms": self.vad_prefix_padding_ms,
                "silence_duration_ms": self.vad_silence_duration_ms,
                "create_response": True,
                "interrupt_response": True
            }
        
        if self.enable_input_transcription:
            config["input_audio_transcription"] = {
                "model": self.transcription_model
            }
            
        return config

class Conversation(models.Model):
    """A conversation within a call session"""
    call_session = models.ForeignKey('CallSession', on_delete=models.CASCADE, related_name='conversations')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"Conversation {self.id} - {self.call_session.session_id[:8]}..."


class Event(models.Model):
    """Raw OpenAI Realtime API events for audit trail"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=80, help_text="e.g., response.output_text.delta")
    event_id = models.CharField(max_length=128, blank=True, help_text="Server-assigned event ID")
    item_id = models.CharField(max_length=128, blank=True, help_text="Conversation item ID")
    response_id = models.CharField(max_length=128, blank=True, help_text="Response ID for grouping deltas")
    role = models.CharField(max_length=16, blank=True, help_text="user | assistant")
    payload = models.JSONField(default=dict, help_text="Raw event data")
    text_delta = models.TextField(blank=True, help_text="Text content for accumulation")
    error = models.TextField(blank=True, help_text="Error message if applicable")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'event_type']),
            models.Index(fields=['conversation', 'response_id']),
            models.Index(fields=['conversation', 'item_id']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.created_at}"


class Turn(models.Model):
    """Complete user or assistant message (materialized from events)"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="turns")
    role = models.CharField(max_length=16, choices=[('user', 'User'), ('assistant', 'Assistant')])
    text = models.TextField(blank=True, help_text="Complete message text")
    audio_url = models.URLField(blank=True, help_text="URL to audio file if persisted")
    meta = models.JSONField(default=dict, blank=True, help_text="Additional metadata")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['started_at']
    
    def __str__(self):
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"{self.role}: {preview}"


class CallSession(models.Model):
    """Track call sessions"""
    session_id = models.CharField(max_length=100, unique=True)
    twilio_call_sid = models.CharField(max_length=100, null=True, blank=True)
    twilio_stream_sid = models.CharField(max_length=100, null=True, blank=True)
    agent_config = models.ForeignKey(AgentConfiguration, on_delete=models.CASCADE, null=True, blank=True)
    phone_number = models.ForeignKey(PhoneNumber, on_delete=models.SET_NULL, null=True, blank=True, related_name='call_sessions')
    
    # Call metadata
    caller_number = models.CharField(max_length=20, null=True, blank=True)
    called_number = models.CharField(max_length=20, null=True, blank=True)
    call_start_time = models.DateTimeField(auto_now_add=True)
    call_end_time = models.DateTimeField(null=True, blank=True)
    call_duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Session status
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('connected', 'Connected'),
        ('ended', 'Ended'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    
    # Conversation log (optional - for debugging/analytics)
    conversation_log = models.JSONField(default=list, blank=True)
    
    def __str__(self):
        return f"Session {self.session_id} - {self.status}"
    
    def add_to_conversation_log(self, message_type, content, timestamp=None):
        """Add a message to the conversation log"""
        from django.utils import timezone
        
        if timestamp is None:
            timestamp = timezone.now().isoformat()
            
        log_entry = {
            "type": message_type,
            "content": content,
            "timestamp": timestamp
        }
        
        self.conversation_log.append(log_entry)
        self.save(update_fields=['conversation_log'])

# Signal to automatically create UserProfile when User is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)