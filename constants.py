ALLOWED_EXTENSIONS = frozenset(['.txt', '.tsv', '.csv', '.xls', '.xlsx', '.gz'])
ALLOWED_MIME_TYPES = frozenset(['text/plain', 'text/csv', 'application/vnd.ms-excel',
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                'application/x-gzip', 'application/gzip', 'application/csv'])
COMPRESSED_MIME_TYPES = frozenset(['application/x-gzip', 'application/gzip'])
EXCEL_MIME_TYPES = frozenset(['application/vnd.ms-excel',
                              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
COMMA_DELIMITED_EXTENSIONS = frozenset(['.csv'])
