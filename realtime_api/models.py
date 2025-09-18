from django.db import models
import json

class AgentConfiguration(models.Model):
    """Configuration for AI agents"""
    name = models.CharField(max_length=100, unique=True)
    instructions = models.TextField(
        default="You are a helpful AI assistant. You can respond with both text and audio. Keep responses concise and natural."
    )
    voice = models.CharField(
        max_length=20, 
        choices=[
            ('alloy', 'Alloy'),
            ('echo', 'Echo'),
            ('fable', 'Fable'),
            ('onyx', 'Onyx'),
            ('nova', 'Nova'),
            ('shimmer', 'Shimmer'),
        ],
        default='alloy'
    )
    temperature = models.FloatField(default=0.8)
    max_response_output_tokens = models.CharField(max_length=10, default="inf")
    
    # Audio settings
    input_audio_format = models.CharField(max_length=20, default="pcm16")
    output_audio_format = models.CharField(max_length=20, default="pcm16")
    
    # VAD settings
    vad_threshold = models.FloatField(default=0.5)
    vad_prefix_padding_ms = models.IntegerField(default=300)
    vad_silence_duration_ms = models.IntegerField(default=200)
    
    # Transcription settings
    enable_input_transcription = models.BooleanField(default=True)
    transcription_model = models.CharField(max_length=50, default="whisper-1")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name
    
    def to_openai_config(self):
        """Convert to OpenAI session configuration format"""
        config = {
            "modalities": ["text", "audio"],
            "instructions": self.instructions,
            "voice": self.voice,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "temperature": self.temperature,
            "max_response_output_tokens": self.max_response_output_tokens,
            "turn_detection": {
                "type": "server_vad",
                "threshold": self.vad_threshold,
                "prefix_padding_ms": self.vad_prefix_padding_ms,
                "silence_duration_ms": self.vad_silence_duration_ms
            },
            "tools": [],
            "tool_choice": "auto"
        }
        
        if self.enable_input_transcription:
            config["input_audio_transcription"] = {
                "model": self.transcription_model
            }
            
        return config

class CallSession(models.Model):
    """Track call sessions"""
    session_id = models.CharField(max_length=100, unique=True)
    twilio_call_sid = models.CharField(max_length=100, null=True, blank=True)
    twilio_stream_sid = models.CharField(max_length=100, null=True, blank=True)
    agent_config = models.ForeignKey(AgentConfiguration, on_delete=models.CASCADE, null=True, blank=True)
    
    # Call metadata
    caller_number = models.CharField(max_length=20, null=True, blank=True)
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