from django.core.management.base import BaseCommand
from home.models import User


class Command(BaseCommand):
    help = 'Fix admin user permissions for Django admin access'
    
    def handle(self, *args, **options):
        self.stdout.write('=== FIXING ADMIN USER PERMISSIONS ===\n')
        
        # Get all users with admin role
        admin_users = User.objects.filter(role='admin')
        self.stdout.write(f'Found {admin_users.count()} users with admin role:\n')
        
        for admin in admin_users:
            self.stdout.write(f'\nProcessing: {admin.username}')
            self.stdout.write(f'   Current: is_staff={admin.is_staff}, is_superuser={admin.is_superuser}')
            
            # Fix admin permissions
            if admin.role == 'admin':
                admin.is_staff = True
                admin.is_superuser = True
                admin.save()
                self.stdout.write(f'   Updated: is_staff=True, is_superuser=True')
                self.stdout.write(f'   [FIXED] Now can access Django Admin')
            else:
                self.stdout.write(f'   [SKIP] Role is not admin')
        
        self.stdout.write(f'\n=== SUMMARY ===')
        self.stdout.write(f'All admin role users now have Django admin access!')
        self.stdout.write(f'They can login at: http://127.0.0.1:8000/admin/')
