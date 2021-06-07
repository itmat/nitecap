#RUN mkdir /nitecap_web \
mkdir -p /nitecap_web/uploads
mkdir -p /nitecap_web/db_backup
mkdir -p /nitecap_web/db
mkdir -p /nitecap_web/logs
chown www-data:www-data /nitecap_web /nitecap_web/uploads /nitecap_web/db_backup /nitecap_web/db /nitecap_web/logs

# Starts the appropriate server based off the current 'ENV' (i.e. either PROD or DEV server)
if [[ ${ENV} == "DEV" ]] ; then
    # Dev - use Flask's built-in development server
    exec dumb-init python app.py
else
    # Production - use apache
    # The init system rewrites SIGTERM signal into SIGWINCH which gracefully stops Apache
    exec dumb-init --rewrite 15:28 /usr/sbin/apache2ctl -DFOREGROUND
fi
