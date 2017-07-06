import datetime

def temp_f_to_c(temp_f):
    "Convert a Fahrenheit temperature to celcius, floating point"
    return (temp_f - 32) * 5.0 / 9.0

def temp_c_to_f(temp_c):
    "Convert a Celcius temperature to Fahrenheit, floating point"
    return temp_c * 9.0 / 5.0 + 32

def sg_to_plato(sg):
    "Convert a standard gravity reading to plato (floating point)"
    return 135.997 * sg**3 - 630.272 * sg**2 + 1111.14 * sg - 616.868

def rfc3339_timestamp_to_datetime(ts_string):
    return datetime.datetime.strptime(
        ts_string,
        '%Y-%m-%dT%H:%M:%S.%f'
    )

SPREADSHEET_DATETIME_BASE = datetime.datetime(1899, 12, 30)

def convert_spreadsheet_date(sheetdate):
    """
    Google Sheets uses a format of float number where the whole part
    represents days since December 30, 1899, and the decimal part represents
    partial days. This function converts a google sheet date to a Python
    datetime.
    """
    try:
        sheetdate = float(sheetdate)
        return SPREADSHEET_DATETIME_BASE + datetime.timedelta(
            days=int('{:.0f}'.format(sheetdate)),
            seconds=int((sheetdate % 1.0) * 86400)
        )
    except ValueError:
        # new date format: M/D/Y HH:MM:SS
        return datetime.datetime.strptime(
            sheetdate,
            '%m/%d/%Y %H:%M:%S'
        )
