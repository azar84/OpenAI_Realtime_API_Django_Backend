import uuid
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
# from twilio.twiml.voice_response import VoiceResponse  # Temporarily commented out
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def twilio_webhook(request):
    """Handle incoming Twilio calls and connect to WebSocket"""
    try:
        # Generate unique session ID for this call
        session_id = str(uuid.uuid4())
        
        # Get call information from Twilio
        call_sid = request.POST.get('CallSid', '')
        caller_number = request.POST.get('From', '')
        called_number = request.POST.get('To', '')
        
        # Build WebSocket URL dynamically
        # In production, replace with your actual domain
        host = request.get_host()
        # Use WSS for ngrok (HTTPS) and WS for local development
        is_secure = request.is_secure() or 'ngrok' in host
        protocol = 'wss' if is_secure else 'ws'
        websocket_url = f"{protocol}://{host}/ws/realtime/{session_id}/"
        
        # Create TwiML response that connects to our WebSocket
        twiml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Hello! You're now connected to an AI assistant. Please speak after the tone.</Say>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>'''
        
        logger.info(f"New call connected - CallSid: {call_sid}, From: {caller_number}, Session: {session_id}")
        
        return HttpResponse(twiml_response, content_type='text/xml')
        
    except Exception as e:
        logger.error(f"Error in Twilio webhook: {e}")
        
        # Fallback response
        fallback_response = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Sorry, there was an error connecting you to the assistant. Please try again later.</Say>
    <Hangup/>
</Response>'''
        
        return HttpResponse(fallback_response, content_type='text/xml')

@csrf_exempt
def twilio_status_callback(request):
    """Handle Twilio status callbacks"""
    call_status = request.POST.get('CallStatus')
    call_sid = request.POST.get('CallSid')
    
    logger.info(f"Call {call_sid} status: {call_status}")
    
    return HttpResponse("OK")

def health_check(request):
    """Simple health check endpoint"""
    return HttpResponse("OK")

@csrf_exempt
def get_tools(request):
    """Get available function tools for the AI agent"""
    # Example tools - you can expand this based on your needs
    tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        },
        {
            "type": "function", 
            "name": "get_time",
            "description": "Get current time",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]
    
    from django.http import JsonResponse
    return JsonResponse({"tools": tools})

def get_public_url(request):
    """Get the public URL for this server"""
    from django.http import JsonResponse
    
    # Build the public URL dynamically
    protocol = 'https' if request.is_secure() else 'http'
    host = request.get_host()
    public_url = f"{protocol}://{host}"
    
    return JsonResponse({"publicUrl": public_url})
