def is_instance_of_any(X, *types):
    """
    Checks if the given X is an instance of any of the provided types.
    
    Parameters
    ----------
    X : any
    types : Variable number of types to check against

    Returns
    -------
    result : bool
        True if value is an instance of any of the types, False otherwise
    """
    result = any(isinstance(X, t) for t in types)
    return result

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
    result = is_instance_of_any(X, bytearray, bytes)
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
    result = is_instance_of_any(X, int, float)
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


