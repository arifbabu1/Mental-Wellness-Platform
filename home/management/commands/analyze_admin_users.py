from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from home.models import User as CustomUser


class Command(BaseCommand):
    help = 'Analyze admin users and their permissions'
    
    def handle(self, *args, **options):
        self.stdout.write('=== ADMIN USER ANALYSIS ===\n')
        
        # Get all users with admin role
        admin_users = CustomUser.objects.filter(role='admin')
        self.stdout.write(f'Found {admin_users.count()} users with admin role:\n')
        
        for admin in admin_users:
            self.stdout.write(f'\nUser: {admin.username}')
            self.stdout.write(f'   Email: {admin.email}')
            self.stdout.write(f'   Phone: {admin.phone}')
            self.stdout.write(f'   Role: {admin.role}')
            self.stdout.write(f'   is_staff: {admin.is_staff}')
            self.stdout.write(f'   is_superuser: {admin.is_superuser}')
            self.stdout.write(f'   is_active: {admin.is_active}')
            self.stdout.write(f'   is_verified: {admin.is_verified}')
            self.stdout.write(f'   Date joined: {admin.date_joined}')
            
            # Check if they can access admin
            if admin.is_staff and admin.is_active:
                self.stdout.write(f'   [OK] CAN access Django Admin')
            else:
                self.stdout.write(f'   [FAIL] CANNOT access Django Admin')
                if not admin.is_staff:
                    self.stdout.write(f'      Reason: is_staff = False')
                if not admin.is_active:
                    self.stdout.write(f'      Reason: is_active = False')
        
        # Also check all superusers
        superusers = CustomUser.objects.filter(is_superuser=True)
        self.stdout.write(f'\n\n=== SUPERUSERS ===')
        self.stdout.write(f'Found {superusers.count()} superusers:')
        
        for su in superusers:
            self.stdout.write(f'   {su.username} ({su.email})')
        
        # Check Django's built-in admin users
        self.stdout.write(f'\n\n=== DJANGO USER MODEL CHECK ===')
        django_users = User.objects.all()
        self.stdout.write(f'Total Django User objects: {django_users.count()}')
        
        for user in django_users:
            self.stdout.write(f'   {user.username} - is_staff: {user.is_staff}, is_superuser: {user.is_superuser}')
