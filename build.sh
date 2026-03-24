python manage.py collectstatic --noinput
python manage.py migrate --noinput

# Load mediator data if users.json and mediators.json exist
if [ -f users.json ]; then
    python manage.py loaddata users.json
fi
if [ -f mediators.json ]; then
    python manage.py loaddata mediators.json
fi
