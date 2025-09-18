from django.core.management.base import BaseCommand
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

    def handle(self, *args, **options):
        name = options['name']
        voice = options['voice']
        instructions = options['instructions']

        agent_config, created = AgentConfiguration.objects.get_or_create(
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
                self.style.SUCCESS(f'Successfully created agent configuration: {name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Agent configuration already exists: {name}')
            )
