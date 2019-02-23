ALLOWED_EXTENSIONS = frozenset(['txt', 'csv', 'xlsx', 'gz'])
ALLOWED_MIME_TYPES = frozenset(['text/plain', 'text/csv', 'application/vnd.ms-excel',
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                'application/x-gzip'])
COMPRESSED_MIME_TYPES = frozenset(['application/x-gzip'])