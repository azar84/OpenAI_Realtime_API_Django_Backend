web: daphne realtime_backend.asgi:application --port $PORT --bind 0.0.0.0 -v2
worker: python manage.py runworker -v2
release: python manage.py fix_production_db && python manage.py migrate --noinput && python manage.py collectstatic --noinput
