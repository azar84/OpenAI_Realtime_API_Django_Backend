from django.core.management.base import BaseCommand
from django.utils import timezone
from realtime_api.models import CallSession, Conversation, Turn, Event


class Command(BaseCommand):
    help = 'Fix timestamps for existing AI turns that were reprocessed'

    def add_arguments(self, parser):
        parser.add_argument('--session-id', type=str, help='Specific session ID to fix')
        parser.add_argument('--all', action='store_true', help='Fix all sessions')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        if options['session_id']:
            self.fix_session(options['session_id'], options['dry_run'])
        elif options['all']:
            self.fix_all_sessions(options['dry_run'])
        else:
            self.stdout.write("Please specify --session-id or --all")

    def fix_session(self, session_id, dry_run=False):
        """Fix timestamps for a specific session"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            conversations = call_session.conversations.all()
            
            self.stdout.write(f"\n🔧 Fixing Timestamps for Session: {session_id}")
            self.stdout.write("=" * 50)
            
            for conversation in conversations:
                self.fix_conversation_timestamps(conversation, dry_run)
                
        except CallSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Session {session_id} not found"))

    def fix_all_sessions(self, dry_run=False):
        """Fix timestamps for all sessions"""
        sessions = CallSession.objects.all().order_by('-call_start_time')
        
        self.stdout.write(f"\n🔧 Fixing Timestamps for All Sessions ({sessions.count()} total)")
        self.stdout.write("=" * 60)
        
        fixed_count = 0
        for session in sessions:
            conversations = session.conversations.all()
            if conversations.exists():
                for conversation in conversations:
                    if self.fix_conversation_timestamps(conversation, dry_run):
                        fixed_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"✅ Fixed timestamps for {fixed_count} conversations"))

    def fix_conversation_timestamps(self, conversation, dry_run=False):
        """Fix timestamps for AI turns in a conversation"""
        # Find AI turns that were reprocessed and might have incorrect timestamps
        ai_turns = conversation.turns.filter(role='assistant', meta__reprocessed=True)
        
        if not ai_turns.exists():
            return False
        
        self.stdout.write(f"\n📝 Fixing Conversation {conversation.id}")
        self.stdout.write(f"  Found {ai_turns.count()} reprocessed AI turns")
        
        fixed_count = 0
        for turn in ai_turns:
            response_id = turn.meta.get('response_id')
            if response_id:
                # Get the events for this turn's response_id
                events = conversation.events.filter(response_id=response_id).order_by('created_at')
                if events.exists():
                    # Calculate correct timestamps
                    start_time = events.first().created_at
                    end_time = events.last().created_at
                    
                    if not dry_run:
                        # Update timestamps
                        turn.started_at = start_time
                        turn.completed_at = end_time
                        turn.save()
                        fixed_count += 1
                        self.stdout.write(f"    ✅ Fixed turn: {turn.text[:50]}...")
                        self.stdout.write(f"        Started: {start_time.strftime('%H:%M:%S')}")
                        self.stdout.write(f"        Completed: {end_time.strftime('%H:%M:%S')}")
                    else:
                        self.stdout.write(f"    [DRY RUN] Would fix turn: {turn.text[:50]}...")
                        self.stdout.write(f"        Current: {turn.started_at.strftime('%H:%M:%S')} -> {turn.completed_at.strftime('%H:%M:%S')}")
                        self.stdout.write(f"        Would set: {start_time.strftime('%H:%M:%S')} -> {end_time.strftime('%H:%M:%S')}")
                        fixed_count += 1
        
        if fixed_count > 0:
            if dry_run:
                self.stdout.write(f"  [DRY RUN] Would fix {fixed_count} AI turn timestamps")
            else:
                self.stdout.write(f"  ✅ Fixed {fixed_count} AI turn timestamps")
            return True
        else:
            self.stdout.write(f"  ℹ️  No AI turn timestamps needed fixing")
            return False
