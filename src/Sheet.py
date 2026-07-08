import numpy as np
import pandas as pd
import re
from abc import ABC, abstractmethod

from Test import Test
from HasDependency import Has_Dependency
from validators import _validate_regex_kwarg


class Sheet(Test, Has_Dependency, ABC):
    def __init__(self,):
        Test.__init__(self)
        if not isinstance(self, Sheet_Empty):
            Has_Dependency.__init__(self, Sheet_Empty)
        else:
            self.dependencies = []


    def set_positional(self, ws, ws_name):
        if not isinstance(ws, pd.DataFrame):
            raise ValueError("ws must be a pandas DataFrame")
        if not isinstance(ws_name, str):
            raise ValueError("ws_name must be a string")
        self.ws = ws
        self.ws_name = ws_name

class Sheet_Empty(Sheet):
    def __init__(self,):
        
        Sheet.__init__(self,)
        self.empty = None


    def validate(self, ws, ws_name):
        self.set_positional(ws, ws_name)

        # Check if the worksheet is empty
        if self.ws.empty:
            # The test failed
            self.status = False

            # Set empty status
            self.empty = True

            # Set the message
            self.message = "Worksheet is empty"

            self.issues = {"sheet": self.ws_name}

        else:
            # The test passed
            self.status = True

            # Set empty status
            self.empty = False

            # Set the message
            self.message = "Worksheet is not empty"

class Sheet_Name(Sheet):
    def __init__(self, *,
                 special_char_pattern=r"[!@#$%^&*()+=\[\]{};:'\"|\\,<>\?/]"):
        
        Sheet.__init__(self,)
        self.special_char_pattern = _validate_regex_kwarg(
            self.name, "special_char_pattern", special_char_pattern
        )

    def validate(self, ws, ws_name, sheet_empty):
        self.set_positional(ws, ws_name)



        # detect special characters in filename
        spec_char = re.search(self.special_char_pattern, self.ws_name)
        message = "Worksheet name: "
        if spec_char:
            self.status = False

            self.issues["sheet"] = spec_char.group(0)
            message += f"contains special characters ({spec_char.group(0)}) "
        
        # detect whitespace in sheet name
        if re.search(r"\s", self.ws_name):
            self.status = False

            self.issues["sheet"] = self.ws_name
            message += "contains whitespace "

        
        if  self.status is None:
            # The test passed
            self.status = True

            # Set the message
            self.message = "Worksheet name does not contain special characters or whitespace"
        else:
            self.message = message

# Check that the table is in the upper left corner
# The first_row is not working.
class Sheet_Upper_Left_Corner(Sheet):

    def __init__(self,):
        Sheet.__init__(self,)

        # Share that col_start and row_start are 0, default     
        self.first_row_idx = 0
        self.first_col_idx = 0

    def validate(self, ws, ws_name, sheet_empty):
        self.set_positional(ws, ws_name)

        
        mask = self.ws.notna().to_numpy()

        if sheet_empty.empty:
            self.handle_empty()
            return



        # Detect whether the headers were defined
        no_headers = self.ws.columns == "Unnamed"

        # If none of the headers are defined, search in the table for them
        if no_headers.all():
            # Check each col for NA values, extract idx of first non-NA in each
            col_starts = np.argmax(mask, axis = 0)
            col_starts = np.where(
                np.sum(mask, axis = 0) == 0,
                len(col_starts),
                col_starts)

        # Else one or more of the headers were defined
        else:
            # So the first col is the top row of the table
            col_starts = np.array([-1])


        # Check each row for NA values, extract column name of first non-NA
        row_starts = np.argmax(mask, axis = 1)
        row_starts = np.where(
            np.sum(mask, axis = 1) == 0,
            len(row_starts),
            row_starts)

        # Set the start of the grid
        # The first nonempty row is where first column starts
        first_row = int(col_starts.min())
        first_row = first_row + 1

        first_col = int(row_starts.min())

        
        # Check for blank space before the first column or row
        if first_col > 0 or first_row > 0:
            
            # Where exactly it failed
            self.issues["first_col_idx"] = first_col
            self.issues["first_row_idx"] = first_row

            # Save results to share with other tests
            self.first_col_idx = first_col
            self.first_row_idx = first_row
            # Mark that there is a displaced table
            self.displaced = True
            # Save an effective table
            self.effective_ws = self.ws.iloc[first_row:, first_col:]
            if first_row > 0:
                # First row is the column names
                cols = self.effective_ws.iloc[0]
                self.effective_ws.columns = cols
                self.effective_ws = self.effective_ws[1:].reset_index(drop=True)
            # Else the columns are already assigned correctly

        else:
            self.displaced = False
            self.effective_ws = self.ws


        Test.validate(self,
            "Table is not in the upper left corner",
            "Table is in the upper left corner"
        )

