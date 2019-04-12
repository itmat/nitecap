import os
import sqlite3
import time


def purge(dbfile):

    ids = []
    connection = sqlite3.connect(dbfile)
    cursor = connection.cursor()

    cursor.execute("SELECT s.id, s.uploaded_file_path, s.file_path"
                   " FROM spreadsheets AS s, users AS u"
                   " WHERE s.user_id = u.id AND u.username='annonymous'")
    visitor_spreadsheets = cursor.fetchall()

    visitor_spreadsheet_keep_limit = os.environ.get('VISITOR_SPREADSHEET_KEEP_LIMIT', 7)

    if visitor_spreadsheets:
        for spreadsheet in visitor_spreadsheets:
            id, uploaded_file_path, working_file_path = spreadsheet
            if os.path.exists(uploaded_file_path) and os.stat(uploaded_file_path).st_ctime < \
                (time.time() - int(visitor_spreadsheet_keep_limit) * 86_400):
                try:
                    sql = 'DELETE FROM spreadsheets WHERE spreadsheets.id=?'
                    cursor.execute(sql, (id,))
                    if os.path.exists(working_file_path):
                        os.remove(working_file_path)
                    if os.path.exists(uploaded_file_path):
                        os.remove(uploaded_file_path)
                    ids.append(str(id))
                    print(f"Visitor spreadsheet {id} at "
                                            f"{uploaded_file_path} completely purged.")
                except Exception as e:
                    print(f"The data for visitor spreadsheet {id} could not all "
                                             f"be successfully expunged.", e)
                finally:
                    connection.commit()
    return ids

if __name__ == '__main__':
    purge("nitecap.db")