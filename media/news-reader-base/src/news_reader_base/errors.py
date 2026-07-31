"""Exception hierarchy with CLI exit codes.

Each reader skill subclasses ReaderError with its own concrete name (FTError,
NYTError, WSJError) so `except` blocks remain source-specific.
"""
from __future__ import annotations


class ReaderError(Exception):
    exit_code = 1
    code = "ERROR"


class SessionExpiredError(ReaderError):
    exit_code = 2
    code = "SESSION_EXPIRED"


class NotFoundError(ReaderError):
    exit_code = 3
    code = "NOT_FOUND"


class UpstreamError(ReaderError):
    exit_code = 4
    code = "NETWORK"


def create_reader_errors(source_name: str):
    """
    Dynamically create source-specific error classes that inherit from Base errors.
    Example: create_reader_errors("FT") -> { "FTError": ..., "FTSessionExpiredError": ... }
    """
    base = ReaderError
    
    # Custom base for this source
    source_err_name = f"{source_name}Error"
    source_err = type(source_err_name, (base,), {"__doc__": f"Base error for {source_name}"})
    
    # Source-specific subclasses
    errors = {
        source_err_name: source_err,
        f"{source_name}SessionExpiredError": type(f"{source_name}SessionExpiredError", (source_err, SessionExpiredError), {}),
        f"{source_name}NotFoundError": type(f"{source_name}NotFoundError", (source_err, NotFoundError), {}),
        f"{source_name}UpstreamError": type(f"{source_name}UpstreamError", (source_err, UpstreamError), {}),
    }
    return errors

