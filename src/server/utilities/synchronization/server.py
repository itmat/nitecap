from flask import Flask

server = Flask(__name__)


@server.route("/")
def home():
    return "Synchronizing data..."


server.run(host="0.0.0.0")
