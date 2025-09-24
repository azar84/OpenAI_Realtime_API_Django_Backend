from django.core.management.base import BaseCommand
from django.utils import timezone
from realtime_api.models import CallSession, Conversation, Turn, Event
import json


class Command(BaseCommand):
    help = 'Reprocess existing conversations to extract AI responses from events'

    def add_arguments(self, parser):
        parser.add_argument('--session-id', type=str, help='Specific session ID to reprocess')
        parser.add_argument('--all', action='store_true', help='Reprocess all conversations')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        if options['session_id']:
            self.reprocess_session(options['session_id'], options['dry_run'])
        elif options['all']:
            self.reprocess_all_sessions(options['dry_run'])
        else:
            self.stdout.write("Please specify --session-id or --all")

    def reprocess_session(self, session_id, dry_run=False):
        """Reprocess a specific session"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            conversations = call_session.conversations.all()
            
            self.stdout.write(f"\n🔄 Reprocessing Session: {session_id}")
            self.stdout.write("=" * 50)
            
            for conversation in conversations:
                self.reprocess_conversation(conversation, dry_run)
                
        except CallSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Session {session_id} not found"))

    def reprocess_all_sessions(self, dry_run=False):
        """Reprocess all sessions"""
        sessions = CallSession.objects.all().order_by('-call_start_time')
        
        self.stdout.write(f"\n🔄 Reprocessing All Sessions ({sessions.count()} total)")
        self.stdout.write("=" * 60)
        
        processed_count = 0
        for session in sessions:
            conversations = session.conversations.all()
            if conversations.exists():
                for conversation in conversations:
                    if self.reprocess_conversation(conversation, dry_run):
                        processed_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Processed {processed_count} conversations"))

    def reprocess_conversation(self, conversation, dry_run=False):
        """Reprocess a single conversation to extract AI responses"""
        # Get all audio transcript events for this conversation
        audio_events = conversation.events.filter(
            event_type='response.audio_transcript.delta'
        ).order_by('created_at')
        
        if not audio_events.exists():
            return False
        
        self.stdout.write(f"\n📝 Reprocessing Conversation {conversation.id}")
        self.stdout.write(f"  Found {audio_events.count()} audio transcript events")
        
        # Group events by response_id
        response_groups = {}
        for event in audio_events:
            response_id = event.response_id
            if response_id:
                if response_id not in response_groups:
                    response_groups[response_id] = []
                response_groups[response_id].append(event)
        
        self.stdout.write(f"  Found {len(response_groups)} unique AI responses")
        
        created_turns = 0
        for response_id, events in response_groups.items():
            # Check if we already have a turn for this response
            existing_turn = conversation.turns.filter(
                role='assistant',
                meta__response_id=response_id
            ).first()
            
            if existing_turn:
                self.stdout.write(f"    Response {response_id[:8]}... already has turn")
                continue
            
            # Combine all deltas for this response
            text_parts = []
            metadata = {}
            
            for event in events:
                if event.text_delta:
                    text_parts.append(event.text_delta)
                
                # Get metadata from the first event
                if not metadata and event.payload:
                    try:
                        payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
                        metadata = payload.get('response', {})
                    except:
                        pass
            
            if text_parts:
                complete_text = "".join(text_parts)
                
                if not dry_run:
                    # Create the turn
                    # Calculate proper timestamps
                    start_time = min(event.created_at for event in events)
                    end_time = max(event.created_at for event in events)
                    
                    turn = Turn.objects.create(
                        conversation=conversation,
                        role='assistant',
                        text=complete_text,
                        meta={
                            'response_id': response_id,
                            'audio_transcript': True,
                            'reprocessed': True,
                            **metadata
                        },
                        started_at=start_time,
                        completed_at=end_time
                    )
                    created_turns += 1
                    self.stdout.write(f"    ✅ Created turn for response {response_id[:8]}...: {complete_text[:50]}...")
                else:
                    self.stdout.write(f"    [DRY RUN] Would create turn for response {response_id[:8]}...: {complete_text[:50]}...")
                    created_turns += 1
        
        if created_turns > 0:
            if dry_run:
                self.stdout.write(f"  [DRY RUN] Would create {created_turns} AI response turns")
            else:
                self.stdout.write(f"  ✅ Created {created_turns} AI response turns")
            return True
        else:
            self.stdout.write(f"  ℹ️  No new AI response turns needed")
            return False
