import pandas as pd
import pprint
from abc import ABC, abstractmethod
import re
import json
# from datetime import datetime as dt
from copy import deepcopy
import os
import inspect
import zipfile
import csv

from validators import _validate_kwarg_type, _validate_optional_str_list, _validate_regex_kwarg
from HasDependency import Has_Dependency
from Test import Test
from Cell import Cell, Cell_Aggregate_Row, Cell_Dates, Cell_Missing_Value_Text, Cell_Newlines_Tabs, Cell_Number_Space, Cell_Question_Mark_Only, Cell_Scientific_Notation, Cell_Special_Characters, Cell_Units, Cell_Untrimmed_White_Space, Cell_White_Space_Only
from Sheet import Sheet_Empty, Sheet_Multi_Table, Sheet_Upper_Left_Corner
from Header import Header, Header_Date, Header_Duplicates, Header_First_Char, Header_ID, Header_Length, Header_Mixed_Datatypes, Header_Space, Header_Special_Characters, Header_Untrimmed_White_Space, Header_Word_Separation


# ISO Strict OOXML uses purl.oclc.org namespaces; openpyxl (pandas' default xlsx engine) does not.
_STRICT_OOXML_MARKER = "purl.oclc.org/ooxml"


def _is_strict_open_xml_spreadsheet(path):
    """Return True if path is a .xlsx package using Strict OOXML (not transitional SpreadsheetML)."""
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            try:
                with zf.open("xl/workbook.xml") as f:
                    head = f.read(65536)
            except KeyError:
                return False
    except (OSError, zipfile.BadZipFile):
        return False
    return _STRICT_OOXML_MARKER in head.decode("utf-8", errors="ignore")


def _discover_tests(test_level = "all", to_run = None, to_skip = None):
    """
    Find all concrete (non-abstract) Test subclasses whose __init__ takes only
    `ws` as a required positional arg.  These are the per-sheet tests that
    Test_Suite queues automatically.
    """

    # Save either to_run or to_skip as a set to filter the tests
    if to_run is not None:
        to_filter = set(to_run)
        is_included = True
    elif to_skip is not None:
        to_filter = set(to_skip)
        is_included = False
    else:
        # Else we are not including the empty set
        to_filter = set()
        is_included = False



    # List of all available tests
    all_tests = dict()

    # List of classes to assess
    to_visit = list(Test.__subclasses__())

    # Classes we've already assessed
    # Prevents infinite loops from diamond dependency graphs
    visited = set()

    # While there are classes to assess
    while to_visit:

        # Get the first class
        cls = to_visit.pop(0)

        # If the class has already been assessed, skip it
        if cls in visited:
            # Skip it
            continue

        # Add the class to the list of visited classes
        visited.add(cls)

        # Add the subclasses of the class to the list of classes to assess
        to_visit.extend(cls.__subclasses__())

        # If the class is abstract
        if inspect.isabstract(cls):
            # Skip it
            continue
        
        # Else the class is not abstract
        else:

            # Add the test_name to the list of all tests
            all_tests[cls.__name__.lower()] = cls
    
    

    # Verify that to_filter contains valid test names
    for test_name in to_filter:
        # If the test name is not in the list of all tests
        if test_name not in all_tests:
            # Raise an error
            raise ValueError(f"Invalid test name: {test_name}")


    # Initialize the result list of tests
    result = {}

    # For each test in the list of all tests
    for test_name,test_cls in all_tests.items():

        # If test_level
        if test_level == "all" or test_level in test_name:

            # Apply the filter
            if test_name in to_filter and is_included:
                # Add the class to the list of tests
                result[test_name] = test_cls
            elif test_name not in to_filter and not is_included:
                # Add the class to the list of tests
                result[test_name] = test_cls
            else:
                # Skip the class
                continue
            
    # Return the dictionary of tests
    return result


