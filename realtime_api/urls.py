from django.urls import path
from . import views

urlpatterns = [
    # Twilio endpoints
    path('webhook/', views.twilio_webhook, name='twilio_webhook'),
    path('twiml/', views.twilio_webhook, name='twilio_twiml'),  # Alternative endpoint name
    path('status/', views.twilio_status_callback, name='twilio_status_callback'),
    
    # API endpoints
    path('health/', views.health_check, name='health_check'),
    path('test/', views.health_check, name='test_endpoint'),  # Simple test
    path('tools/', views.get_tools, name='get_tools'),
    path('public-url/', views.get_public_url, name='get_public_url'),
    path('template-instructions/', views.get_template_instructions, name='get_template_instructions'),
    path('conversation-history/<str:session_id>/', views.conversation_history, name='conversation_history'),
    path('conversation-events/<str:session_id>/', views.conversation_events, name='conversation_events'),
    
    # Chat history template
    path('chat-history/<str:session_id>/', views.chat_history_view, name='chat_history'),
]
