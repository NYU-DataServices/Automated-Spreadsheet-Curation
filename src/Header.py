import pandas as pd
import re
# from abc import ABC, abstractmethod

from validators import _validate_kwarg_type, _validate_optional_str_list, _validate_regex_kwarg
from Test import Test
from HasDependency import Has_Dependency
from Sheet import Sheet_Empty, Sheet_Upper_Left_Corner, Sheet_Multi_Table


class Header(Test, Has_Dependency):

    def __init__(self):
        Test.__init__(self)

        # This test depends on the grid edges test
        Has_Dependency.__init__(self, Sheet_Empty,Sheet_Upper_Left_Corner, Sheet_Multi_Table)

    def _handle_dependencies(self, sheet_empty, sheet_upper_left_corner, sheet_multi_table, fn):
        if sheet_empty.empty:
            self.handle_empty()
        elif sheet_multi_table.multi_table:
            self.handle_multi_table()
        else:
            self.headers = self.get_headers(sheet_upper_left_corner)
            self.ws = sheet_upper_left_corner.effective_ws
            fn(self.headers)


    def get_headers(self, sheet_upper_left_corner):
        # Check that the upper left corner test has been run
        self.check_input(sheet_upper_left_corner)

        return sheet_upper_left_corner.effective_ws.columns
    

class Header_Duplicates(Header):

    def __init__(self):

        # Initialize a headers test
        Header.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.detect_duplicates)

    def detect_duplicates(self, headers):
        duplicates = headers[headers.duplicated(keep = False)]
        if len(duplicates) > 0:
            for dup in duplicates.unique():
                    # Flag the location as an issue
                    self.issues[dup] = f"Repeated {(duplicates == dup).sum()} times"

        Test.validate(self, "Duplicate headers found", "All headers unique")


class Header_ID(Header):

    def __init__(self):
        Header.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.check_id)

    def check_id(self, headers):
        if headers[0] == "ID":
            self.issues[(0, headers[0])] = headers[0]

        Test.validate(self, "First header is ID", "First header is not ID")

class Header_Length(Header):
        
        def __init__(self, *, min_length=1, max_length=24):
            Header.__init__(self)
            _validate_kwarg_type(self.name, "min_length", min_length, int)
            _validate_kwarg_type(self.name, "max_length", max_length, int)
            if min_length < 0 or max_length < 0:
                raise ValueError(
                    f"{self.name}: `min_length` and `max_length` must be >= 0."
                )
            if min_length > max_length:
                raise ValueError(
                    f"{self.name}: `min_length` ({min_length}) must be <= "
                    f"`max_length` ({max_length})."
                )
            self.min_length = min_length
            self.max_length = max_length

        def validate(self, *ignore, **dependencies):
            self._handle_dependencies(**dependencies, fn=self.check_length)

        def check_length(self, headers):
            for idx, header in enumerate(headers):

                assert isinstance(header, str)

                # If bad length
                if len(header) < self.min_length or len(header) > self.max_length:
                    self.issues[(idx, header)] = header


            Test.validate(self, "Headers should be between 1 and 24 characters", "All headers have acceptable lengths")
                


class Header_First_Char(Header):
        
        def __init__(self):
            Header.__init__(self)

        def validate(self, *ignore, **dependencies):
            self._handle_dependencies(**dependencies, fn=self.check_first_char)

        def check_first_char(self, headers):
            for idx, header in enumerate(headers):

                assert isinstance(header, str)

                # If bad length
                if header[0].isdigit():
                    self.issues[(idx, header)] = header

            Test.validate(self, "Some headers start with a digit", "No headers start with digits")
                


class Header_Space(Header):
        
        def __init__(self):
            Header.__init__(self)

        def validate(self, *ignore, **dependencies):
            self._handle_dependencies(**dependencies, fn=self.check_space)

        def check_space(self, headers):
            for idx, header in enumerate(headers):

                assert isinstance(header, str)

                # If bad length
                if " " in header:
                    self.issues[(idx, header)] = header
                

            Test.validate(self, "Some headers have spaces", "No headers have spaces")

# Search for leading or trailing white space in headers

