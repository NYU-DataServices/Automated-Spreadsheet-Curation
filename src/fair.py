# These imports are currently necessary for test discovery -- commenting out the unused ones results in no tests being run
from TestSuite import Test_Suite
from Test import Test
from File import File, File_Delimiter, File_Encoding, File_Name, File_Name_Final, File_Name_Length, File_Name_Special_Characters, File_Name_Whitespace, File_Name_Word_Separation
from Cell import Cell, Cell_Aggregate_Row, Cell_Dates, Cell_Missing_Value_Text, Cell_Newlines_Tabs, Cell_Number_Space, Cell_Question_Mark_Only, Cell_Scientific_Notation, Cell_Special_Characters, Cell_Units, Cell_Untrimmed_White_Space, Cell_White_Space_Only
from Sheet import Sheet_Empty, Sheet_Multi_Table, Sheet_Upper_Left_Corner
from Header import Header, Header_Date, Header_Duplicates, Header_First_Char, Header_ID, Header_Length, Header_Mixed_Datatypes, Header_Space, Header_Special_Characters, Header_Untrimmed_White_Space, Header_Word_Separation


# If run as a script
if __name__ == "__main__":

    # Create a test suite from the demo notebook
    suite = Test_Suite("demo.xlsx")
    
    # Run all the tests and outputs
    suite.run()
    suite.report()
    suite.save(format = "json")
    suite.save(format = "csv")