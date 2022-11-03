"""
Utilities file
"""
from os.path import basename

def replace_str(text_in : str, replace : dict):
    """
    Replace each occurence of a key in a text and return it
    
    Parameters
    ----------
    text_in : str
        Path to template file
    replace : dict
        Dictionary of keys and data to replace
    """
    output = text_in
    for key, rep in replace.items():
        if not f">>>{key}<<<" in output:
            raise ValueError(f"Missing key '{key}' from text")
        output = output.replace(f">>>{key}<<<", rep)
    return output

def replace(template_file : str, output_file : str, replace : dict):
    """
    Replace each occurence of a key in template file with replace_width element
    and save to output_file
    
    Parameters
    ----------
    template_file : str
        Path to template file
    output_file : str
        Path to output file
    replace : dict
        Dictionary of keys and data to replace
    """
    with open(template_file, 'r', encoding='utf-8') as template_file_handler:
        template = template_file_handler.read()
        try:
            output = replace_str(template, replace)
        except ValueError as e:
            raise ValueError(f"{e} ({template_file}")
            
        with open(output_file, 'w', encoding='utf-8') as output_file_handler:
            print(f"Write file {basename(output_file)}")
            output_file_handler.write(output)