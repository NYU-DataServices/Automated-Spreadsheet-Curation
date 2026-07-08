import csv
import os
import re
from abc import ABC

from Test import Test
from validators import _validate_kwarg_type, _validate_regex_kwarg


class File(Test, ABC):
    def __init__(self,):

        # Initialize the test
        Test.__init__(self,)

    def set_positional(self, wb_path):
        if not isinstance(wb_path, str):
            raise ValueError("wb_path must be a string")
        self.wb_path = wb_path


class File_Name(File, ABC):
    def __init__(self,):

        # Initialize the test
        File.__init__(self,)

    
    def set_positional(self, wb_path):
        File.set_positional(self, wb_path)

        # Save the filename
        self.filename = os.path.basename(self.wb_path)


        
class File_Name_Length(File_Name):
    def __init__(self, *, min_length=5, max_length=32):

        File_Name.__init__(self,)
        _validate_kwarg_type(self.name, "min_length", min_length, int)
        _validate_kwarg_type(self.name, "max_length", max_length, int)
        if min_length < 0 or max_length < 0:
            raise ValueError(f"{self.name}: `min_length` and `max_length` must be >= 0.")
        if min_length >= max_length:
            raise ValueError(
                f"{self.name}: `min_length` ({min_length}) must be less than "
                f"`max_length` ({max_length})."
            )
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, wb_path):
        File_Name.set_positional(self, wb_path)

        # If length is greater than max_length.
        if len(self.filename) > self.max_length:
            # The test failed
            self.status = False
            # Add an issue "location = filename": "contents of filename"
            self.issues["filename"] = self.filename
            # Set message
            self.message = f"Filename is > {self.max_length} characters"
        elif len(self.filename) <= self.min_length:
            self.status = False
            self.issues["filename"] = self.filename
            self.message = f"Filename is < {self.min_length} characters"
        else:
            # The test passed
            self.status = True
            # Set message
            self.message = f"Filename is < {self.max_length} characters"


class File_Name_Whitespace(File_Name):
    def __init__(self,):
        # Initialize the test
        File_Name.__init__(self,)

    def validate(self, wb_path):
        File_Name.set_positional(self, wb_path)

        # detect whitespace in filename
        # search returns None if no match is found, else Match object
        if re.search(r"\s", self.filename) is not None:

            # The test failed
            self.status = False

            # Add an issue
            self.issues["filename"] = self.filename
        Test.validate(self, "Filename contains whitespace", "Filename does not contain whitespace")

class File_Name_Final(File_Name):
    def __init__(self,):
        # Initialize the test named filename_final
        File_Name.__init__(self,)

    def validate(self, wb_path):
        File_Name.set_positional(self, wb_path)

        # If filename contains 'final'
        if "final" in self.filename.lower():
            self.status = False

            self.issues["filename"] = self.filename

            self.message = "Filename contains 'final'"
        else:
            self.status = True
            self.message = "Filename does not contain 'final'"
    
class File_Name_Word_Separation(File_Name):
    def __init__(self,):
        # Initialize the test named filename_word_separation
        File_Name.__init__(self,)

    def validate(self, wb_path):
        File_Name.set_positional(self, wb_path)

        # Detect combo of camel case, underscore, and dash in filename
        # Expressions work even if there are whitespace in the filename
        # camel case: capital letters in the middle of words
        camel_case = re.search(r'[a-z][A-Z]', self.filename) is not None
        underscore = "_" in self.filename
        dash = "-" in self.filename

        # If more than one are true
        if sum([camel_case, underscore, dash]) > 1:
            self.status = False
            self.issues["filename"] = self.filename
            self.message = "Filename mixes camel case, underscores, and dashes"
        else:
            self.status = True
            self.message = "Filename does not mix camel case, underscores, and dashes"

