#RUN mkdir /nitecap_web \
mkdir -p /nitecap_web/uploads
mkdir -p /nitecap_web/db_backup
mkdir -p /nitecap_web/db
touch /nitecap_web/log
chown www-data:www-data /nitecap_web /nitecap_web/uploads /nitecap_web/db_backup /nitecap_web/db /nitecap_web/log

# Starts the appropriate server based off the current 'ENV' (i.e. either PROD or DEV server)
if [[ ${ENV} == "DEV" ]] ; then
    # Dev - use Flask's built-in development server
    exec python app.py
else
    # Production - use apache
    exec /usr/sbin/apache2ctl -DFOREGROUND
fi
