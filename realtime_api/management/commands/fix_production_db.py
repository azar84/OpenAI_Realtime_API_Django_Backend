from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from realtime_api.models import AgentConfiguration, UserProfile


class Command(BaseCommand):
    help = 'Fix production database issues for Heroku deployment'

    def handle(self, *args, **options):
        self.stdout.write("🔧 Fixing production database issues...")
        
        # 1. Create admin user if doesn't exist
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_superuser': True,
                'is_staff': True,
            }
        )
        
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created admin user: {admin_user.username}')
            )
        else:
            self.stdout.write(f'ℹ️  Admin user already exists: {admin_user.username}')
        
        # 2. Create UserProfile for admin if doesn't exist
        profile, profile_created = UserProfile.objects.get_or_create(user=admin_user)
        if profile_created:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created UserProfile for: {admin_user.username}')
            )
        
        # 3. Assign agents with null user_id to admin
        agents_without_users = AgentConfiguration.objects.filter(user__isnull=True)
        count = agents_without_users.count()
        
        if count > 0:
            for agent in agents_without_users:
                agent.user = admin_user
                agent.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Assigned {count} agents to admin user')
            )
        else:
            self.stdout.write('ℹ️  All agents already have users assigned')
        
        # 4. Summary
        total_agents = AgentConfiguration.objects.count()
        total_users = User.objects.count()
        
        self.stdout.write(
            self.style.SUCCESS(f'🎯 Database fixed! Users: {total_users}, Agents: {total_agents}')
        )
