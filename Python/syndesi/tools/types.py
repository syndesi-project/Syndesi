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