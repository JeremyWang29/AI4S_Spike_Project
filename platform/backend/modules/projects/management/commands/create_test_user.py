from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or reset a local invited test account"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        if len(options["password"]) < 8:
            raise CommandError("测试密码至少需要8个字符")
        user, created = get_user_model().objects.get_or_create(username=options["username"])
        user.is_active = True
        user.set_password(options["password"])
        user.save()
        action = "created" if created else "reset"
        self.stdout.write(self.style.SUCCESS(f"{action}: {user.get_username()}"))
