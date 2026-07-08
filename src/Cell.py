import pandas as pd
import re
from abc import ABC, abstractmethod

from validators import _validate_kwarg_type, _validate_optional_str_list, _validate_regex_kwarg
from Test import Test
from HasDependency import Has_Dependency
from Sheet import Sheet_Empty, Sheet_Upper_Left_Corner, Sheet_Multi_Table


# Abstract class for tests that check each cell in the worksheet
class Cell(Test, Has_Dependency, ABC):

    def __init__(self):
        Test.__init__(self)
        Has_Dependency.__init__(
            self, Sheet_Empty,Sheet_Upper_Left_Corner, Sheet_Multi_Table)

    # Generator over pandas dataframes
    # tuple of the cell coordinates and the cell contents
    # This is used to iterate over the cells in the worksheet
    def pandas_iter(self, df = None):

        # If no dataframe is provided, use the worksheet
        if df is None:
            df = self.effective_ws

        # For each row in the worksheet except the first row (headers)
        for row_idx, row in df.iterrows():

            # For each column
            for col_idx, col_name in enumerate(df.columns):
                cell = df.iloc[row_idx, col_idx]

                # Yield the cell coordinates and the cell contents
                # (row_idx, (col_idx, col_name)), contents)
                yield (row_idx, (col_idx, col_name)), cell

    
    def _handle_dependencies(self, sheet_empty,sheet_upper_left_corner, sheet_multi_table, fn):
        if sheet_empty.empty:
            self.handle_empty()
        elif sheet_multi_table.multi_table:
            self.handle_multi_table()
        else:
            fn(sheet_upper_left_corner.effective_ws)

    # Cell by cell validation.  
    # Assumes that the not_valid method is implemented
    def validate(self, fail_message, pass_message, df = None):

        # If provided, df may be a subset of the whole worksheet
        # If not provided, use the effective worksheet
        if df is None:
            df = self.ws

        
        for cell in self.pandas_iter(df):

            # If the cell is not valid, as given by subclass
            if self.not_valid(cell[1]):

                # Save the cell coordinates and the cell contents
                self.issues[cell[0]] = cell[1]
        

        # Set the status messages
        Test.validate(self, fail_message, pass_message)


    # The not_valid method is an abstract method that must be implemented
    # by each test class that inherits from Cell
    # This method should return True if the cell is not valid, and False if it is valid
    # The validate method will call this method for each cell in the worksheet
    @abstractmethod
    def not_valid(self, cell):
        pass


class Cell_Aggregate_Row(Cell):

    def __init__(self, *, aggregate_words=None):
        Cell.__init__(self)

        if aggregate_words is None:
            aggregate_words = ["total", "sum", "average", "count", "min", "max"]
        self.aggregate_words = _validate_optional_str_list(
            self.name, "aggregate_words", aggregate_words
        )

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_aggregate_row)

    def _check_aggregate_row(self, df):

        words = self.aggregate_words
        if not words:
            regex = None
        else:
            regex = re.compile(
                r"(" + "|".join(re.escape(w) for w in words) + r")",
                re.IGNORECASE,
            )

        # Get the last row
        last_row = df.iloc[-1]

        # List of indices of cells that contain aggregate words
        agg_word_idx = []
        for idx, cell_contents in enumerate(last_row):
            if isinstance(cell_contents, str) and regex is not None:
                if regex.search(cell_contents):
                    agg_word_idx.append(idx)

        is_aggregate_row = False
        for idx in agg_word_idx:
            if idx + 1 < len(last_row) and isinstance(
                last_row.iloc[idx + 1], (int, float)
            ):
                is_aggregate_row = True
                break

        if is_aggregate_row:
            row_idx = df.index[-1]
            for idx in agg_word_idx:
                col_idx = idx
                col = df.columns[col_idx]
                self.issues[row_idx, (col_idx, col)] = (
                    last_row.iloc[idx],
                    last_row.iloc[idx + 1],
                )

        Test.validate(self, "Last row contains aggregate words", "Last row does not contain aggregate words")

    # Required by Cell to make this class not abstract
    def not_valid(self, cell):
        pass
        
