from django.contrib import admin
from .models import AgentConfiguration, CallSession

@admin.register(AgentConfiguration)
class AgentConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'voice', 'temperature', 'is_active', 'created_at')
    list_filter = ('voice', 'is_active', 'created_at')
    search_fields = ('name', 'instructions')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Configuration', {
            'fields': ('name', 'instructions', 'is_active')
        }),
        ('Voice Settings', {
            'fields': ('voice', 'temperature', 'max_response_output_tokens')
        }),
        ('Audio Settings', {
            'fields': ('input_audio_format', 'output_audio_format')
        }),
        ('Voice Activity Detection', {
            'fields': ('vad_threshold', 'vad_prefix_padding_ms', 'vad_silence_duration_ms')
        }),
        ('Transcription', {
            'fields': ('enable_input_transcription', 'transcription_model')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'caller_number', 'status', 'agent_config', 'call_start_time', 'call_duration_seconds')
    list_filter = ('status', 'agent_config', 'call_start_time')
    search_fields = ('session_id', 'twilio_call_sid', 'caller_number')
    readonly_fields = ('session_id', 'call_start_time', 'call_end_time', 'call_duration_seconds')
    
    fieldsets = (
        ('Session Info', {
            'fields': ('session_id', 'status', 'agent_config')
        }),
        ('Twilio Info', {
            'fields': ('twilio_call_sid', 'twilio_stream_sid', 'caller_number')
        }),
        ('Call Timing', {
            'fields': ('call_start_time', 'call_end_time', 'call_duration_seconds')
        }),
        ('Conversation Log', {
            'fields': ('conversation_log',),
            'classes': ('collapse',)
        })
    )
