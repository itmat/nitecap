ALLOWED_EXTENSIONS = frozenset(['txt', 'csv', 'xlsx', 'gz'])
ALLOWED_MIME_TYPES = frozenset(['text/plain', 'text/csv', 'application/vnd.ms-excel',
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                'application/x-gzip', 'application/gzip'])
COMPRESSED_MIME_TYPES = frozenset(['application/x-gzip', 'application/gzip'])
EXCEL_MIME_TYPES = frozenset(['application/vnd.ms-excel',
                              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])