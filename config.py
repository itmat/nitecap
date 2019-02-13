
UPLOAD_FOLDER = '/opt/nitecap/uploads'
DEBUG = True
SECRET_KEY = 'cris'
SQLALCHEMY_DATABASE_URI = "sqlite:///nitecap.db"
SQLALCHEMY_TRACK_MODIFICATIONS = False
SERVER = "127.0.0.1:5000"
EMAIL_SENDER = "criswlawrence@gmail.com"
ALLOWED_EXTENSIONS = frozenset(['txt', 'csv', 'xlsx'])