# Look for special characters in the cells
class Cell_Special_Characters(Cell):

    def __init__(self, *,
                 default_pattern=r"[!@#$%^&*()+=\[\]{};:'\"|\\,<>\?/]",
                 url_pattern=r"^https?://",
                 free_text_pattern=r"[!@#$%&*(){}\[\]|<>/]",
                 url_columns=None,
                 free_text_columns=None,
                 skip_columns=None):
        Cell.__init__(self)
        
        self.default_pattern = _validate_regex_kwarg(
            self.name, "default_pattern", default_pattern
        )
        self.url_pattern = _validate_regex_kwarg(self.name, "url_pattern", url_pattern)
        self.free_text_pattern = _validate_regex_kwarg(
            self.name, "free_text_pattern", free_text_pattern
        )
        self.url_columns = _validate_optional_str_list(
            self.name, "url_columns", url_columns
        )
        self.free_text_columns = _validate_optional_str_list(
            self.name, "free_text_columns", free_text_columns
        )
        self.skip_columns = _validate_optional_str_list(
            self.name, "skip_columns", skip_columns
        )

    def validate(self, ws, ws_name, **dependencies):
        self.ws_name = ws_name
        self._handle_dependencies(**dependencies, fn=self._check_special_characters)

    def _check_special_characters(self, df):
        # Check the url columns
        if len(self.url_columns) > 0:
            try:
                url_df = df[self.url_columns]
            except KeyError:
                raise KeyError(f"Column(s) {self.url_columns} not found in worksheet {self.ws_name}")
            self.bad_chars_regex = self.url_pattern
            Cell.validate(self, "Invalid URL cells found", "Valid URL cells found", url_df)
        
        # Check the free text columns
        if len(self.free_text_columns) > 0:
            free_text_df = df[self.free_text_columns]
            self.bad_chars_regex = self.free_text_pattern
            Cell.validate(self, "Invalid free text cells found", "Valid free text cells found", free_text_df)

        # Check the rest of the cells
        default_df = df.drop(
            columns=self.url_columns + self.free_text_columns + self.skip_columns,
            errors="ignore",
        )
        self.bad_chars_regex = self.default_pattern
        Cell.validate(self, "General special characters found", "No general special characters found", default_df)


    def not_valid(self, cell):
        """Return True if the cell is not valid (has disallowed special chars). Uses coord for free_text_columns."""
        if not isinstance(cell, str):
            return False

        bad_chars = re.findall(self.bad_chars_regex, cell)
        return len(bad_chars) > 0


# Search for leading or trailing white space
class Cell_Untrimmed_White_Space(Cell):
    def __init__(self):
        Cell.__init__(self)
        
    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_untrimmed_white_space)

    def _check_untrimmed_white_space(self, df):
        # Use the default validate method for Cell
        Cell.validate(self,
            "Leading or trailing white space found",
            "No leading or trailing white space found",
            df)
    
    # Required by Cell
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # This regex matches any white space at the beginning or end of the string
        # Bad_space is a list of all the leading or trailing white space found, but not if the cell is exactly a single space
        if cell == " ":
            bad_space = []
        else:
            bad_space = re.findall(r'^\s|\s$', cell)

        # If there is no leading or trailing white space, return False
        if len(bad_space) == 0:
            return False
        else:
            # The cell had leading or trailing white space
            return True

