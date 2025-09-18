from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import AgentConfiguration, CallSession, UserProfile, PhoneNumber

# UserProfile inline admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('openai_api_key', 'twilio_account_sid', 'twilio_auth_token')
    extra = 0

# Extend User admin to include UserProfile
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = UserAdmin.list_display + ('has_openai_key', 'agent_count', 'phone_count')
    
    def has_openai_key(self, obj):
        """Check if user has OpenAI API key"""
        try:
            return obj.profile.has_valid_openai_key()
        except UserProfile.DoesNotExist:
            return False
    has_openai_key.boolean = True
    has_openai_key.short_description = 'Has OpenAI Key'
    
    def agent_count(self, obj):
        """Count of user's agents"""
        return obj.agents.count()
    agent_count.short_description = 'Agents'
    
    def phone_count(self, obj):
        """Count of user's phone numbers"""
        return obj.phone_numbers.count()
    phone_count.short_description = 'Phone Numbers'

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_valid_openai_key', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('API Keys', {
            'fields': ('openai_api_key', 'twilio_account_sid', 'twilio_auth_token'),
            'description': 'Enter your personal API keys. Leave blank to use system defaults.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Filter profiles to show only user's own profile (for non-superusers)"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'user', 'agent_config', 'is_active', 'created_at')
    list_filter = ('user', 'is_active', 'created_at')
    search_fields = ('phone_number', 'twilio_phone_number_sid', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Phone Number Info', {
            'fields': ('user', 'phone_number', 'twilio_phone_number_sid', 'is_active')
        }),
        ('Agent Assignment', {
            'fields': ('agent_config',),
            'description': 'Select which agent should handle calls to this number. Leave blank to use the user\'s default agent.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Filter phone numbers to show only user's own numbers (for non-superusers)"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit user and agent fields to current user's data for non-superusers"""
        if not request.user.is_superuser:
            if db_field.name == "user":
                kwargs["queryset"] = User.objects.filter(id=request.user.id)
                kwargs["initial"] = request.user.id
            elif db_field.name == "agent_config":
                kwargs["queryset"] = AgentConfiguration.objects.filter(user=request.user, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def save_model(self, request, obj, form, change):
        """Automatically set user for new phone numbers if not superuser"""
        if not change and not request.user.is_superuser:
            obj.user = request.user
        super().save_model(request, obj, form, change)

@admin.register(AgentConfiguration)
class AgentConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'voice', 'temperature', 'is_active', 'created_at')
    list_filter = ('user', 'voice', 'is_active', 'created_at')
    search_fields = ('name', 'instructions', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Configuration', {
            'fields': ('user', 'name', 'instructions', 'is_active')
        }),
        ('Voice Settings', {
            'fields': ('voice', 'temperature', 'max_response_output_tokens')
        }),
        ('Model Settings', {
            'fields': ('model',),
            'description': 'Choose the OpenAI Realtime model for this agent'
        }),
        ('Audio Settings', {
            'fields': ('input_audio_format', 'output_audio_format')
        }),
        ('Voice Activity Detection', {
            'fields': ('vad_type', 'vad_threshold', 'vad_prefix_padding_ms', 'vad_silence_duration_ms', 'vad_eagerness'),
            'description': 'Configure how the AI detects when you start/stop speaking'
        }),
        ('Transcription', {
            'fields': ('enable_input_transcription', 'transcription_model')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Filter agents to show only user's own agents (for non-superusers)"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit user field to current user for non-superusers"""
        if db_field.name == "user" and not request.user.is_superuser:
            kwargs["queryset"] = User.objects.filter(id=request.user.id)
            kwargs["initial"] = request.user.id
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def save_model(self, request, obj, form, change):
        """Automatically set user for new agents if not superuser"""
        if not change and not request.user.is_superuser:
            obj.user = request.user
        super().save_model(request, obj, form, change)

@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'caller_number', 'called_number', 'phone_number', 'status', 'agent_config', 'call_start_time', 'call_duration_seconds')
    list_filter = ('status', 'phone_number__user', 'agent_config', 'call_start_time')
    search_fields = ('session_id', 'twilio_call_sid', 'caller_number', 'called_number')
    readonly_fields = ('session_id', 'call_start_time', 'call_end_time', 'call_duration_seconds')
    
    fieldsets = (
        ('Session Info', {
            'fields': ('session_id', 'status', 'phone_number', 'agent_config')
        }),
        ('Twilio Info', {
            'fields': ('twilio_call_sid', 'twilio_stream_sid', 'caller_number', 'called_number')
        }),
        ('Call Timing', {
            'fields': ('call_start_time', 'call_end_time', 'call_duration_seconds')
        }),
        ('Conversation Log', {
            'fields': ('conversation_log',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Filter call sessions to show only user's phone number sessions (for non-superusers)"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(phone_number__user=request.user)
