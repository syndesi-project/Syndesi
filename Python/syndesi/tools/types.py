try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

def is_byte_instance(X):
    """
    Check if the given X is an instance of bytearray or bytes
    
    Parameters
    ----------
    X : any
    
    Returns
    -------
    result : bool
    """
    result = isinstance(X, (bytearray, bytes))
    return result

def assert_byte_instance(*args):
    """
    Checks if the given argument(s) is of type bytes
    or bytes. A TypeError is raised if it isn't the case

    Parameters
    ----------
    args
    """
    for arg in args:
        if not is_byte_instance(arg):
            raise TypeError(f"Variable {arg} should be of type bytes or bytes")

def is_number(X):
    """
    Check if the given X is an instance of int or float
    
    Parameters
    ----------
    X : any

    Returns
    -------
    result : bool 
    """
    result = isinstance(X, (int, float, np.number) if HAS_NUMPY else (int, float))
    return result

def assert_number(*args):
    """
    Checks if the given argument(s) is a number.
    A TypeError is raised if it isn't the case

    Parameters
    ----------
    args
    """
    for arg in args:
        if not is_number(arg):
            raise TypeError(f"Variable {arg} should be a number")

def to_bytes(data):
    """
    Convert data to bytes array
    bytearray -> bytearray
    bytes -> bytes
    str -> bytes (UTF-8 encoding by default)
    """
    if isinstance(data, bytes):
        return data
    elif isinstance(data, str):
        return data.encode('utf-8')
    else:
        raise ValueError(f"Invalid data type : {type(data)}")





