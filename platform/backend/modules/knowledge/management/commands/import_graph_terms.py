"""Import a licensed terminology release from a local JSON array."""
import json
import uuid
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from modules.knowledge.services import import_graph_terms


class Command(BaseCommand):
    help = 'Import a licensed read-only graph terminology release'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--project-id', help='Project UUID; omit for platform-wide terms')
        parser.add_argument('--platform-wide-authorized', action='store_true',
            help='Assert reviewed license permits access by every pilot project')
        parser.add_argument('--graph-version', required=True)
        parser.add_argument('--license', required=True)
        parser.add_argument('--allow-external-sharing', action='store_true')

    def handle(self, *args, **options):
        try:
            project_id = uuid.UUID(options['project_id']) if options['project_id'] else None
            rows = json.loads(Path(options['path']).read_text(encoding='utf-8'))
            count = import_graph_terms(project_id, options['graph_version'], options['license'], rows,
                external_sharing_allowed=options['allow_external_sharing'],
                platform_wide_authorized=options['platform_wide_authorized'])
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Imported {count} graph terms'))
