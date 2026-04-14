class Logger:
    def __init__(self, printDebugInformation=False, printWarnInformation=True):
        self.printDebugInformation = printDebugInformation
        self.printWarnInformation = printWarnInformation

    def debugLog(self, msg):
        if self.printDebugInformation is True:
            print(msg)
        elif callable(self.printDebugInformation):
            self.printDebugInformation(msg)

    def warnLog(self, msg):
        if self.printWarnInformation is True:
            print(f"WARNING: {msg}")
        elif callable(self.printWarnInformation):
            self.printWarnInformation(msg)
