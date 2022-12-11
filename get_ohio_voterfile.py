import pandas as pd
from matching_tools import merge_columns

# Where to get the source files for matching
url_template_voterfile = 'https://www6.ohiosos.gov/ords/f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:{county_num}'

# Where to save the voterfile output
output_filepath = 'ohio_voterfile.csv'

# Highest county number available in OH
max_county = 88

def get_voterfile(
  url_template,
  start_county=1,
  end_county=4
):
  # Make sure we only try to grab real counties
  if end_county > max_county:
    raise Exception(f'ERROR: end_county must not exceed {max_county}.')

  if start_county < 1:
    raise Exception('ERROR: start_county must be greater than 1.')

  # Make sure start_county is smaller than end_county
  if start_county > end_county:
    raise Exception('ERROR: start_county must be smaller than end_county.')

  # Loop over county numbers, saving data in a list of pandas DataFrames as we go.
  dfs = []
  for county in range(start_county, end_county+1):
    print(f'loading data for county number {county}...')

    # Construct the URL from the template and county number
    url = url_template.format(county_num=county)

    # Load the current county's data and append it to the list of DataFrames
    dfs.append(
      pd.read_csv(
        url,
        storage_options={'User-Agent': 'Mozilla/5.0'}, # Pretend we're a browser, otherwise we get a 403 error.
        dtype={
          'RESIDENTIAL_ZIP': str,
          'MAILING_ZIP': str
        },
        encoding='latin1'
      )
    )

  # Merge all the DataFrames
  dfs = pd.concat(
    dfs, 
    axis=0
  ).reset_index()

  # Add a convenience column that stores middle initial
  dfs['MIDDLE_INITIAL'] = dfs['MIDDLE_NAME'].apply(
    lambda record: record[0] if isinstance(record, str) else ''
  )

  # Add a convenience column that concatenates first, middle initial, and last nameparts
  dfs['FULL_NAME'] = merge_columns(
    dfs,
    [
      'FIRST_NAME',
      'MIDDLE_INITIAL',
      'LAST_NAME'
    ]
  )

  # Extract birth year
  dfs['BIRTH_YEAR'] = dfs['DATE_OF_BIRTH'].apply(
    lambda record: record[:4]
  )

  return dfs

if __name__ == '__main__':
  df_voterfile = get_voterfile(url_template_voterfile)
  df_voterfile.to_csv(output_filepath)
