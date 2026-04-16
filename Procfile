release: flask --app run.py db upgrade
web: gunicorn --bind 0.0.0.0:$PORT --timeout 120 "platform_app:create_app()"
