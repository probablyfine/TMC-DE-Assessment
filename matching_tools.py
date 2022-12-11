from string_grouper import StringGrouper, StringGrouperConfig, compute_pairwise_similarities
import re
import pandas as pd

excl_chars = [',','-','.','/','\\','*','(',')','_','@','!','#','$','"',"'"]

def get_fuzzy_matches(
  df_to_populate,               # DataFrame that will have matches populated into it.
  df_potential_matches,         # DataFrame that contains potential matches.
  to_populate_match_col,        # Column in the "to_populate" DataFrame that we should match on.
  potential_matches_match_col,  # Column in the "potential_matches" DataFrame that we should match on.
  to_populate_label=None,       # User-friendly label for the "to_populate" DataFrame.
  potential_matches_label=None, # User-friendly label for the "potential_matches" DataFrame.
  to_populate_appends=[],       # Columns in the "to_populate" DataFrame that we should include in the output.
  potential_matches_appends=[], # Columns in the "potential_matches" DataFrame that we should include in the output.
  ignore_case=True,             # Should the match ignore character case?
  min_similarity=0.45,          # Number between 0-1 specifying the worst score of an acceptable match.
  max_n_matches=30,             # Number of potential matches to retain.
  pad_short_strings=True        # Should we add "padding" characters where needed? If set to False, the matching
                                # process will discard very short strings that can't be broken into "ngrams".
):
  # Grab the column in the "to_populate" DataFrame that we should match on,
  # and run it through a custom function that cleans/sanitizes its contents
  to_populate_cleaned = clean_column(
    df_to_populate[to_populate_match_col],
    pad_short_strings=pad_short_strings
  )
  
  # Do the same for the "potential_matches" DataFrame
  potential_matches_cleaned = clean_column(
    df_potential_matches[potential_matches_match_col],
    pad_short_strings=pad_short_strings
  )

  # Instantiate a matcher object from the string_grouper package, pass it
  # our cleaned inputs, and run the initial match.
  grouper = StringGrouper(
    potential_matches_cleaned,
    to_populate_cleaned, 
    ignore_case=ignore_case,
    ignore_index=False,
    min_similarity=min_similarity,
    max_n_matches=max_n_matches
  ).fit()
  
  # Pull the list of potential matches out of the string_grouper object
  df_matches = grouper.get_matches()
  
  # Loop over the columns in the "potential_matches" DataFrame that we want to keep
  # in the output, and append them to the matches list
  for col in potential_matches_appends:
    df_matches = append_column(
      df_matches,
      df_potential_matches,
      col,
      'left',
      potential_matches_label
    )

  # Find the rows in the "to_populate" DataFrame that were dropped due to poor match quality
  missing_idx = (
    df_to_populate
    .index
    .difference(
      pd.Index(df_matches['right_index'].unique())
    )
  )

  # Pull out those missing records as a new DataFrame
  df_missing = df_to_populate.loc[missing_idx,to_populate_match_col]
  df_missing = df_missing.reset_index(drop=False)

  # Re-work the "missing records" DataFrame to fit into the matches DataFrame
  df_missing.rename(
    columns={
      to_populate_match_col: 'right_' + to_populate_match_col,
      'index': 'right_index'
    },
    inplace=True
  )
  
  # Append the missing records (without any corresponding matches) into the matches DataFrame
  df_matches = pd.concat(
    (df_matches, df_missing),
    axis=0,
    ignore_index=True
  )

  # Loop over the columns in the "to_populate" DataFrame that we want to keep
  # in the output, and append them to the matches list
  for col in to_populate_appends:
    df_matches = append_column(
      df_matches,
      df_to_populate,
      col,
      'right',
      to_populate_label
    )

  # Rename the similarity score column for extra clarity
  df_matches.rename(
    columns={ 'similarity': f'similarity [{to_populate_match_col} vs {potential_matches_match_col}]'},
    inplace=True
  )

  # Return the match results (and the extra columns we appended), dropping
  # some convenience columns we'll no longer need.
  return df_matches.drop(
    columns=[
      f'left_{potential_matches_match_col}',
      f'right_{to_populate_match_col}',
      'left_index',
      'right_index'
    ]
  )

