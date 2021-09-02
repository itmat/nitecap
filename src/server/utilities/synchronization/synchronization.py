#!/usr/bin/env python

import boto3
import functools
import os

print = functools.partial(print, flush=True)

s3 = boto3.resource("s3")

source_bucket_name = os.environ["SOURCE_BUCKET_NAME"]
destination_bucket_name = os.environ["SPREADSHEET_BUCKET_NAME"]

for object in s3.Bucket(destination_bucket_name).objects.all():
    print("Deleting object", object.key)
    object.delete()

for object in s3.Bucket(source_bucket_name).objects.all():
    print("Copying object", object.key)
    s3.meta.client.copy(
        CopySource={"Bucket": source_bucket_name, "Key": object.key},
        Bucket=destination_bucket_name,
        Key=object.key,
    )
