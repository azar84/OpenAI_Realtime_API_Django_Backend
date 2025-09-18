# Django OpenAI Realtime API Backend

A Django backend server that connects Twilio phone calls to OpenAI's Realtime API, enabling voice conversations with AI agents over the phone.

## Features

- 🎯 **WebSocket Integration**: Real-time connection to OpenAI's Realtime API
- 📞 **Twilio Integration**: Handle incoming phone calls and stream audio
- 🤖 **Agent Management**: Configurable AI agents with different personalities and settings
- 🎵 **Audio Streaming**: Bidirectional audio streaming between Twilio and OpenAI
- 📊 **Session Tracking**: Track call sessions and conversation logs
- ⚙️ **Admin Interface**: Django admin for managing agents and viewing call history

## Architecture

```
Twilio Call → Django WebSocket → OpenAI Realtime API
     ↓              ↓                    ↓
Phone User ← Audio Stream ← AI Assistant Response
```

## Installation

### Prerequisites

- Python 3.10+
- Redis server (for Django Channels)
- Twilio account
- OpenAI API key with Realtime API access

### Setup

1. **Clone and install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Configuration:**
   Create a `.env` file based on `env_example.txt`:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
   TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
   SECRET_KEY=your_secret_key_here
   DEBUG=True
   REDIS_URL=redis://localhost:6379
   ```

3. **Database Setup:**
   ```bash
   python manage.py migrate
   python manage.py create_default_agent
   python manage.py createsuperuser
   ```

4. **Start Redis Server:**
   ```bash
   redis-server
   ```

5. **Run the Development Server:**
   ```bash
   python manage.py runserver
   ```

## Usage

### Twilio Configuration

1. **Configure Webhook URL** in your Twilio phone number settings:
   ```
   https://your-domain.com/api/webhook/
   ```

2. **Status Callback URL** (optional):
   ```
   https://your-domain.com/api/status/
   ```

### Agent Configuration

Access the Django admin at `/admin/` to:

- Create and manage AI agent configurations
- Set voice, temperature, instructions, and other parameters
- View call session history and conversation logs

### WebSocket Endpoint

The WebSocket endpoint for real-time communication:
```
wss://your-domain.com/ws/realtime/{session_id}/
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/webhook/` | POST | Twilio webhook for incoming calls |
| `/api/status/` | POST | Twilio status callback |
| `/api/health/` | GET | Health check endpoint |
| `/admin/` | GET | Django admin interface |

## Models

### AgentConfiguration
- **Purpose**: Define AI agent behavior and settings
- **Fields**: name, instructions, voice, temperature, audio formats, VAD settings
- **Methods**: `to_openai_config()` - converts to OpenAI session format

### CallSession
- **Purpose**: Track individual call sessions
- **Fields**: session_id, twilio_call_sid, agent_config, call timing, conversation_log
- **Methods**: `add_to_conversation_log()` - log conversation events

## WebSocket Consumer

The `RealtimeConsumer` handles:

1. **Connection Management**: Establish connections to OpenAI Realtime API
2. **Audio Streaming**: Bidirectional audio between Twilio and OpenAI
3. **Session Configuration**: Apply agent settings to OpenAI session
4. **Message Routing**: Route messages between Twilio and OpenAI
5. **Error Handling**: Graceful error handling and connection cleanup

## Message Types

### From Twilio:
- `twilio_stream_start`: Stream initialization
- `twilio_media`: Audio data packets
- `twilio_stream_stop`: Stream termination

### From OpenAI:
- `session.created`: Session established
- `response.audio.delta`: Audio response chunks
- `response.text.delta`: Text response chunks
- `conversation.item.created`: New conversation item

## Development

### Project Structure
```
realtime_backend/
├── realtime_api/           # Main application
│   ├── consumers.py        # WebSocket consumer
│   ├── models.py          # Database models
│   ├── views.py           # HTTP views
│   ├── routing.py         # WebSocket routing
│   └── admin.py           # Admin configuration
├── realtime_backend/       # Django project settings
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Key Components

1. **WebSocket Consumer** (`consumers.py`):
   - Handles real-time communication
   - Manages OpenAI API connections
   - Processes audio streaming

2. **Models** (`models.py`):
   - Agent configuration management
   - Call session tracking
   - Conversation logging

3. **Views** (`views.py`):
   - Twilio webhook handlers
   - TwiML response generation
   - Health check endpoints

## Deployment

### Production Considerations

1. **WebSocket Server**: Use Daphne or similar ASGI server
2. **Redis**: Configure Redis for production use
3. **SSL/TLS**: Ensure HTTPS/WSS for secure connections
4. **Environment Variables**: Secure API key management
5. **Logging**: Configure appropriate logging levels
6. **Monitoring**: Set up health checks and monitoring

### Docker Deployment (Optional)
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "realtime_backend.asgi:application"]
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**:
   - Check OpenAI API key and permissions
   - Verify Realtime API access
   - Check network connectivity

2. **Audio Quality Issues**:
   - Verify audio format settings (PCM16)
   - Check VAD threshold settings
   - Review network latency

3. **Twilio Integration**:
   - Verify webhook URL accessibility
   - Check Twilio credentials
   - Review TwiML response format

### Logging

Enable debug logging in `settings.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'realtime_api': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions:
- Check the troubleshooting section
- Review Django Channels documentation
- Consult OpenAI Realtime API documentation
- Check Twilio WebSocket documentation