class Cell_Newlines_Tabs(Cell):
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_newlines_tabs)

    def _check_newlines_tabs(self, df):
        # Use the default validate method for Cell
        Cell.validate(self,
            "Newlines, tabs, or vertical tabs found",
            "No newlines, tabs, or vertical tabs found",
            df)
        
    # Required by Cell
    def not_valid(self, cell):

        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # This regex matches newlines, tabs, and vertical tabs anywhere
        # bad_space is a list of all the matches
        bad_space = re.findall(r'[\t\n\v]', cell)

        # If there are no newlines... etc
        if len(bad_space)==0:
            return False
        else:
            # The cell had newlines
            return True



        
    # Required by Cell
    def not_valid(self, cell):

        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # This regex matches single and double quotes around comma or a tab
        # bad_space is a list of all the matches
        delimiters_in_cells = re.findall(r'[\'\"][,\t][\'\"]', cell)

        # If there are no newlines... etc
        if len(delimiters_in_cells)==0:
            return False
        else:
            # The cell had newlines
            return True

class Cell_Missing_Value_Text(Cell):
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_missing_value_text)

    def _check_missing_value_text(self, df):
        # Use the default validate method for Cell
        Cell.validate(self,
            "Text denoting missing values found",
            "No text denoting missing values found",
            df)
        
    # Required by Cell
    def not_valid(self, cell):

        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # This regex matches newlines, tabs, and vertical tabs anywhere
        # bad is a list of all the matches
        bad = re.findall(r'^(?:(no data)|(nd)|(missing)|(missing data)|(na)|(null)|(\-)|(\.)|(\s+)|(_+))$', cell, flags = re.IGNORECASE)

        # If there are matches
        if len(bad)==0:
            return False
        else:
            # The cell had missing data text
            return True

# Search for cells containing only question marks
class Cell_Question_Mark_Only(Cell):
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_question_mark_only)

    def _check_question_mark_only(self, df):
        Cell.validate(self, "Cells with just a question mark found", "No question mark cells found", df)
    
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # If the cell is exactly a question mark.
        return cell == "?"
            
class Cell_White_Space_Only(Cell):
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_white_space_only)

    def _check_white_space_only(self, df):
        Cell.validate(self, "Cells with white space only found", "No cells with white space only found", df)
    
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        bad_space = re.findall(r'^\s+$', cell)
        if len(bad_space) == 0:
            return False
        else:
            return True

class Cell_Number_Space(Cell):
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_number_space)

    def _check_number_space(self, df):
        Cell.validate(self, "Cells with only spaces and numbers found", "No cells with only spaces and numbers found", df)
    
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # Matches cells with at least one number and at least one spacer
        # but no other character type
        bad_match = re.findall(r'^(?=.*\d)(?=.*\s)[\d\s]+$', cell)
        if len(bad_match) == 0:
            return False
        else:
            return True



