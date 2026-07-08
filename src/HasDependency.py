from abc import ABC, abstractmethod

# Abstract class for tests that depend on other tests
class Has_Dependency(ABC):

    # The dependencies are provided as arguments 
    # Each dependency is a test class, not an instance
    def __init__(self, *dependencies):
        if hasattr(self, "dependencies"):
            self.dependencies += list(dependencies)
        else:
            self.dependencies = list(dependencies)

    # At the time of validation, instances of the dependencies are passed
    # We check that they have been run. 
    def check_input(self, *inputs):

        # Save the inputs
        self.inputs = inputs

        # Check that all dependencies have been run
        for test in self.inputs:

            # Raise an assertion error if the test has not been run
            # This should only ever happen if there is a bug in the code.
            # Nothing the user does can produce this issue.
            assert test.is_run, f"{test.name} dependency not yet run"