# Detect if there are multiple tables
class Sheet_Multi_Table(Sheet, Has_Dependency):

    def __init__(self,):
        Sheet.__init__(self,)
        Has_Dependency.__init__(self, Sheet_Upper_Left_Corner)
        self.multi_table = None
        self.effective_ws = None

    def validate(self, ws, ws_name, sheet_empty, sheet_upper_left_corner):
        self.set_positional(ws, ws_name)

        if sheet_empty.empty:
            self.handle_empty()
            return

        # Get shifted worksheet if relevant
        ws = sheet_upper_left_corner.effective_ws

        # Dimensions
        n_row, n_col = ws.shape

        # Array = 0 where value exists, else 1
        mask = ws.isna().to_numpy()
        # Obtain offset in case table not in upper left corner
        col_offset = sheet_upper_left_corner.first_col_idx
        row_offset = sheet_upper_left_corner.first_row_idx
        


        # First value in each row
        left_edge = np.argmin(mask, axis = 1)
        # left_edge = 0 if either all True or all False
        # test if all empty (True)
        empty_rows = np.all(mask, axis = 1)
        # Set left_edge to n_col if empty_row
        left_edge = np.where(empty_rows == 1, n_col, left_edge)
        # First value in each col
        top_edge = np.argmin(mask, axis = 0)
        # top_edge = 0 if either all True or all False
        # test if all empty (True)
        empty_cols = np.all(mask, axis = 0)
        
        # If there were any
        if np.any(empty_cols):
            # Could be multiple tables

            # Get locations of empty columns
            empty_cols_idx = np.argwhere(empty_cols)
            # Add an issue
            self.issues["empty columns"] = (empty_cols_idx + col_offset).ravel().tolist()
        
        # Set top_edge to n_row if empty_col
        top_edge = np.where(empty_cols == 1, n_row, top_edge)
        
        # Look for lower right corner
        # For candidate corner (i,j) in grid
        # If left_edge > j and also top_edge > i
        # We have a bounding box with
        # Upper right (0,0) and lower right (i,j)

        # Compute mesh grid of coordinates
        ii, jj = np.mgrid[0:n_row, 0:n_col]

        # Create zeros grid where empty cells left of left_edge filled with ones
        left_grid = np.where(left_edge[:,np.newaxis] > jj, 1, 0 )

        # Create zeros grid where empty cells above top_edge filled with ones
        top_grid = np.where(top_edge[np.newaxis,:] > ii, 1, 0)

        # If left padded grid intersects top padded grid
        # Then there exists a bounding box around subset of data
        box = np.logical_and(left_grid, top_grid)

        # If there is a bounding box smaller than the whole table
        if np.any(box):
            # Get location of lower right corner candidates
            lower_right_corners = np.argwhere(box)

            # Get location of corner closest to 0,0
            best_corner = lower_right_corners[0,:]

            # Add offset back in
            best_corner[0] = best_corner[0] + row_offset
            best_corner[1] = best_corner[1] + col_offset

            # Save the result as an issue
            self.issues["multi_table_corner"] = best_corner.tolist()

            # Feed forward property, prevents tests that would fail under multitable from running
            self.multi_table = True
        else:
            self.multi_table = False

        Test.validate(self,
            "Found bounding box around table smaller than full dimensions.  Sheet may have multiple tables.",
            "Sheet does not have multiple tables")