def clean_column(
  series,                                      # Column to clean, as a pandas Series
  excl_chars=excl_chars,                       # List of characters to strip out/ignore
  pad_short_strings=True,                      # Should we pad out very short strings?
  missing_values='drop',                       # How to handle missing values. 'drop' means discard, 'fill' means substitute empty string
  ngram_size=StringGrouperConfig().ngram_size, # ngram_size pulled from string_grouper
  regex=StringGrouperConfig().regex            # The regex that string_grouper uses internally for cleaning
):

  if missing_values == 'drop':
    # Toss out missing values (nothing to match on) and convert to string dtype
    series = (
      series
      .dropna()
      .astype(str)
    )
  elif missing_values == 'fill':
    # Replace missing values with empty strings
    series = (
      series
      .fillna('')
      .astype(str)
    )
  else:
    raise Exception("ERROR: missing_values must be 'drop' or 'fill'")

  # Strip out any characters we want to ignore
  for char in excl_chars:
    series = series.str.replace(
      char, 
      '', 
      regex=False
    )
  
  # Pad very short strings so that string_grouper doesn't drop them
  if pad_short_strings:
    series = pad_column(
      series, 
      ngram_size, 
      regex
    )

  return series

def append_column(
  df_matches, # The matches DataFrame we want to append column to
  df,         # Source DataFrame containing the column we want to append to the matches DataFrame
  col,        # Name of column we want to append
  side,       # 'left' or 'right', specifying the 'potential_matches' or 'to_populate' DataFrame, respectively
  label=None  # Optional label to append to column name to clarify its source
):
  # If the user gave us a label for more easily identifying the source of the column, append it.
  if label:
    col_out = f'{col} ({label})'
  else:
    col_out = col

  # Use the indexes in the source and match DataFrames to align/append the column
  df_matches.loc[:,col_out] = (
    df.loc[df_matches[f'{side}_index'],col]
    .reset_index(drop=True)
  )
  
  return df_matches

def pad_column(
  series, 
  ngram_size, 
  regex
):
  # Series containing the length of every string in 's', after applying the regex
  # that string_grouper uses internally to clean strings.
  series_re = series.apply(
    lambda record: len(
      re.sub(regex, r'', record)
    )
  )
  
  # Create a mask to select only the strings shorter than string_grouper's ngram_size, 
  # but larger than 0 so we dont cause empty values to get padded/matched.
  short_string_mask = (series_re < ngram_size) & (series_re > 0)
  
  # Update any short strings in the original Series in-place. This works by doing string addition 
  # to pad (and string multiplication for variable-length padding).
  series.update( 
    series[short_string_mask] + series_re[short_string_mask].apply( 
      lambda record: '_' * (ngram_size - record)
    )
  )
  
  return series

# Convenience function for merging a bunch of DataFrame columns
def merge_columns(df, cols):
  # If we only got 1 column, just return a copy of it
  if len(cols) == 1:
    return df[cols[0]].copy()
  
  # Take the very first column (we'll append the others next),
  # replace missing values with an empty string, then
  # explicitly convert the dtype to string
  col_out = df[cols[0]].fillna('').astype(str)
  
  # Loop over the other columns, appending as we go. Do the same
  # missing value + dtype conversion as in previous step.
  for c in cols[1:]:
    col_out = col_out.str.cat(
      df[c].fillna('').astype(str), 
      sep=' '
    )

  return col_out

def fuzzy_pairwise_compare(
  df_matches,
  to_populate_match_col,
  potential_matches_match_col,
  ignore_case=True,
  pad_short_strings=True
):
  # Track missing values to distinguish between them and true 0-similarity matches
  missing_mask = (
    df_matches[to_populate_match_col].isna() |
    df_matches[potential_matches_match_col].isna()
  )

  # Clean/sanitize the column from the "to_populate" DataFrame
  to_populate_cleaned = clean_column(
    df_matches[to_populate_match_col],
    pad_short_strings=pad_short_strings,
    missing_values='fill'
  )
  
  # Do the same for the "potential_matches" column
  potential_matches_cleaned = clean_column(
    df_matches[potential_matches_match_col],
    pad_short_strings=pad_short_strings,
    missing_values='fill'
  )

  # Run the columns through string_grouper's pairwise compare function
  similarities = compute_pairwise_similarities(
    to_populate_cleaned, 
    potential_matches_cleaned, 
    ignore_case=ignore_case
  )

  # Rename the new similarity column for extra clarity
  similarities.name = f'similarity [{to_populate_match_col} vs {potential_matches_match_col}]'

  # Add the missing values back in
  similarities[missing_mask] = pd.NA

  # Return the source DataFrame with the new similarity column appended
  return pd.concat(
    (df_matches, similarities),
    axis=1,
    ignore_index=False
  )
