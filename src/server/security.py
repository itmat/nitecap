from passlib.context import CryptContext

# Simply followed this url:  http://blog.tecladocode.com/learn-python-encrypting-passwords-python-flask-and-passlib/

pwd_context = CryptContext(
        schemes=["pbkdf2_sha256"],
        default="pbkdf2_sha256",
        pbkdf2_sha256__default_rounds=30000
)

def encrypt_password(password):
    return pwd_context.encrypt(password)


def check_encrypted_password(password, hashed):
    return pwd_context.verify(password, hashed)
