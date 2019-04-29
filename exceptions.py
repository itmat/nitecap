class NitecapException(Exception):

    @property
    def message(self):
        return getattr(super, 'message', 'A Nitecap administrator will look into the error')

