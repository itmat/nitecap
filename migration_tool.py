import os
import re
import sqlite3

import termcolor as termcolor
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
            user_folder = os.path.join(os.environ['UPLOAD_FOLDER'], f'user_{user_id}')

            # Prepare spreadsheet data folder
            print("\tSpreadsheet data folder")
            spreadsheet_data_folder = os.path.join(user_folder, f'spreadsheet_{spreadsheet_id}')

            # Create spreadsheet data folder
            if not os.path.exists(spreadsheet_data_folder):
                if not rehearse:
                    os.makedirs(spreadsheet_data_folder, exist_ok=True)
                print(f"\t\tMkdir - {spreadsheet_data_folder}")

            # Add spreadsheet data folder to spreadsheet record
            if not rehearse:
                sql = "UPDATE spreadsheets SET spreadsheet_data_path = ? WHERE id = ?"
                cursor.execute(sql, (spreadsheet_data_folder, spreadsheet_id))
                connection.commit()
            print(f"\t\tUPDATE spreadsheets SET spreadsheet_data_path = '{spreadsheet_data_folder}' "
                  f"WHERE id = {spreadsheet_id}")

            # Check for related uploaded spreadsheet file and if present, move it under new spreadsheet folder
            print(f"\tOriginal uploaded file path: {uploaded_file_path}")
            if uploaded_file_path and os.path.exists(uploaded_file_path):
                uploaded_file_ext = os.path.basename(os.path.splitext(uploaded_file_path)[1])
                new_uploaded_file_path = os.path.join(spreadsheet_data_folder,
                                                      f"uploaded_spreadsheet.{uploaded_file_ext}")
                # Relocate uploaded spreadsheet
                if not rehearse:
                    os.rename(uploaded_file_path, new_uploaded_file_path)
                print(f"\t\tmv {uploaded_file_path} to {new_uploaded_file_path}")

                # Add new upload file path to spreadsheet record
                if not rehearse:
                    sql = "UPDATE spreadsheets SET uploaded_file_path = ? WHERE id = ?"
                    cursor.execute(sql, (new_uploaded_file_path, spreadsheet_id))
                    connection.commit()
                print(f"\t\tUPDATE spreadsheets SET uploaded_file_path = '{new_uploaded_file_path}' "
                      f"WHERE id = {spreadsheet_id}")

            else:
                if not uploaded_file_path:
                    termcolor.cprint(f"\t\tSpreadsheet {spreadsheet_id} missing uploaded spreadsheet reference", 'red')
                else:
                    termcolor.cprint(f"\t\tSpreadsheet {spreadsheet_id} missing uploaded spreadsheet file", 'red')

            # Check for related processed spreadsheet file and if present, move it under new spreadsheet folder
            print(f"\tOriginal processed file path: {processed_file_path}")
            if processed_file_path and os.path.exists(processed_file_path):
                processed_file_ext = os.path.basename(os.path.splitext(processed_file_path)[1])
                new_processed_file_path = os.path.join(spreadsheet_data_folder,
                                                       f"processed_spreadsheet.{processed_file_ext}")

                # Relocate processed spreadsheet
                if not rehearse:
                    os.rename(processed_file_path, new_processed_file_path)
                print(f"\t\tmv {processed_file_path} to {new_processed_file_path}")

                # Add new processed file path to spreadsheet record
                if not rehearse:
                    sql = "UPDATE spreadsheets SET file_path = ? WHERE id = ?"
                    cursor.execute(sql, (new_processed_file_path, spreadsheet_id))
                    connection.commit()
                print(
                    f"\t\tUPDATE spreadsheets SET file_path = '{new_processed_file_path}' WHERE id = {spreadsheet_id}")

            else:
                if not processed_file_path:
                    termcolor.cprint(f"\t\tSpreadsheet {spreadsheet_id} missing processed spreadsheet reference", 'red')
                else:
                    termcolor.cprint(f"\t\tSpreadsheet {spreadsheet_id} missing processed spreadsheet file", 'red')

            print(180 * "-")
            relocated_files.extend([os.path.basename(uploaded_file_path), os.path.basename(processed_file_path)])

    # Handle remaining top level files
    print("")
    print("Handling those files not directly identifiable via the db...")
    pattern = re.compile('^(\d+)v(\d+)\.comparison.*$')
    for filename in os.listdir(upload_folder):

        filepath = os.path.join(upload_folder, filename)

        # Skip over directories
        if os.path.isdir(filepath):
            continue

        # If the file was supposed to have been relocated, note it and bypass it.  Skip for rehearse since that doesn't
        # really change anything.
        if filepath in relocated_files:
            if not rehearse:
                termcolor.cprint(f"\tFile {filepath} should have been relocated!", 'red')
            continue
        print(180 * "-")

        # Look for comparison files
        print(f"Evaluating {filepath}")
        result = re.match(pattern, filename)

        if result:

            # Got a comparison file but do the related spreadsheets still exist?  If so, do not move it anywhere.
            sql = 'SELECT user_id FROM spreadsheets WHERE id = ?'
            cursor.execute(sql, (result.group(1),))
            user_id = cursor.fetchone()
            if user_id:
                user_id = user_id[0]
            else:
                termcolor.cprint(f"\tSpreadsheet id {result.group(1)} no longer exists for {filename}", 'red')
                continue
            cursor.execute(sql, (result.group(2),))
            user_id_repeat = cursor.fetchone()
            if user_id_repeat:
                user_id_repeat = user_id_repeat[0]
            else:
                termcolor.cprint(f"\tSpreadsheet id {result.group(2)} no longer exists for {filename}", 'red')
                continue

            # Check if the spreadsheets are both owned by the same user.  If not, do not move the comparison file
            if user_id != user_id_repeat:
                termcolor.cprint(f"\tDifferent users ({user_id},{user_id_repeat}) own the different spreadsheets"
                                 f" ({result.group(1), result.group(2)}) in {filename}.  No action taken.", 'red')
                continue
            else:
                user_folder = os.path.join(upload_folder, f"user_{user_id}")

                # Create a comparisons folder for the user if needed
                comparison_folder = os.path.join(user_folder, "comparisons")
                if not os.path.exists(comparison_folder):
                    if not rehearse:
                        os.makedirs(comparison_folder, exist_ok=True)
                    print(f"\tMkdir - {comparison_folder}")

                # Relocate the comparisons file
                new_filepath = os.path.join(comparison_folder, filename)
                if not rehearse:
                    os.rename(filepath, new_filepath)
                print(f"\tmv {filepath} to {new_filepath}")

        else:
            # A non-comparison file with no reference
            termcolor.cprint(f"\tFile {filepath} has no owner.  May be legecy data.", 'red')

    connection.close()


if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    DATABASE_FILE = os.environ['DATABASE_FILE']
    DATABASE_FOLDER = os.environ.get('DATABASE_FOLDER', '')
    if DATABASE_FOLDER:
        DATABASE_FOLDER += os.sep
    DATABASE = DATABASE_FOLDER + DATABASE_FILE
    migrate(True, DATABASE)
