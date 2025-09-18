from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from realtime_api.models import AgentConfiguration

class Command(BaseCommand):
    help = 'Create a default agent configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            default='Default Assistant',
            help='Name for the agent configuration',
        )
        parser.add_argument(
            '--voice',
            type=str,
            default='alloy',
            choices=['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            help='Voice for the agent',
        )
        parser.add_argument(
            '--instructions',
            type=str,
            default='You are a helpful AI assistant. You can respond with both text and audio. Keep responses concise and natural.',
            help='Instructions for the agent',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Username to create agent for (if not provided, creates for first superuser)',
        )

    def handle(self, *args, **options):
        name = options['name']
        voice = options['voice']
        instructions = options['instructions']
        username = options.get('user')

        # Get the user
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User "{username}" does not exist')
                )
                return
        else:
            # Get first superuser or create a default user
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(
                    self.style.WARNING('No superuser found. Please create a superuser first with: python manage.py createsuperuser')
                )
                return

        agent_config, created = AgentConfiguration.objects.get_or_create(
            user=user,
            name=name,
            defaults={
                'instructions': instructions,
                'voice': voice,
                'temperature': 0.8,
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created agent configuration: {name} for user: {user.username}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Agent configuration already exists: {name} for user: {user.username}')
            )
