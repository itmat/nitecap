import os
import simplejson as json

from __main__ import app
from models.users.decorators import requires_account

ALGORITHMS = ["cosinor", "ls", "arser"]
NOTIFICATION_API_ENDPOINT = os.environ["NOTIFICATION_API_ENDPOINT"]

template = {}
with open("computation/templates/index.html") as fin:
    template["homepage"] = fin.read()

with open("computation/templates/spreadsheet.html") as fin:
    template["spreadsheet"] = fin.read()


@app.route("/computation/spreadsheets")
@requires_account
def list_spreadsheets(user):
    spreadsheets = [{
        "id": spreadsheet.id,
        "filename": spreadsheet.original_filename
    } for spreadsheet in user.spreadsheets]

    return template["homepage"].replace(
        "DATA",
        json.dumps({
            "userId": user.id,
            "spreadsheets": spreadsheets,
        }),
    )


@app.route("/computation/spreadsheet/<spreadsheetId>", methods=["get"])
@requires_account
def view_spreadsheet(user, spreadsheetId):
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheetId)
    return template["spreadsheet"].replace(
        "DATA",
        json.dumps({
            "userId": user.id,
            "spreadsheet": {
                "id": spreadsheet.id,
                "filename": spreadsheet.original_filename
            },
            "algorithms": ALGORITHMS,
            "NOTIFICATION_API_ENDPOINT": NOTIFICATION_API_ENDPOINT,
        }),
    )