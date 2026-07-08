from abc import ABC, abstractmethod

# Abstract class for the structure of a test
class Test(ABC):


    def __init__(self):
        # Get the base class name (deepest/first concrete class in MRO)
        base_cls = type(self)
        # Save the base class name as the test name
        self.name = base_cls.__name__.lower()

        # Whether the test has been run
        self.is_run = False

        # True if the test passed, False if it failed
        self.status = None


        # The issues found during the test
        # This is a dict of cell coordinates and their associated issues
        self.issues = dict()

        # The message to display with the test results
        # This is a string that describes the outcome of the test in plain english
        self.message = "Not yet run"


    # The validate method is the main method that runs the test
    # Every Test class must implement this method
    # Most tests will use the status code given below at the end
    @abstractmethod
    def validate(self, fail_message, pass_message):

        # The test has been run
        self.is_run = True

        # If there were any issues
        if len(self.issues) > 0:

            # The test failed
            self.status = False

            # Save the fail message
            self.message = fail_message 
        else:

            # The test passed
            self.status = True

            # Save the pass message
            self.message = pass_message       


    def handle_empty(self):
        Test.validate(
            self,
            None,
            "Cannot assess test if sheet is empty.  Pass by default")

    def handle_multi_table(self):
        Test.validate(
            self,
            None,
            "Cannot assess test if multiple tables are present.  Pass by default")