class Cell_Dates(Cell):
    def __init__(self, *,
        date_columns=None,
        auto_detect_columns=False,
        format_code="%Y/%m/%d",
        date_column_threshold=0.8):

        Cell.__init__(self)

        
        if date_columns is None:
            self.date_columns = None
        elif isinstance(date_columns, dict):
            for sheet_name, columns in date_columns.items():
                _validate_optional_str_list(self.name, "date_columns", columns)
                self.date_columns[sheet_name] = columns
        else:
            raise ValueError(
                f"{self.name}: `date_columns` must be a dictionary with sheet names as keys and lists of column names as values."
            )
        
        _validate_kwarg_type(self.name, "auto_detect_columns", auto_detect_columns, bool)

        if auto_detect_columns and date_columns is not None:
            raise ValueError(
                f"{self.name}: `auto_detect_columns` and `date_columns` cannot be used together."
            )
        else:    
            self.auto_detect_columns = auto_detect_columns


        _validate_kwarg_type(self.name, "format_code", format_code, str)
        self.format_code = format_code
        _validate_kwarg_type(self.name, "date_column_threshold", date_column_threshold, (int, float))
        if date_column_threshold < 0 or date_column_threshold > 1:
            raise ValueError(
                f"{self.name}: `date_column_threshold` must be between 0 and 1."
            )
        self.threshold = date_column_threshold
        
        
    def validate(self, _, sheet_name, **dependencies):
        dc = self.date_columns
        if dc is None or sheet_name in dc or "*" in dc:
            self._handle_dependencies(**dependencies, fn=self._check_dates)



    def _check_dates(self, df):
        
        if self.auto_detect_columns:
            remaining_df = df.drop(self.date_columns)

            # Coerce all cells to datetimes, 'coerce' will set invalid dates to na
            # 'mixed' will try to parse the dates in any format
            # Note this is usually overly ambitious
            parsed_dates = remaining_df.apply(
                pd.to_datetime, errors="coerce", format="mixed"
            )

            # Check the ratio of valid dates to total dates
            # This will be a series with the column names as the index
            # and the ratio of valid dates as the values
            ratio_dates = parsed_dates.apply(lambda s: s.notna().mean())
            # Get only with more than the threshold of valid dates
            date_cols = ratio_dates[ratio_dates > self.threshold].index
            # Add the new columns to the date dataframe
            date_df = pd.concat([date_df, remaining_df[date_cols]])
        elif self.date_columns is not None:
            date_df = df[self.date_columns]
        else:
            date_df = df

        # Validate the date dataframe
        Cell.validate(
            self,
            "Cells with non-ISO dates found",
            "Either no dates or all dates are ISO",
            date_df,
        )


    def not_valid(self, cell):
        if not isinstance(cell, str):
            # This test does not apply
            return False

        # Check if the dates are in the required format
        try:
            # Attempt to parse the date
            cell_date = dt.strptime(cell, self.format_code)
            # If the parsing is successful, the date is valid
            return False
        except ValueError as e:
            # If the parsing is not successful, the date is invalid
            return True


class Cell_Scientific_Notation(Cell):
    # This test fails for "small" exponents like 1e-3
    # Because pandas reads these as floats automatically
    def __init__(self):
        Cell.__init__(self)

    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_scientific_notation)

    def _check_scientific_notation(self, df):
        Cell.validate(self, "Cells with scientific notation found", "No cells with scientific notation found", df)
    
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        
        # This regex matches any number in scientific notation
        sci_notation = re.fullmatch(r'^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+$', cell.strip())

        # If the cell is not in scientific notation, return False
        if sci_notation == None:
            return False
        else:
            # The cell is in scientific notation
            return True




_DEFAULT_UNIT_ABBREVS = [
    "nm", "µm", "um", "mm", "cm", "m", "km",
    "in", "ft", "yd", "mi",
    "gal", "L", "mL",
    "g", "kg", "lb", "oz", "mg", "µg", "ug", "ng", "pg",
    "µmol", "umol", "mmol", "mol",
    "s", "sec", "min", "hr", "h", "d", "day", "week", "w", "y", "year", "mo",
]


class Cell_Units(Cell):
    def __init__(self, *, unit_abbreviations=None):
        Cell.__init__(self)
        if unit_abbreviations is None:
            unit_abbreviations = _DEFAULT_UNIT_ABBREVS
        self.unit_abbreviations = _validate_optional_str_list(
            self.name, "unit_abbreviations", unit_abbreviations
        )
        self.units_regex = r'^[+-]?[\d\.]+(' + '|'.join(re.escape(u) for u in self.unit_abbreviations) + r')$'


    def validate(self, *ignore, **dependencies):
        self._handle_dependencies(**dependencies, fn=self._check_units)

    def _check_units(self, df):
        # Check that the grid edges test has been run
        Cell.validate(self, "Cells with units found", "No cells with units found", df)
    
    def not_valid(self, cell):
        
        # Check if the cell is a string
        if not isinstance(cell, str):
            # This test does not apply
            return False
        

        matches = re.fullmatch(self.units_regex, cell.strip())

        # If the cell has no units, return False
        if matches == None:
            return False
        else:
            # The cell has units
            return True


