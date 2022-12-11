import pandas as pd
from matching_tools import get_fuzzy_matches, fuzzy_pairwise_compare

# Where to save the matched output
output_filename = 'eng-matching-output.csv'

# Where to download the input file we'll be populating with matches
url_input_to_be_matched = 'https://drive.google.com/open?id=1o3SWFV1oJ4Z3hr6nFPAQPO8y8wWtlfgL'

# Path to Ohio voterfile (please run the get_ohio_voterfile.py script first to get this file)
path_to_voterfile = 'ohio_voterfile.csv'

# Minimum acceptable weighted match score (ranges from 0-1)
min_weighted_similarity = 0.70

# Where to find the voterid column in the voterfile
voterid_col = 'SOS_VOTERID'

# Configure the fuzzy matching process.
# 'primary_match_columns' will be used to narrow the universe of potential matches 
# between the two input lists. It is a tuple representing (input_column, voterfile_column, weight).
# The 'weight' field specifies how important the the two columns are for the overall match.
# 'secondary_match_columns is a list of similar tuples for refining the potential 
# matches using other columns.
fuzzy_match_configuration = {
  'primary_match_columns': ('name', 'FULL_NAME', 1.0),
  'secondary_match_columns': [
    ('address', 'RESIDENTIAL_ADDRESS1', 0.5),
    ('address', 'MAILING_ADDRESS1', 0.5),
    ('city', 'RESIDENTIAL_CITY', 0.25),
    ('city', 'MAILING_CITY', 0.25),
  ]
}

# exact_match_configuration is a list of tuples representing (input_column, voterfile_column, weight)
# In addition to the fuzzy matching, we will do exact matching on these columns.
exact_match_configuration = [
  ('birth_year', 'BIRTH_YEAR', 0.5),
  ('state', 'RESIDENTIAL_STATE', 0.25),
  ('state', 'MAILING_STATE', 0.25),
  ('zip', 'RESIDENTIAL_ZIP', 0.25),
  ('zip', 'MAILING_ZIP', 0.25)
]

def get_input_to_be_matched(url):
  # Modify the input URL to ask Drive for the actual file.
  # Note: we're replacing the word 'open' with 'uc', but matching
  # on a leading '/' and a trailing '?' to be extra-safe about
  # which part of the URL gets replaced.
  url = url.replace(
    '/open?',
    '/uc?'
  )

  return pd.read_csv(
    url,
    dtype={
      'birth_year': str,
      'zip': str
    }
  )

def perform_match(
  df_to_populate,
  df_potential_matches,
  fuzzy_match_configuration,
  exact_match_configuration
):

  # Grab some data from the configurations set at the top of the script
  fuzzy_primary_config = fuzzy_match_configuration['primary_match_columns']
  fuzzy_secondary_config = fuzzy_match_configuration['secondary_match_columns']

  # Perform the initial fuzzy match, passing in all the input/source data, info on
  # which columns to use, and info on which extra columns to retain in the output
  df_matches = get_fuzzy_matches(
    df_to_populate, 
    df_potential_matches, 
    fuzzy_primary_config[0], 
    fuzzy_primary_config[1],
    to_populate_appends=df_input.columns, 
    potential_matches_appends=[
      voterid_col,
      fuzzy_primary_config[1],
      *[ config[1] for config in fuzzy_secondary_config ],
      *[ config[1] for config in exact_match_configuration ]
    ]
  )

  # Run a bunch of fuzzy pairwise comparisons between secondary matching columns
  for config in fuzzy_secondary_config:
    df_matches = fuzzy_pairwise_compare(
      df_matches,
      config[0],
      config[1]
    )

  # Run some exact (though case-insensitive) matches on additional columns
  for config in exact_match_configuration:
    # Track missing values (we'll re-insert them later)
    missing_mask = (
      df_matches[config[0]].isna() |
      df_matches[config[1]].isna()
    )

    # Construct the column name where we'll store the exact match result
    # we're working on in this iteration of the for loop
    col_name = f'exact [{config[0]} vs {config[1]}]'

    # Do the exact match/comparison on the columns
    df_matches[col_name] = (
      df_matches[config[0]].str.upper() == df_matches[config[1]].str.upper()
    )

    # Re-insert missing values
    df_matches.loc[missing_mask,col_name] = pd.NA

  # For exact matches, convert the booleans to 1 or 0
  df_matches.replace(
    {
      True: 1.0,
      False: 0.0
    },
    inplace=True
  )
  
  return df_matches

