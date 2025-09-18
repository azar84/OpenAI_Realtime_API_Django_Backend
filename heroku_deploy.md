# Heroku Deployment Guide

## 🚀 Quick Deploy to Heroku

### 1. Install Heroku CLI
```bash
# Download from: https://devcenter.heroku.com/articles/heroku-cli
```

### 2. Login to Heroku
```bash
heroku login
```

### 3. Create Heroku App
```bash
heroku create your-app-name
```

### 4. Add Required Add-ons
```bash
# PostgreSQL database
heroku addons:create heroku-postgresql:essential-0

# Redis for WebSocket channels
heroku addons:create heroku-redis:essential-0
```

### 5. Set Environment Variables
```bash
heroku config:set OPENAI_API_KEY=your_openai_api_key
heroku config:set TWILIO_ACCOUNT_SID=your_twilio_sid
heroku config:set TWILIO_AUTH_TOKEN=your_twilio_token
heroku config:set DEBUG=False
```

### 6. Deploy
```bash
git add .
git commit -m "Heroku deployment configuration"
git push heroku main
```

### 7. Run Migrations
```bash
heroku run python manage.py migrate
heroku run python manage.py create_default_agent
```

### 8. Configure Twilio
Update your Twilio webhook URL to:
```
https://your-app-name.herokuapp.com/api/webhook/
```

## 🔧 One-Command Deploy
```bash
heroku create && heroku addons:create heroku-postgresql:essential-0 && heroku addons:create heroku-redis:essential-0 && git push heroku main && heroku run python manage.py migrate && heroku run python manage.py create_default_agent
```
