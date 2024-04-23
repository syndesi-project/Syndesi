DEFAULT_ATTRIBUTE_FLAG_NAME = '_is_default'


def default_argument(instance):
    setattr(instance, DEFAULT_ATTRIBUTE_FLAG_NAME, True)
    return instance

def is_default_argument(instance):
    return hasattr(instance, DEFAULT_ATTRIBUTE_FLAG_NAME)
        
