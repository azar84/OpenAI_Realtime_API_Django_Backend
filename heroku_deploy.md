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

### 7. Migrations Run Automatically
The `release` phase in Procfile automatically runs:
- `python manage.py migrate --noinput` (applies all migrations)
- `python manage.py collectstatic --noinput` (collects static files)
- `python manage.py create_default_agent` (creates default agent if needed)

**No manual migration commands needed!** ✅

### 8. Configure Twilio
Update your Twilio webhook URL to:
```
https://your-app-name.herokuapp.com/api/webhook/
```

## 🔧 One-Command Deploy
```bash
heroku create && heroku addons:create heroku-postgresql:essential-0 && heroku addons:create heroku-redis:essential-0 && git push heroku main
```

## 🛡️ Preventing Migration Issues

### Automatic Migration Execution
The `release` phase in `Procfile` ensures migrations run on every deployment:
```bash
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py create_default_agent --name "Default Assistant" || true
```

### Migration Safety Features
- **Data migrations included**: Handle existing production data
- **User assignment**: Automatically assigns agents to admin user
- **Graceful fallbacks**: Won't fail deployment if admin user exists
- **Non-interactive**: All commands run without user input

### Best Practices
1. **Always test migrations locally** before deploying
2. **Create data migrations** for schema changes affecting existing data
3. **Use `--noinput` flags** for non-interactive deployment
4. **Include fallback logic** in migration scripts
