import os
import re
import sqlite3

from dotenv import load_dotenv, find_dotenv


def migrate(rehearse, db):
    upload_folder = os.environ["UPLOAD_FOLDER"]
    relocated_files = []
    connection = sqlite3.connect(db)
    cursor = connection.cursor()

    sql = 'SELECT user_id, id, uploaded_file_path, file_path FROM spreadsheets ORDER BY user_id'
    cursor.execute(sql)
    data = cursor.fetchall()
    if data:
        for datum in data:
            user_id, spreadsheet_id, uploaded_file_path, processed_file_path = datum
            print(f"Migrating data for spreadsheet_id {spreadsheet_id} belonging to user_id {user_id}")
            print(f"\tOriginal uploaded file path: {uploaded_file_path}")
            print(f"\tOriginal processed file path: {processed_file_path}")
            user_folder = os.path.join(os.environ['UPLOAD_FOLDER'], f'user_{user_id}')
            spreadsheet_data_folder = os.path.join(user_folder, f'spreadsheet_{spreadsheet_id}')
            if not os.path.exists(spreadsheet_data_folder):
                if rehearse:
                    print(f"\t\tMkdir - {spreadsheet_data_folder}")
                else:
                    os.makedirs(spreadsheet_data_folder, exist_ok=True)
            uploaded_file_ext = os.path.basename(os.path.splitext(uploaded_file_path)[1])
            processed_file_ext = os.path.basename(os.path.splitext(processed_file_path)[1])
            new_uploaded_file_path = os.path.join(spreadsheet_data_folder, f"uploaded_spreadsheet.{uploaded_file_ext}")
            new_processed_file_path = os.path.join(spreadsheet_data_folder, f"processed_spreadsheet.{processed_file_ext}")
            if rehearse:
                print(f"\t\tUPDATE spreadsheets SET spreadsheet_data_path = {spreadsheet_data_folder} WHERE id = {spreadsheet_id}")
                print(f"\t\tmv {uploaded_file_path} to {new_uploaded_file_path}")
                print(f"\t\tmv {processed_file_path} to {new_processed_file_path}")
                print(160*"-")
            else:
                sql = 'UPDATE spreadsheets SET spreadsheet_data_path = ? WHERE id = ?'
                cursor.execute(sql, (spreadsheet_data_folder, spreadsheet_id))
                os.rename(uploaded_file_path, new_uploaded_file_path)
                os.rename(processed_file_path, new_processed_file_path)
            relocated_files.extend([os.path.basename(uploaded_file_path), os.path.basename(processed_file_path)])

    print("")
    print("Handling those files not directly identifiable via the db...")
    pattern = re.compile('^(\d+)v(\d+)\.comparison.*$')
    for filepath in os.listdir(upload_folder):
        filename = os.path.basename(filepath)
        if filename in relocated_files:
            if not rehearse:
                print(f"\tFile {filename} should have been relocated!")
            continue
        print(160 * "-")
        print(f"Evaluating {filepath}")
        result = re.match(pattern, filename)
        if result:
            sql = 'SELECT user_id FROM spreadsheets WHERE id = ?'
            cursor.execute(sql, (result.group(1),))
            user_id = cursor.fetchone()
            if user_id:
                user_id = user_id[0]
            else:
                print(f"\tSpreadsheet id {result.group(1)} no longer exists for {filename}")
                continue
            cursor.execute(sql, (result.group(2),))
            user_id_repeat = cursor.fetchone()
            if user_id_repeat:
                user_id_repeat = user_id_repeat[0]
            else:
                print(f"\tSpreadsheet id {result.group(2)} no longer exists for {filename}")
                continue
            if user_id != user_id_repeat:
                print(f"\tDifferent users ({user_id},{user_id_repeat}) own the different spreadsheets"
                      f" ({result.group(1), result.group(2)}) in {filename}.  No action taken.")
                continue
            else:
                user_folder = os.path.join(upload_folder, f"user_{user_id}")
                comparison_folder = os.path.join(user_folder, "comparisons")
                if not os.path.exists(comparison_folder):
                    if rehearse:
                        print(f"\tMkdir - {comparison_folder}")
                    else:
                        os.makedirs(comparison_folder, exist_ok=True)
                new_filepath = os.path.join(comparison_folder, filename)
                if rehearse:
                    print(f"\tmv {filepath} to {new_filepath}")
                #os.rename(filepath, new_filepath)
        else:
            print(f"\tFile {filepath} has no owner.  May be legecy data.")



if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    DATABASE_FILE = os.environ['DATABASE_FILE']
    DATABASE_FOLDER = os.environ.get('DATABASE_FOLDER', '')
    if DATABASE_FOLDER:
        DATABASE_FOLDER += os.sep
    DATABASE = DATABASE_FOLDER + DATABASE_FILE
    migrate(True, DATABASE)