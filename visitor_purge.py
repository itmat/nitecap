import os
import sqlite3


def purge(dbfile):

    visitor_keep_limit = os.environ.get('VISITOR_SPREADSHEET_KEEP_LIMIT', 7)

    ids = []
    connection = sqlite3.connect(dbfile)
    cursor = connection.cursor()

    # Find the paths to all the spreadsheets belonging the visitors who last accessed the system more than
    # VISITOR_SPREADSHEET_KEEP_LIMIT days ago along with the ids of those visitors.
    sql = f"SELECT s.id, s.uploaded_file_path, s.file_path, u.id" \
          f" FROM spreadsheets AS s, users AS u" \
          f" WHERE s.user_id = u.id AND u.visitor is TRUE" \
          f"  AND date(u.last_access) <= date('now', '-{visitor_keep_limit} days')"
    print(sql)
    cursor.execute(sql)
    data = cursor.fetchall()

    # If any such visitors are found, delete the spreadsheet files associated with them.
    if data:
        for datum in data:
            spreadsheet_id, uploaded_file_path, working_file_path, user_id = datum
            try:
                sql = 'DELETE FROM spreadsheets WHERE spreadsheets.id=?'
                cursor.execute(sql, (spreadsheet_id,))
                if os.path.exists(working_file_path):
                    os.remove(working_file_path)
                if os.path.exists(uploaded_file_path):
                    os.remove(uploaded_file_path)
                ids.append(str(user_id))
                print(f"Spreadsheet for visitor {user_id} at {uploaded_file_path} completely purged.")
            except Exception as e:
                print(f"Spreadsheet {uploaded_file_path} for visitor {user_id} could not be completely expunged.", e)

        # Finally remove the visitors from the database.  By virtue of cascade delete, their spreadsheet records
        # should be expunged as well.
        sql = f"DELETE FROM users WHERE visitor is TRUE " \
              f" AND date(last_access) <= date('now', '-{visitor_keep_limit} days')"
        cursor.execute(sql)
        connection.commit()
        connection.close()
    return set(ids)


if __name__ == '__main__':
    print(purge("nitecap.db"))
