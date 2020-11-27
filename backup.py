#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Backup PostgreSQL database to Yandex Object Storage, that has S3 compatible
API.
"""
import datetime
import os
from pathlib import Path

import boto3
import pytz
from dotenv import load_dotenv
from termcolor import colored

load_dotenv()

DB_HOSTNAME = os.getenv("DB_HOSTNAME", "localhost")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
BACKUP_KEY_PUB_FILE = os.getenv("BACKUP_KEY_PUB_FILE")
TIME_ZONE = os.getenv("TIME_ZONE", "Europe/Moscow")
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
PERIODICITY = os.getenv("PERIODICITY")

DB_FILENAME = "/tmp/backup_db.sql.gz.enc"

CHECK_DATE = {
    'daily': lambda x: x - datetime.timedelta(hours=23),
    'weekly': lambda x: x - datetime.timedelta(days=6),
    'monthly': lambda x: x - datetime.timedelta(weeks=3),
    'yearly': lambda x: x - datetime.timedelta(days=360)
}


def say_hello():
    print(colored("Hi! This tool will dump PostgreSQL database, compress \n"
        "and encode it, and then send to Yandex Object Storage.\n", "cyan"))


def get_now_datetime_str():
    now = datetime.datetime.now(pytz.timezone(TIME_ZONE))
    return now.strftime('%Y-%m-%d__%H-%M-%S'), now


def check_key_file_exists():
    if not Path(BACKUP_KEY_PUB_FILE).is_file():
        exit(
            f"Public encrypt key ({BACKUP_KEY_PUB_FILE}) "
            f"not found. If you have no key – you need to generate it. "
            f"You can find help here: "
            f"https://www.imagescape.com/blog/2015/12/18/encrypted-postgres-backups/"
        )


def check_last_backup():
    _, now = get_now_datetime_str()
    dumps = get_s3_instance().list_objects(Bucket=f'{S3_BUCKET_NAME}.{PERIODICITY}').get('Contents')
    if dumps:
        dumps.sort(key=lambda x: x['LastModified'])
        last_backup_filename = dumps[-1]
        if CHECK_DATE['daily'](now) < last_backup_filename['LastModified']:
            exit('Early to do backup.')
    print('Time to do backup.')


def dump_database():
    print("Preparing database backup started")
    dump_db_operation_status = os.WEXITSTATUS(os.system(
        f"PGPASSWORD={DB_PASSWORD} pg_dump -p 5432 -h {DB_HOSTNAME} -U {DB_USER} {DB_NAME} | gzip -c --best | \
        openssl smime -encrypt -aes256 -binary -outform DEM \
        -out {DB_FILENAME} {BACKUP_KEY_PUB_FILE}"
    ))
    if dump_db_operation_status != 0:
        exit(f"Dump database command exits with status "
             f"{dump_db_operation_status}.")
    print("DB dumped, archieved and encoded")


def get_s3_instance():
    session = boto3.session.Session(
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY
    )
    return session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net'
    )


def delete_old_backup():
    print("Starting delete old backup from Object Storage")
    backups_from_storage = []
    backups = get_s3_instance().list_objects(Bucket=f'{S3_BUCKET_NAME}.{PERIODICITY}').get('Contents')
    if not backups:
        print(f"Not old backups")
    else:
        for key in backups:
            backups_from_storage.append([key['LastModified'], key['Key']])
        backups_from_storage = sorted(backups_from_storage, key=lambda x: x[0], reverse=True)
        if len(backups_from_storage) > 4:
            for_delete = []
            for i in range(len(backups_from_storage) - 1, 3, -1):
                for_delete.append({'Key': backups_from_storage[i][1]})
            get_s3_instance().delete_objects(Bucket=f'{S3_BUCKET_NAME}.{PERIODICITY}', Delete={'Objects': for_delete})
        print("Deleted")


def upload_dump_to_s3():
    print("Starting upload to Object Storage")
    str_date, _ = get_now_datetime_str()
    get_s3_instance().upload_file(
        Filename=DB_FILENAME,
        Bucket=f'{S3_BUCKET_NAME}.{PERIODICITY}',
        Key=f'{PERIODICITY}-db-{str_date}.sql.gz.enc'
    )
    print("Uploaded")


def remove_temp_files():
    os.remove(DB_FILENAME)
    print(colored("That's all!", "green"))


if __name__ == "__main__":
    say_hello()
    check_key_file_exists()
    check_last_backup()
    dump_database()
    delete_old_backup()
    upload_dump_to_s3()
    remove_temp_files()
