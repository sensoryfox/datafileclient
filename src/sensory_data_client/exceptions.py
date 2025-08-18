class DataClientError(Exception):
    """Base class."""


class DatabaseError(DataClientError):
    pass
class NotFoundError(DataClientError):
    pass


class MinioError(DataClientError):
    pass
class ESError(DataClientError):
    pass


class DocumentNotFoundError(DataClientError):
    pass