class File_Name_Special_Characters(File_Name):
    def __init__(self, *,
                 special_char_pattern=r"[!@#$%^&*()+=\[\]{};:'\"|\\,<>\?/]"):
        File_Name.__init__(self,)
        self.special_char_pattern = _validate_regex_kwarg(
            self.name, "special_char_pattern", special_char_pattern
        )

    def validate(self, wb_path):
        File_Name.set_positional(self, wb_path)

        spec_char = re.search(self.special_char_pattern, self.filename)
        
        # If there was a special character
        if spec_char:
            # The test failed
            self.status = False

            # Add an issue
            self.issues["filename"] = spec_char.group(0)

            self.message = "Filename contains special characters"
        else:
            self.status = True
            self.message = "Filename does not contain special characters"
        

class File_Encoding(File):
    def __init__(self, *, valid_encoding="utf-8"):
        
        File.__init__(self,)
        _validate_kwarg_type(self.name, "valid_encoding", valid_encoding, str)
        self.valid_encoding = valid_encoding
    
    def validate(self, wb_path):
        File.set_positional(self, wb_path)
        self.file_extension = os.path.splitext(self.wb_path)[1].lower()
        
        # Only check encoding for text-based files (CSV, not Excel)
        if self.file_extension == ".xlsx" or self.file_extension == ".xls":
            # Excel files are binary ZIP archives, encoding check doesn't apply
            self.status = True
            self.message = "Encoding check skipped for Excel files (binary format)"
            self.is_run = True
            return
        
        
        # For CSV and other text files, check encoding
        try:
            with open(self.wb_path, 'rb') as f:
                # Read the file content as a list of lines in bytes
                lines_bytes = f.readlines()
                # Try to decode each line as UTF-8
                for row_num, line in enumerate(lines_bytes):
                    text = line.decode(self.valid_encoding, errors='replace')

                    # Check to see if the official replacement character was used
                    if '\ufffd' in text:
                        self.issues[f"row {row_num}"] = text
                        
        except Exception as e:
            # Handle other exceptions (e.g., file not found)
            self.status = False
            self.issues["file"] = f"Error reading file: {str(e)}"
            self.message = f"Error checking file encoding: {str(e)}"
        
        # Pass issues and messages forward
        Test.validate(self, f"File encoding is not {self.valid_encoding}", f"File encoding is {self.valid_encoding}")

# Compare the text file extension with the delimiter
class File_Delimiter(File):

    def __init__(self, *, valid_delimiter_pairs=[(",",".csv"),("\t",".tsv")]):
        # Initialize the test
        File.__init__(self,)
        self.valid_delimiter_pairs=valid_delimiter_pairs
    def validate(self, wb_path):
        File.set_positional(self, wb_path)
        self.file_extension = os.path.splitext(self.wb_path)[1].lower()
        
        # Only check delimiter for text-based files (CSV, not Excel)
        if self.file_extension == ".xlsx" or self.file_extension == ".xls":
            # Excel files are binary ZIP archives, delimiter check doesn't apply
            self.status = True
            self.message = "Delimiter check skipped for Excel files (binary format)"
            self.is_run = True
            return
        
        
        # For CSV and other text files, use csv sniffer to figure out delimiter
        try:
            with open(self.wb_path, 'r') as f:
                delimiter = csv.Sniffer().sniff(f.read(5000)).delimiter
                #simplify to be just an if statement
                #if (delimiter == ',' and file_extension != '.csv') or (delimiter == '\t' and file_extension != ".tsv"):
                if (delimiter, self.file_extension) not in self.valid_delimiter_pairs:
                    self.issues["file"] = f"delimiter: {delimiter} and extension: {self.file_extension}"

                #look into way to not interpret \t to an actual tab

        except Exception as e:
            # Handle other exceptions (e.g., file not found)
            self.status = False
            self.issues["file"] = f"Error reading file: {str(e)}"
            self.message = f"Error checking delimiter: {str(e)}"
        
        # Pass issues and messages forward
        Test.validate(self, f"File delimiter and file extension don't match", f"File delimiter matches extension")
