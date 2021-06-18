import os
import time
import sqlite3
import shutil
import logging

logger = logging.getLogger(__name__)
def backup(dbfile):
    db_backup_folder = os.environ['DB_BACKUP_FOLDER']
    if not os.path.isdir(db_backup_folder):
        raise Exception(f"Database backup folder, {db_backup_folder} does not exist")

    backup_file = os.path.join(db_backup_folder, os.path.basename(dbfile) +
                               time.strftime("-%Y%m%d-%H%M%S"))

    connection = sqlite3.connect(dbfile)
    cursor = connection.cursor()

    # Lock database before making a backup
    cursor.execute('begin immediate')

    # Make new backup file
    shutil.copyfile(dbfile, backup_file)
    logger.info(f"Creating {backup_file}...")

    # Unlock database
    connection.rollback()

def clean_backups():

    logger.info("Cleaning up old backups")
    db_backup_folder = os.environ['DB_BACKUP_FOLDER']
    db_backup_limit = os.environ['DB_BACKUP_LIMIT']

    for filename in os.listdir(db_backup_folder):
        backup_file = os.path.join(db_backup_folder, filename)
        if os.stat(backup_file).st_ctime < (time.time() - int(db_backup_limit) * 86_400):
            if os.path.isfile(backup_file):
                os.remove(backup_file)
                logger.info(f"Deleting {backup_file}...")