def process_matches(df_matches):
  # Pull some info out of the configurations set at the top of the script
  fuzzy_config = [ 
    fuzzy_match_configuration['primary_match_columns'], 
    *fuzzy_match_configuration['secondary_match_columns']
  ]

  # Create a new column that will store a weighted average of all the various
  # comparisons between columns; set it to 0 to start.
  weighted_col = 'weighted similarity'
  df_matches[weighted_col] = 0.

  # Create a new column to store the maximum possible weight across all columns--
  # this will be used to compute the weighted average at the end.
  max_weight_col = 'max possible weight'
  df_matches[max_weight_col] = 0.

  # Loop over the configured fuzzy match columns - we're working on a weighted average here
  for config in fuzzy_config:
    # Construct the name for the similarity column we're working on
    current_col = f'similarity [{config[0]} vs {config[1]}]'

    # Get the weight from the configuration, weight the similarity score (inserting zeros if null)
    df_matches[weighted_col] += (
      config[2] * df_matches[current_col]
    ).fillna(0.)

    # Also track the maximum possible weight, based on the config. This will either be zero
    # (if the record is null), or the configured weight.
    df_matches[max_weight_col] += (
      config[2] * df_matches[current_col].notna()
    )

  # Repeat the same steps for the exact match columns
  for config in exact_match_configuration:
    current_col = f'exact [{config[0]} vs {config[1]}]'

    df_matches[weighted_col] += (
      config[2] * 
      df_matches[current_col]
    ).fillna(0.)

    df_matches[max_weight_col] += (
      config[2] * df_matches[current_col].notna()
    )

  # Normalize the weighted sum into a weighted average
  df_matches[weighted_col] /= df_matches[max_weight_col]

  # Sort by row (asc), weighted_avg (desc) - this will help us take only
  # the best match for each original row (next step)
  df_matches.sort_values(
    by=['row', weighted_col],
    ascending=[True, False],
    inplace=True
  )

  # Drop all but the first (best) match for each row
  df_matches.drop_duplicates(
    subset='row',
    keep='first',
    inplace=True
  )

  # Blank out any voterid match where the weighted average similarity is too low
  poor_match_mask = ( df_matches[weighted_col] < min_weighted_similarity )
  df_matches.loc[poor_match_mask,voterid_col] = pd.NA

  keep_cols = [
    'row',
    'name',
    'birth_year',
    'address',
    'city',
    'state',
    'zip',
    voterid_col
  ]

  # Pare down on columns and rename the voterid field
  df_matches = df_matches[keep_cols]
  df_matches.rename(
    columns={ 'SOS_VOTERID': 'matched_voterid' },
    inplace=True
  )

  return df_matches

if __name__ == '__main__':
  # Load the input csv that we'll populate with voterids
  df_input = get_input_to_be_matched(url_input_to_be_matched)
  
  # Load the voterfile (please run the get_ohio_voterfile.py script first)
  df_voterfile = pd.read_csv(
    path_to_voterfile,
    dtype={
      'RESIDENTIAL_ZIP': str,
      'MAILING_ZIP': str,
      'BIRTH_YEAR': str
    },
    encoding='latin1'
  )

  # Run the match
  df_matches = perform_match(
    df_input,
    df_voterfile,
    fuzzy_match_configuration,
    exact_match_configuration
  )

  # Process the match results
  df_matches = process_matches(df_matches)

  # Save the matches to a file
  df_matches.to_csv(
    output_filename,
    index=False  
  )
