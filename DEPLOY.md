# Mediators on Call - Production Deployment

## Prerequisites

- Python 3.14+
- PostgreSQL 14+
- Redis 6+
- Nginx
- systemd

## Environment Setup

1. Copy `.env.example` to `.env` and fill in values:
```bash
cp .env.example .env
```

2. Key environment variables:
- `DJANGO_SECRET_KEY` - Generate a strong secret key
- `DJANGO_DEBUG=False` - Must be False in production
- `DJANGO_ALLOWED_HOSTS` - Your domain(s), comma-separated
- Database credentials
- Twilio credentials for SMS
- AWS credentials for S3 (optional)

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser
```

## Running Services

### Option 1: Manual (development)

```bash
# Terminal 1: Run Django
python manage.py runserver 0.0.0.0:8000

# Terminal 2: Run Celery worker
celery -A mediators_on_call worker --loglevel=info

# Terminal 3: Run Celery beat
celery -A mediators_on_call beat --loglevel=info
```

### Option 2: Production with Gunicorn + Celery

```bash
# Start Gunicorn
gunicorn mediators_on_call.wsgi:application --config gunicorn.conf.py

# Start Celery worker (as systemd service)
sudo cp deploy/celery-worker.service /etc/systemd/system/
sudo systemctl enable celery-worker
sudo systemctl start celery-worker

# Start Celery beat (as systemd service)
sudo cp deploy/celery-beat.service /etc/systemd/system/
sudo systemctl enable celery-beat
sudo systemctl start celery-beat
```

### Option 3: Docker

```bash
# Build and run with Docker Compose
docker-compose up -d --build
```

## Nginx Configuration

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/mediators-on-call
sudo ln -s /etc/nginx/sites-available/mediators-on-call /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## SSL Certificate

```bash
# Using Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mediators-on-call.com -d www.mediators-on-call.com
```

## Verify Deployment

1. Check Django: `curl https://mediators-on-call.com/admin/`
2. Check Celery: `celery -A mediators_on_call inspect active`
3. Check logs: `/var/log/celery/`

## Monitoring

- Sentry SDK is integrated - set `SENTRY_DSN` environment variable
- Celery logs: `/var/log/celery/`
- Django logs: Configure in settings
