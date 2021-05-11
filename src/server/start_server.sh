# Starts the appropriate server based off the current 'ENV' (i.e. either PROD or DEV server)
if [ ${ENV} = "DEV" ] ; then
    # Dev - use Flask's built-in development server
    python app.py
else
    # Production - use apache
    /usr/sbin/apache2ctl -DFOREGROUND
fi