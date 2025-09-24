# Chat History Template

## Overview

The chat history template provides a beautiful, modern interface for viewing conversation history from AI agent calls. It displays the complete conversation flow between users and AI agents in an easy-to-read format.

## Features

- **Modern UI**: Clean, responsive design with gradient backgrounds and smooth animations
- **Call Information**: Displays caller/called numbers, agent details, call duration, and status
- **Conversation Flow**: Shows complete conversation turns with user and AI messages
- **Error Handling**: Displays transcription failures and errors gracefully
- **Mobile Responsive**: Works perfectly on desktop and mobile devices
- **Admin Integration**: Direct links from Django admin interface

## How to Access

### From Django Admin

1. Go to the Django admin interface
2. Navigate to **Realtime API > Call Sessions**
3. Click on any call session
4. Click the **"📞 View Chat History"** button
5. The chat history will open in a new tab

### Direct URL Access

You can also access chat history directly via URL:

```
http://your-domain.com/api/chat-history/{session_id}/
```

Replace `{session_id}` with the actual session ID from the call session.

## Template Structure

The template is located at:
```
realtime_api/templates/realtime_api/chat_history.html
```

### Key Components

1. **Header Section**: Shows session ID and call information
2. **Call Info Grid**: Displays caller/called numbers, agent, status, timing
3. **Conversation List**: Shows all conversations with their turns
4. **Turn Display**: Individual messages with avatars and timestamps

### Styling

The template includes comprehensive CSS styling with:
- Modern gradient backgrounds
- Card-based layout
- Smooth animations and transitions
- Responsive design for mobile devices
- Status badges and visual indicators

## Security

- **User Isolation**: Non-superusers can only view their own call sessions
- **Permission Checks**: Proper authentication and authorization
- **Session Validation**: Ensures session IDs are valid before display

## Data Sources

The template displays data from:
- `CallSession` model: Basic call information
- `Conversation` model: Conversation metadata
- `Turn` model: Individual user/AI messages
- `Event` model: Raw OpenAI API events (for debugging)

## Customization

You can customize the template by:
1. Modifying the CSS styles in the `<style>` section
2. Adding new fields to the context in `views.py`
3. Changing the layout structure in the HTML
4. Adding new interactive features with JavaScript

## Example Usage

```python
# In your Django view
from django.shortcuts import render
from .models import CallSession

def my_chat_view(request, session_id):
    call_session = CallSession.objects.get(session_id=session_id)
    conversations = call_session.conversations.prefetch_related('turns').all()
    
    return render(request, 'realtime_api/chat_history.html', {
        'call_session': call_session,
        'conversations': conversations,
    })
```

## Troubleshooting

### Template Not Found
- Ensure the template is in `realtime_api/templates/realtime_api/chat_history.html`
- Check that `APP_DIRS = True` in Django settings

### Permission Denied
- Verify user has access to the call session
- Check that the call session belongs to the user's phone number

### Empty Conversations
- Check if conversation tracking is enabled
- Verify that turns are being saved to the database
- Look at the conversation tracker logs for errors

## Future Enhancements

Potential improvements:
- Real-time updates via WebSocket
- Export conversation history to PDF/CSV
- Search functionality within conversations
- Audio playback for recorded conversations
- Conversation analytics and insights
