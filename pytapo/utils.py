from pytapo.const import ERROR_CODES


@staticmethod
def getErrorMessage(errorCode):
    if str(errorCode) in ERROR_CODES:
        return str(ERROR_CODES[str(errorCode)])
    else:
        return str(errorCode)