class Test_Suite():

    # results is a dict of sheet names, each containing a dict of test names and their results
    # to_run is a list of test classes to run on each sheet
    # wb_path is the path to the workbook
    # wb is a dictionary of pandas dataframes, each representing a sheet in the workbook

    def __init__(self, wb_path, to_run=None, to_skip=None, config_path=None):
        self.wb_path = wb_path

        # --- load config from JSON (optional) ---
        self.config = {}
        if config_path is not None:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except FileNotFoundError:
                print(f"Warning: Config file '{config_path}' not found. Using defaults.")
            except json.JSONDecodeError as e:
                print(f"Warning: Config file '{config_path}' has invalid JSON: {e}. Using defaults.")


        # --- validate to_run / to_skip mutual exclusivity ---
        if to_run is not None and to_skip is not None:
            raise ValueError("Cannot specify both to_run and to_skip. Use one or neither.")
        
        to_filter = to_run if to_run else to_skip
        if to_filter:
            if not isinstance(to_filter, list):
                raise ValueError("to_run or to_skip must be a list (of test names).")
            if not all(isinstance(test_name, str) for test_name in to_filter):
                raise ValueError("to_run or to_skip lists must be of test names (strings).")


        # Discover all the tests to run
        all_tests = _discover_tests(test_level = "all", to_run = to_run, to_skip = to_skip)

        # Verify that config only contains valid test names
        for test_name in self.config.keys():
            if test_name not in all_tests:
                raise ValueError(f"Invalid test name in config: {test_name}. Using specified tests from to_run or to_skip, allowed test names are: {list(all_tests.keys())}.")


        # Initialize the results dict,
        # levels:  [sheet_name] -> [test_name] -> [test_object]
        self.results = dict()
        # Initialize the results dict for the file
        self.results["file"] = dict()



        # First the file level tests
        self.file_tests = {t_name: self._create_test(t_cls) for t_name, t_cls in all_tests.items() if t_name.startswith("file")}


        # --- File encoding test ---
        # Must happen before loading pandas dataframe

        # First check if the file is UTF-8 encoded
        if "file_encoding" in self.file_tests:
            encoding_test = self.file_tests["file_encoding"]
            encoding_test.validate(self.wb_path)
            encoding = encoding_test.valid_encoding
            self.results["file"]["file_encoding"] = encoding_test

            # Remove the file encoding test from remaining tests to run
            self.file_tests.pop("file_encoding")
        else:
            # Skip the file encoding test, default to UTF-8
            encoding = "utf-8"
            pass


        # Extract file extension from wb_path
        file_extension = os.path.splitext(wb_path)[1]


        # If the file extension is .xlsx, read the file as an excel file
        if file_extension == ".xlsx":
            if _is_strict_open_xml_spreadsheet(wb_path):
                raise ValueError(
                    f"File {wb_path} is a Strict Open XML Spreadsheet (ISO 29500), not a standard "
                    "Excel workbook. This package reads standard .xlsx files only. Open the file in "
                    "Excel or LibreOffice Calc and use Save As to save as a normal Excel workbook "
                    "(.xlsx), then try again."
                )
            self.wb = pd.read_excel(
                io = wb_path, # The file path
                dtype = "str", # Parse all cells as strings, leaves the parsing to the tests
                sheet_name = None, # read all sheets returning a dict
                header = None, # Do not load the header at all
            )
        elif file_extension == ".csv" or file_extension == ".tsv":
            self.wb = pd.read_csv(
                wb_path, # The file path
                sep = None, # Automatically detect the separator
                engine = "python", # Enables sep=None and ensures no c engine.
                dtype = "str", # Parse all cells as strings, leaves the parsing to the tests
                header = None, # Do not load the header at all
                na_values = "", # Treat only empty cells as NA
                keep_default_na = False, # Do not keep default NA values
                encoding = encoding, # Read the file
                encoding_errors = "replace", # Replace invalid characters with ?
            )
            # Make the single sheet into a singleton dict to match excel format
            self.wb = {os.path.splitext(os.path.basename(wb_path))[0]: self.wb}
        else:
            raise ValueError(f"File {wb_path} has an invalid file extension: {file_extension}. Use '.xlsx', or '.csv'.  If you want to use '.xls', use conda to install xlrd and change the if statement above to allow xls.")


        # --- Check input arguments from config to tests
        
        
        # Initialize the sheet tests to check input arguments
        self.sheet_tests = {t_name: self._create_test(t_cls) for t_name, t_cls in all_tests.items() if t_name.startswith("sheet")}

        # Initialize the header tests to check input arguments
        self.header_tests = {t_name: self._create_test(t_cls) for t_name, t_cls in all_tests.items() if t_name.startswith("header")}

        # Initialize the cell tests to check input arguments
        self.cell_tests = {t_name: self._create_test(t_cls) for t_name, t_cls in all_tests.items() if t_name.startswith("cell")}


        # Set the first row to be headers no matter what
        def set_headers(df):
            # If empty
            if df.empty:
                # Just return
                return df
            else:
                cols = df.iloc[0]
                cols = cols.mask(cols.isna(), "Unnamed")
                df.columns = cols
                df = df[1:]
                df = df.reset_index(drop=True)

                return df

        if isinstance(self.wb, dict):
            # Get each dataframe in the dict
            self.wb = {name : set_headers(df) for name, df in self.wb.items()}
        else:
            self.wb = set_headers(self.wb)







    def _create_test(self, test_cls):
        """
        Instantiate a test, merging in any config overrides for its
        keyword-only parameters.  First creates with defaults to discover the
        test name, then re-creates with config overrides if any exist.
        """
        test_name = test_cls.__name__.lower()

        # Get the users config options for this test
        cfg = self.config.get(test_name, {})


        # Get the call signature of the tests
        sig = inspect.signature(test_cls.__init__)
        # The allowed options are the keyword-only parameters
        allowed = {
            name for name, p in sig.parameters.items()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        # Check for any invalid options provided by the user
        bad_options = {k: v for k, v in cfg.items() if k not in allowed}
        if bad_options:
            raise ValueError(f"Invalid options for test {test_name}: {bad_options}. Allowed options are: {allowed}.  See the README documentation for more information.")
        # Get the valid options provided by the user (which might be none)
        overrides = {k: v for k, v in cfg.items() if k in allowed}
        
        # Create the test with the valid options provided by the user
        test = test_cls(**overrides)
        return test


    def _validate_tests(self, tests, positional_args, other_dependencies = None):
        f"""
        Runs a list of tests with specified args.

        Args:
            tests: A list of test objects to run.
            positional_args: A list of positional arguments for all the tests.
            other_dependencies: (Not implemented) dict of completed dependencies, dep_name : completed_dep_test, to pass to the tests that are not already in the list of tests.
        """
        import traceback

        completed_tests = dict()
        finalized_tests = dict()
        queue = list(tests.values())
        skip_count = 0

        # While there are tests to run
        while len(queue) > 0:
            try:
                # Check we haven't skipped every test in the queue consecutively.
                # If so, no remaining test is currently runnable.
                if skip_count >= len(queue):
                    remaining_test_names = [t.name for t in queue]
                    raise RuntimeError(
                        f"Circular or unmet dependencies among remaining tests: {remaining_test_names}"
                    )

                # Get the first test
                t_obj = queue.pop(0)

                # Check if the test has dependencies
                if isinstance(t_obj, Has_Dependency):
                    fulfilled = {
                        dep_name: dep_test
                        for dep_name, dep_test in completed_tests.items()
                        if type(dep_test) in t_obj.dependencies
                    }

                    if len(fulfilled) < len(t_obj.dependencies):
                        # Add the test back to the queue
                        queue.append(t_obj)
                        # Increment the skip count
                        skip_count += 1
                        continue
                else:
                    # Fulfilled is empty
                    fulfilled = dict()

                # Validate the test
                try:
                    t_obj.validate(*positional_args, **fulfilled)
                    # Track the completed test
                    completed_tests[t_obj.name] = t_obj
                    finalized_tests[t_obj.name] = t_obj
                    # Reset the skip count because we've completed a test
                    skip_count = 0
                except Exception as e:
                    user_kwonly_args = self.config.get(t_obj.name, {})
                    print(
                        f"===========\n"
                        f"Warning: Runtime error while executing test.  Skipping and continuing with other tests where possible.\n"
                        f"sheet: {positional_args[1]}\n"
                        f"'{t_obj.name}'.\n"
                        f"  positional_args={positional_args}\n"
                        f"  user_keyword_only_args={user_kwonly_args}\n"
                        f"  error_type={type(e).__name__}\n"
                        f"  error_message={e}\n\n"
                        f"  traceback:\n{traceback.format_exc()}"
                        f"\n\n\n"
                    )
                    # Runtime-error tests are treated as not completed.
                    t_obj.status = None
                    t_obj.message = (
                        f"Test did not complete due to runtime error: {type(e).__name__}: {e}"
                    )
                    finalized_tests[t_obj.name] = t_obj
                    # We made progress by removing this test from the queue.
                    skip_count = 0

            except RuntimeError:
                remaining_test_names = [t.name for t in queue]
                print(
                    "Warning: Circular or unmet dependencies detected. "
                    "The following tests remained in the queue and will not be completed: "
                    f"{remaining_test_names}"
                )
                # Mark all remaining tests as not completed and stop this loop.
                for t_obj in queue:
                    t_obj.status = None
                    t_obj.message = (
                        "Test did not complete due to circular or unmet dependencies."
                    )
                    finalized_tests[t_obj.name] = t_obj
                break

        # Return all tests (completed + not completed)
        return finalized_tests



    def run(self):
        # --- file-level tests ---
        print("Running file-level tests")
        self.results["file"].update(
            self._validate_tests(self.file_tests, [self.wb_path]))

        print("Running sheet, header, and cell tests")
        remaining_tests = self.sheet_tests | self.header_tests | self.cell_tests

        for sheet, ws in self.wb.items():
            fresh_tests = deepcopy(remaining_tests)
            print(f"Running tests for sheet: {sheet}")
            self.results[sheet] = self._validate_tests(fresh_tests, [ws, sheet])

            
    # Print a report of the results
    def report(self):

        # For each sheet and its associated tests
        for sheet, tests in self.trimmed_results().items():
            # Add extra extra space between sheets
            print("\n\n" + 80 * "=")
            # Print the sheet name
            print(f"Sheet: {sheet}")
            # Add space
            print("\n")

            # For each tests applied to this sheet
            # trimmed_results is a dict of test names and their results
            for test_name, trimmed_result in tests.items():
                
                # Print the report for that test
                print(f"Test: {test_name}")
                print(f"Message: {pprint.pformat(trimmed_result['message'])}")
                print(f"Issues: {pprint.pformat(trimmed_result['issues'])}")

                # Add some space
                print("\n")

            

    # Trim the results to only include dict entries for failed tests
    def trimmed_results(self, stringify = False):
        
        # initialize the trimmed results dict
        trimmed_results = dict()

        # For each sheet and its associated tests
        for sheet, tests in self.results.items():


            # If any test has failed
            if not all([test.status for test in tests.values()]):

                # Add the sheet to the trimmed results
                trimmed_results[sheet] = dict()

                # For each test applied to this sheet
                for test_name, test in tests.items():

                    # If the test has failed
                    if not test.status:

                        # If strings needed instead of tuples
                        # This is because the keys are tuples of coordinates
                        # and cannot be saved as json
                        if stringify:
                            issues = {
                                str(key): val for key, val in test.issues.items()}
                        else:
                            issues = test.issues

                        # Add the test to the trimmed results
                        # with its status, message, and issues
                        trimmed_results[sheet][test_name] = {
                            "message": test.message,
                            "issues": issues
                        }
        
        # Return the trimmed results
        # This is a dict of sheet names, each containing a dict of test names and their results
        return trimmed_results

    # Save the results to a file
    def save(self, format="json", filename=None):
        import os
        from datetime import datetime as dt
        import json
        print("saving results to file")

        # By default, use "results/" as the folder
        results_folder = "results"
        if not os.path.exists(results_folder):
            os.makedirs(results_folder)

        # Get the base name of the file from wb_path (without folders)
        base_name = os.path.splitext(os.path.basename(self.wb_path))[0]
        # Add datetime and format to the output filename
        timestamp = dt.now().strftime("%Y-%m-%d_%H-%M-%S")
        default_filename = f"{base_name}_{timestamp}.{format}"

        # Full path to output file
        if filename is None:
            filename = os.path.join(results_folder, default_filename)

        if format == "json":
            with open(filename, "w") as f:
                json.dump(self.trimmed_results(stringify=True), f, default=str)
        elif format == "csv":

            rows = []
            # For each sheet and its associated tests
            for sheet, tests in self.trimmed_results().items():
                for test_name, test in tests.items():
                    issues = test["issues"]
                    if not issues:
                        # If no issues, optionally still record a "pass"/empty row
                        continue
                    row_count = len(issues)
                    # Prepare repeated/columnar values
                    paths     = [self.wb_path] * row_count
                    sheets    = [sheet] * row_count
                    test_names= [test_name] * row_count
                    messages  = [test["message"]] * row_count
                    locations, examples = zip(*issues.items())
                    for i in range(row_count):
                        rows.append({
                            "path": paths[i],
                            "sheet": sheets[i],
                            "test_name": test_names[i],
                            "message": messages[i],
                            "location": locations[i],
                            "example": examples[i]
                        })
            import pandas as pd  # ensure pd is imported
            df = pd.DataFrame(rows, columns=["path", "sheet", "test_name", "message", "location", "example"])
            df.to_csv(filename, mode="w", index=False, header=True)
        else:
            # Raise a ValueError
            raise ValueError("Invalid format. Use 'json' or 'csv'.")

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


# If run as a script
if __name__ == "__main__":

    # Create a test suite from the demo notebook
    suite = Test_Suite("demo.xlsx")
    
    # Run all the tests and outputs
    suite.run()
    suite.report()
    suite.save(format = "json")
    suite.save(format = "csv")