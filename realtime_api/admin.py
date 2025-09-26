from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django import forms
from .models import AgentConfiguration, CallSession, UserProfile, PhoneNumber, InstructionTemplate, Conversation, Event, Turn

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

@admin.register(InstructionTemplate)
class InstructionTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'instructions')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Template Info', {
            'fields': ('name', 'category', 'description', 'is_active')
        }),
        ('Instructions', {
            'fields': ('instructions',),
            'description': 'Use {name} as a placeholder for the agent name. Example: "Your name is **{name}**."'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "instructions":
            kwargs["widget"] = forms.Textarea(attrs={
                'rows': 20,
                'cols': 100,
                'placeholder': 'Enter instructions template with {name} placeholders...'
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)


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
            'fields': ('user', 'name', 'instruction_template', 'instructions', 'is_active'),
            'description': 'Select a template or use custom instructions. Template will override custom instructions if selected.'
        }),
        ('Voice Settings', {
            'fields': ('voice', 'temperature', 'max_response_output_tokens'),
            'description': 'Temperature must be between 0.6 and 1.2 for OpenAI Realtime API'
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
        ('MCP Server Integration', {
            'fields': ('mcp_tenant_id', 'mcp_auth_token'),
            'description': 'Configure Model Context Protocol (MCP) server connection for enhanced capabilities. When editing, leave auth token blank to keep existing value, or enter a new token to replace it.',
            'classes': ('collapse',)
        }),
        ('Agent Settings', {
            'fields': ('agent_timezone',),
            'description': 'Agent timezone for time awareness in conversations'
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
        """Automatically set user for new agents if not superuser and preserve MCP token"""
        if not change and not request.user.is_superuser:
            obj.user = request.user
        
        # Preserve MCP auth token if it's not being changed
        if change and hasattr(obj, 'mcp_auth_token'):
            # Get the original object from database
            try:
                original_obj = AgentConfiguration.objects.get(pk=obj.pk)
                # Check the form data for MCP token
                form_mcp_token = form.cleaned_data.get('mcp_auth_token', '') or ''
                
                # If the form field is empty or just whitespace, preserve the original token
                if not form_mcp_token.strip() and original_obj.mcp_auth_token:
                    obj.mcp_auth_token = original_obj.mcp_auth_token
                    # Log that we're preserving the existing token
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Preserving existing MCP token for AgentConfiguration ID {obj.pk}")
            except AgentConfiguration.DoesNotExist:
                pass  # New object, no need to preserve
        
        super().save_model(request, obj, form, change)
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Customize form fields with advanced input controls"""
        if db_field.name == "temperature":
            # Temperature slider with value display
            kwargs["widget"] = forms.NumberInput(attrs={
                'type': 'range',
                'step': '0.1',
                'min': '0.6', 
                'max': '1.2',
                'class': 'temperature-slider slider-with-value',
                'oninput': 'updateSliderValue(this)',
                'data-suffix': ' (0.6=focused, 1.2=creative)'
            })
        elif db_field.name == "vad_threshold":
            # VAD threshold slider with value display
            kwargs["widget"] = forms.NumberInput(attrs={
                'type': 'range',
                'step': '0.1',
                'min': '0.0',
                'max': '1.0',
                'class': 'vad-slider slider-with-value',
                'oninput': 'updateSliderValue(this)',
                'data-suffix': ' (0.0=sensitive, 1.0=requires loud audio)'
            })
        elif db_field.name == "vad_silence_duration_ms":
            # Silence duration with validation
            kwargs["widget"] = forms.NumberInput(attrs={
                'step': '100',
                'min': '200',
                'max': '2000',
                'placeholder': '500ms (recommended)'
            })
        elif db_field.name == "max_response_output_tokens":
            # Max tokens with helpful placeholder
            kwargs["widget"] = forms.TextInput(attrs={
                'placeholder': 'inf (unlimited) or number like 500',
                'size': '30'
            })
        elif db_field.name == "instructions":
            # Larger textarea for instructions
            kwargs["widget"] = forms.Textarea(attrs={
                'rows': 4,
                'cols': 80,
                'placeholder': 'Describe how the AI agent should behave...'
            })
        elif db_field.name == "mcp_tenant_id":
            # MCP Tenant ID with helpful placeholder
            kwargs["widget"] = forms.TextInput(attrs={
                'placeholder': 'e.g., tenant-abc123 (optional)',
                'size': '40'
            })
        elif db_field.name == "mcp_auth_token":
            # MCP Auth Token as password field for security with better UX
            kwargs["widget"] = forms.PasswordInput(attrs={
                'placeholder': 'Enter new token or leave blank to keep existing',
                'size': '50',
                'render_value': False  # Never render the actual value for security
            })
        elif db_field.name == "agent_timezone":
            # Timezone field with helpful placeholder and common timezones
            kwargs["widget"] = forms.TextInput(attrs={
                'placeholder': 'e.g., America/New_York, Europe/London, UTC',
                'size': '40',
                'list': 'timezone-suggestions'
            })
        
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def get_form(self, request, obj=None, **kwargs):
        """Customize form for better MCP token handling"""
        form = super().get_form(request, obj, **kwargs)
        
        # For MCP auth token, add better help text when editing an existing object
        if obj and hasattr(obj, 'mcp_auth_token') and obj.mcp_auth_token:
            # Customize the form field help text for the MCP token
            form.base_fields['mcp_auth_token'].help_text = "A token is currently stored (displayed masked). Leave blank to keep existing token, or enter a new token to replace it."
        elif not obj:
            # For new objects
            form.base_fields['mcp_auth_token'].help_text = "Enter MCP authentication token"
        
        return form
    
    class Media:
        """Add custom CSS and JavaScript for enhanced admin interface"""
        css = {
            'all': ('admin/css/agent_admin.css',)
        }
        js = ('admin/js/agent_admin.js', 'admin/js/template_loader.js')

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'call_session', 'started_at', 'ended_at', 'turn_count', 'event_count', 'view_chat_history')
    list_filter = ('started_at', 'ended_at', 'call_session__agent_config')
    readonly_fields = ('started_at', 'ended_at', 'chat_history_link')
    
    fieldsets = (
        ('Conversation Info', {
            'fields': ('call_session', 'started_at', 'ended_at', 'metadata')
        }),
        ('Chat History', {
            'fields': ('chat_history_link',),
            'description': 'View the complete conversation history for this call session'
        }),
    )
    
    def turn_count(self, obj):
        return obj.turns.count()
    turn_count.short_description = 'Turns'
    
    def event_count(self, obj):
        return obj.events.count()
    event_count.short_description = 'Events'
    
    def view_chat_history(self, obj):
        """Display a link to view chat history"""
        from django.urls import reverse
        from django.utils.html import format_html
        
        if obj.call_session and obj.call_session.session_id:
            url = reverse('chat_history', args=[obj.call_session.session_id])
            return format_html(
                '<a href="{}" target="_blank" style="background: #4f46e5; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 600;">📞 View Chat History</a>',
                url
            )
        return "No session"
    view_chat_history.short_description = 'Chat History'
    view_chat_history.allow_tags = True
    
    def chat_history_link(self, obj):
        """Display chat history link in detail view"""
        return self.view_chat_history(obj)
    chat_history_link.short_description = 'Chat History Link'
    chat_history_link.allow_tags = True


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'role', 'text_preview', 'started_at', 'completed_at', 'view_chat_history')
    list_filter = ('role', 'started_at', 'conversation__call_session__agent_config')
    readonly_fields = ('started_at', 'completed_at', 'chat_history_link')
    
    fieldsets = (
        ('Turn Info', {
            'fields': ('conversation', 'role', 'text', 'audio_url', 'meta')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at')
        }),
        ('Chat History', {
            'fields': ('chat_history_link',),
            'description': 'View the complete conversation history for this call session'
        }),
    )
    
    def text_preview(self, obj):
        return obj.text[:100] + "..." if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Message'
    
    def view_chat_history(self, obj):
        """Display a link to view chat history"""
        from django.urls import reverse
        from django.utils.html import format_html
        
        if obj.conversation and obj.conversation.call_session and obj.conversation.call_session.session_id:
            url = reverse('chat_history', args=[obj.conversation.call_session.session_id])
            return format_html(
                '<a href="{}" target="_blank" style="background: #4f46e5; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 600;">📞 View Chat History</a>',
                url
            )
        return "No session"
    view_chat_history.short_description = 'Chat History'
    view_chat_history.allow_tags = True
    
    def chat_history_link(self, obj):
        """Display chat history link in detail view"""
        return self.view_chat_history(obj)
    chat_history_link.short_description = 'Chat History Link'
    chat_history_link.allow_tags = True


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'event_type', 'role', 'text_delta_preview', 'created_at')
    list_filter = ('event_type', 'role', 'created_at')
    readonly_fields = ('created_at',)
    
    def text_delta_preview(self, obj):
        return obj.text_delta[:50] + "..." if len(obj.text_delta) > 50 else obj.text_delta
    text_delta_preview.short_description = 'Text Delta'


@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'caller_number', 'called_number', 'phone_number', 'status', 'agent_config', 'call_start_time', 'call_duration_seconds', 'view_chat_history')
    list_filter = ('status', 'phone_number__user', 'agent_config', 'call_start_time')
    search_fields = ('session_id', 'twilio_call_sid', 'caller_number', 'called_number')
    readonly_fields = ('session_id', 'call_start_time', 'call_end_time', 'call_duration_seconds', 'chat_history_link')
    
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
        ('Chat History', {
            'fields': ('chat_history_link',),
            'description': 'View the complete conversation history for this call session'
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
    
    def view_chat_history(self, obj):
        """Display a link to view chat history"""
        from django.urls import reverse
        from django.utils.html import format_html
        
        if obj.session_id:
            url = reverse('chat_history', args=[obj.session_id])
            return format_html(
                '<a href="{}" target="_blank" style="background: #4f46e5; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 600;">📞 View Chat History</a>',
                url
            )
        return "No session ID"
    view_chat_history.short_description = 'Chat History'
    view_chat_history.allow_tags = True
    
    def chat_history_link(self, obj):
        """Display chat history link in detail view"""
        return self.view_chat_history(obj)
    chat_history_link.short_description = 'Chat History Link'
    chat_history_link.allow_tags = True
