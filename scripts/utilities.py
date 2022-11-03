"""
Utilities file
"""
from os.path import basename, getmtime, join, dirname, exists
import pickle



def replace_str(text_in : str, replace : dict):
    """
    Replace each occurence of a key in a text and return it
    
    Parameters
    ----------
    text_in : str
        Path to template file
    replace : dict
        Dictionary of keys and data to replace
    force : bool
        Force replace the file (even if there aren't any modifications to it)
    """
    output = text_in
    for key, rep in replace.items():
        if not f">>>{key}<<<" in output:
            raise ValueError(f"Missing key '{key}' from text")
        output = output.replace(f">>>{key}<<<", rep)
    return output

def replace(template_file : str, output_file : str, replace : dict, enable : bool):
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
    enable : bool
        Enable (True) or disable (False) the replacement
    """
    if enable:
        with open(template_file, 'r', encoding='utf-8') as template_file_handler:
            template = template_file_handler.read()
            try:
                output = replace_str(template, replace)
            except ValueError as e:
                raise ValueError(f"{e} ({template_file}")
                
            with open(output_file, 'w', encoding='utf-8') as output_file_handler:
                print(f"Write file {basename(output_file)}")
                output_file_handler.write(output)
    else:
        print(f"No change to file {basename(output_file)}")

class ChangeEvaluator:
    def __init__(self, base_files, store_file):
        """
        Utility class to determine whether or not a file should be updated or not
        based on any change of its template or the command file

        Parameters
        ----------
        base_files : [str]
            Master files paths, if any change is detected in these files, all of the output files will be updated
        store_file : str
            Path to the store file that will remember the edit date
        """
        self._store_file = store_file
        # Load the date file
        if exists(self._store_file):
            with open(self._store_file, 'rb') as f:
                self._store_file_content = pickle.load(f)
        else:
            self._store_file_content = {}

        self._any_master_file_change = False
        for b in base_files:
            key = basename(b)
            if key in self._store_file_content:
                # The master file has been stored
                if self._store_file_content[key] != getmtime(b):
                    # The master file has been changed
                    self._store_file_content[key] = getmtime(b)
                    self._any_master_file_change = True
            else:
                # Create en entry for this master file
                self._store_file_content[key] = getmtime(b)
                self._any_master_file_change = True

    def evaluate(self, *args):
        """
        Evaluate if the template file has been changed or not

        Parameters
        ----------
        file1, file2, ... : strs
            Template files paths

        Returns
        -------
        output : bool
            True if the file has changed (or if any of the master files have been changed). False otherwise

        
        """
        output = False
        if self._any_master_file_change:
            # If any master file have been changed, no need to go further
            output = True
        else:
            for f in args:
                key = basename(f)
                if key in self._store_file_content:
                    # There's an entry for this file
                    if self._store_file_content[key] == getmtime(f):
                        # No change
                        pass
                    else:
                        # There is a change
                        self._store_file_content[key] = getmtime(f)
                        output = True
                        break
                else:
                    # The key isn't created, creating it
                    self._store_file_content[key] = getmtime(f)
                    output = True
                    break
        return output

    def store(self):
        """
        Store the change dates of all the files
        """
        with open(self._store_file, 'wb') as f:
            pickle.dump(self._store_file_content, f)



