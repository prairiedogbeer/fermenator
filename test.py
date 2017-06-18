import logging
from fermenator.datasource.gsheet import GoogleSheet

logging.basicConfig()
logging.getLogger('fermenator').setLevel(logging.DEBUG)

gs = GoogleSheet(config={'client_secret': '/Users/gerad/Dropbox/Brewery/beermon-creds.json'})
gs.get_sheet_range('1HynSfoe9BrXnmRMDMaNftCuXXXi3qyjIi-pxd2hq3EM', 'Sheet1!A1:A10')
