import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coderun2026_starter.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
