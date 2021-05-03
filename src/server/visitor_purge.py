from datetime import datetime
import os
import shutil
import sqlite3

from dotenv import load_dotenv, find_dotenv


def purge(rehearse, db):

    now = datetime.now()
    print(f"Server Time: {now.strftime('%c')}")

    visitor_keep_limit = os.environ.get('VISITOR_SPREADSHEET_KEEP_LIMIT', 7)
    upload_folder = os.environ['UPLOAD_FOLDER']

    ids = []
    connection = sqlite3.connect(db)
    cursor = connection.cursor()

    # Find the paths to all the visitors who last accessed the system more than VISITOR_SPREADSHEET_KEEP_LIMIT days
    # ago along with the ids of those visitors.
    sql = f"SELECT id, datetime(last_access) FROM users WHERE visitor is TRUE" \
          f"  AND date(last_access) <= date('now', '-{visitor_keep_limit} days') ORDER BY id"
    print(sql)
    cursor.execute(sql)
    data = cursor.fetchall()

    # If any such visitors are found, delete them and their spreadsheet data.
    if data:
        for datum in data:
            user_id, last_access = datum
            try:
                sql = 'DELETE FROM spreadsheets WHERE spreadsheets.user_id=?'
                if rehearse:
                    print(sql, user_id)
                else:
                    cursor.execute(sql, (user_id,))
                sql = 'DELETE FROM users WHERE id=?'
                if rehearse:
                    print(sql, user_id)
                else:
                    cursor.execute(sql, (user_id,))
                user_directory_path = os.path.join(upload_folder, f"user_{user_id}")
                if os.path.exists(user_directory_path):
                    if rehearse:
                        print(f"rmtree {user_directory_path}")
                    else:
                        shutil.rmtree(user_directory_path)
                ids.append(str(user_id))
                print(f"Visitor {user_id}, last seen {last_access}, completely purged.")
            except Exception as e:
                print(f"Visitor {user_id}, last seen {last_access}, could not be completely expunged.", e)
        connection.commit()
        connection.close()
    return set(ids)


if __name__ == '__main__':
    load_dotenv(find_dotenv(usecwd=True))
    DATABASE_FILE = os.environ['DATABASE_FILE']
    DATABASE_FOLDER = os.environ.get('DATABASE_FOLDER', '')
    if DATABASE_FOLDER:
        DATABASE_FOLDER += os.sep
    DATABASE = DATABASE_FOLDER + DATABASE_FILE
    print(purge(True, DATABASE))
