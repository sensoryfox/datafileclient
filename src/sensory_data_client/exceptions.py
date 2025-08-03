class DataClientError(Exception):
    """Base class."""


class DatabaseError(DataClientError):
    pass


class MinioError(DataClientError):
    pass


class DocumentNotFoundError(DataClientError):
    pass