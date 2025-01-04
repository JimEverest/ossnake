from typing import Optional

class OSSError(Exception):
    """Base class for all OSS exceptions."""
    pass

class OSSDriverError(OSSError):
    """Base class for driver-specific exceptions."""
    pass

class ConnectionError(OSSError):
    """Exception raised for connection errors."""
    pass

class AuthenticationError(OSSError):
    """Exception raised for authentication errors."""
    pass

class ObjectNotFoundError(OSSError):
    """Exception raised when an object is not found."""
    pass

class BucketNotFoundError(OSSError):
    """Exception raised when a bucket is not found."""
    pass

class UploadError(OSSError):
    """Exception raised for upload errors."""
    pass

class DownloadError(OSSError):
    """Exception raised for download errors."""
    pass

class TransferError(OSSError):
    """Exception raised for general transfer errors."""
    pass

class BucketError(OSSError):
    """Exception raised for bucket-related errors."""
    pass

class GetUrlError(OSSError):
    """Exception raised for errors in getting file URL."""
    pass

class DeleteError(OSSError):
    """Exception raised for delete errors."""
    pass 