class Header_Untrimmed_White_Space(Header):
        
        def __init__(self):
            Header.__init__(self)

        def validate(self, *ignore, **dependencies):
            self._handle_dependencies(**dependencies, fn=self.check_headers_untrimmed_space)

        def check_headers_untrimmed_space(self, headers):
            for idx, header in enumerate(headers):

                assert isinstance(header, str)

                leading_trailing = re.findall(r'^\s|\s$', header)
                if len(leading_trailing) > 0:
                    self.issues[(idx, header)] = header
                

            Test.validate(self, "Leading or trailing white space in header",
            "No leading or trailing white space in header")
                
class Header_Word_Separation(Header):

    def __init__(self):
        Header.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.check_underscore_dash)

    def check_underscore_dash(self, headers):
        for idx, header in enumerate(headers):
            assert isinstance(header, str)

            # Detect captial letters in the middle of words
            camel_case = re.search(r'[a-z][A-Z]', header) is not None
            underscore =  "_" in header
            dash = "-" in header

        if sum([camel_case, underscore, dash]) > 1:
            self.issues["all headers"] = headers

            
        Test.validate(self, "Headers use mixture of camel case, underscores, and dashes", "Headers do not use a mixture of camel case, underscores and dashes")


class Header_Special_Characters(Header):
    def __init__(self, *,
                 special_char_pattern=r"[!@#$%^&*()+=\[\]{};:'\"|\\,<>\?/]"):
        Header.__init__(self)
        self.special_char_pattern = _validate_regex_kwarg(
            self.name, "special_char_pattern", special_char_pattern
        )

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.check_special_characters)

    def check_special_characters(self, headers):
        for idx, header in enumerate(headers):
            assert isinstance(header, str)
            if re.search(self.special_char_pattern, header):
                self.issues[(idx, header)] = header

        Test.validate(self, "Headers contain special characters", "Headers do not contain special characters")

class Header_Date(Header):
    def __init__(self, *, date_keywords=None):
        Header.__init__(self)
        if date_keywords is None:
            date_keywords = ["date", "datetime", "timestamp"]
        self.date_keywords = _validate_optional_str_list(
            self.name, "date_keywords", date_keywords
        )

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.check_date)

    def check_date(self, headers):
        for idx, header in enumerate(headers):
            assert isinstance(header, str)
            if any(keyword in header.lower() for keyword in self.date_keywords):
                self.issues[(idx, header)] = header

        Test.validate(self, "Column may combine YYYY-MM-DD in one column instead of breaking up", "Column does not combine YYYY-MM-DD in one column")


class Header_Mixed_Datatypes(Header):

    def __init__(self):
        Header.__init__(self)


    def validate(self, ws, ws_name, **dependencies):
        self._handle_dependencies(**dependencies, fn=self.check_mixed_datatypes)
        
    def check_mixed_datatypes(self, headers):
        ws = self.ws
        n_rows, n_cols = ws.shape

        # For each column in the worksheet
        for col_idx, col_name in enumerate(ws.columns):

            types_found = dict()

            # Get the column data

            col_data = ws.iloc[:,col_idx]

            # Remove values that are missing to begin with

            col_data = col_data[col_data.notna()]

            # Attempt to convert the column to general numeric

            col_float = pd.to_numeric(col_data, errors='coerce')

            # Compute the number of rows that are possibly numeric

            n_numeric = col_float.notna().sum()

            # If there are any numeric rows

            if n_numeric > 0:

                # Record the number of numeric entries

                types_found["numeric"] = int(n_numeric)


            # Compute number of missing data
            n_missing = col_data.isna().sum()

            # If it's not anything else, it must be text
            n_text = n_rows - n_numeric - n_missing

            # If there's any text
            if n_text > 0:
                types_found["text"] = int(n_text)

                # Loop to the next column
                # Report each column containing multiple types
                # Loop over the columns

            # If there are multiple types
            if len(types_found.keys()) > 1:

                # Add to issues
                self.issues[col_name] = types_found

            Test.validate(self,
                "Table contains columns with mixed data types",
                "Table columns each contains one datatype"
            )
