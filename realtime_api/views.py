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
    """Handle incoming Twilio calls and route to appropriate user's agent"""
    try:
        # Get basic call information from Twilio FIRST
        call_sid = request.POST.get('CallSid', '')
        caller_number = request.POST.get('From', '')
        called_number = request.POST.get('To', '')
        
        # Generate unique session ID for this call
        session_id = str(uuid.uuid4())
        
        logger.info(f"Incoming call - CallSid: {call_sid}, From: {caller_number}, To: {called_number}")
        
        # Build WebSocket URL immediately (before any database lookups)
        host = request.get_host()
        is_secure = request.is_secure() or 'ngrok' in host
        protocol = 'wss' if is_secure else 'ws'
        websocket_url = f"{protocol}://{host}/ws/realtime/{session_id}/"
        
        # IMMEDIATELY return TwiML with "Connected" message
        # Do routing logic asynchronously in the WebSocket consumer
        twiml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Connected</Say>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>'''
        
        logger.info(f"Sending immediate TwiML response for session: {session_id}")
        
        # Store basic call session info (routing will be done in consumer)
        try:
            from .models import CallSession
            CallSession.objects.create(
                session_id=session_id,
                twilio_call_sid=call_sid,
                caller_number=caller_number,
                called_number=called_number,
                status='started'
            )
        except Exception as e:
            logger.error(f"Error creating call session: {e}")
        
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
    from .tools import get_tools_for_openai
    
    tools = get_tools_for_openai()
    
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

@csrf_exempt
def get_template_instructions(request):
    """Get instructions for a specific template"""
    from django.http import JsonResponse
    from .models import InstructionTemplate
    
    template_id = request.GET.get('template_id')
    agent_name = request.GET.get('agent_name', 'Agent')
    
    if not template_id:
        return JsonResponse({'error': 'template_id is required'}, status=400)
    
    try:
        template = InstructionTemplate.objects.get(id=template_id, is_active=True)
        formatted_instructions = template.get_formatted_instructions(agent_name)
        
        return JsonResponse({
            'instructions': formatted_instructions,
            'template_name': template.name,
            'template_description': template.description
        })
    except InstructionTemplate.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
