# The Movement Cooperative Engineering Exercise

This repository contains a pair of scripts for matching Ohio voterfile IDs to some input data:
1. `get_ohio_voterfile.py` This script downloads voterfile data from the Ohio Secretary of State website. By default it only grabs the first 4 counties worth of data - this behavior can be changed by passing the optional kwargs `start_county` and `end_county` to the `get_voterfile` method in that script.
2. `voterfile_fuzzy_match.py` This script reads the voterfile data, plus some input data, and uses a fuzzy matching approach to populate voter IDs from the voterfile into the input file.

## How to run it

- First grab the required Python packages:
```
pip3 install pandas
pip3 install string_grouper
```

- Next, clone this repository and change directory to where you cloned it.
- Run `python3 get_ohio_voterfile.py` to download the voterfile data - it will be saved to a CSV file called `ohio_voterfile.csv`
- Run `python3 voterfile_fuzzy_match.py` to run the match - the results will be saved to a CSV file called `eng-matching-output.csv`

## How it works - lower level
This project uses a fuzzy matching technique. The core/lower-level matching methods can be found in `matching_tools.py`. A lot of the code in that `.py` file was not newly written specifically for this exercise - it is based heavily on my open-source fuzzy matching project (https://github.com/probablyfine/matchapp) and adapted for this demo. It uses the excellent open-source `string_grouper` package (https://github.com/Bergvca/string_grouper) to do the actual fuzzy comparisons.

Check out the `string_grouper` project (and the blog posts they link) for a very nice write-up of how it works, but the short version is that it breaks strings into [n-grams](https://en.wikipedia.org/wiki/N-gram), computes some [frequency stats](https://en.wikipedia.org/wiki/Tf–idf) on each n-gram occurance to build out feature vectors, and then computes similarities between those vectors using [cosine similarity](https://en.wikipedia.org/wiki/Cosine_similarity).

A huge advantage of this approach over other fuzzy matching techniques is that it is *really* fast. Try it out on a few million rows! (Okay that'll still take some time, but we're talking on the order of minutes, not hours or days.)

One quirk to watch out for: since the similarity score is influence by how frequently an n-gram appears in the "corpus", we will actually get different scores for the same string comparison if the inputs as a whole have changed. In practice I haven't found this to matter much, but it can be a little confusing.

## How it works - higher level
Once we have chosen our matching algorithm (see below for some other reasonable choices), the next step is to work out a strategy for comparing columns in the source files. I chose to follow a similar strategy I've previously described for my [matchapp](https://github.com/probablyfine/matchapp) software:

1. First, we **narrow the universe** of potential matches based on **full names**. We **cast a relatively wide net** in this step to deal with nicknames, mispellings, missing nameparts, etc., and the result is a bunch of potential matches.
2. The next step is to **narrow down this universe** of potential matches. This works by doing another fuzzy match - this time, it's going to be a **pairwise comparison** (as opposed to the wide-net search) of several fields, for each of the potential matches we found in the first step. We'll do fuzzy pairwise comparisons on **address** and **city**.
3. Next, we'll do pairwise **exact matches** (though case-insensitive) on a few other fields: **birth year**, **state** and **zip**. Fuzzy matching on these fields doesn't help us too much, as slight variations would likely indiciate a bad match.
4. The last step is to take a **weighted average** of all the similarities computed across all the fields, and **retain the top match** for each record. We'll also **set a threshold** for an acceptable weighted similarity, dropping any matches that are too weak.

How to choose field weights and acceptable thresholds is definitely an open question, and often comes down to making a judgement call, spot-checking results, and iterating if necessary. You can see my choices toward the top of `voterfile_fuzzy_match.py`; they're stored alongside column names in the variables `fuzzy_match_configuration` and `exact_match_configuration`. 

As you can see in the code, **full name** is the field with the highest weight. However, there are **several address fields**, and, in sum, address-parts have more weight than name-parts. This is heavily balanced out, though, since the initial universe of potential matches is determined only by full-name similarity (see step 1 above). This helps us avoid false positives stemming from multiple people living at the same address.

Ultimately the interactions between all these choices are fairly complicated, which is one clear downside to my approach in general.

## Potential improvements
- **Address standardization.** This would eliminate the need to use a fuzzy match on address-parts. We could instead just run an exact match on the standardized/normalized versions. Unfortunately this is usually a paid service. Google has a nice, easy-to-use API for this, but you pay per address.
- **Smarter name-parts parsing.** In my code, I've naively merged the voterfile fields for first, middle initial, and last name-parts, since this is the general format of the input file. We could do a bit better by analyzing the format for each record. For example, on row 96 of the input, we get only a last name; on row 103, we get first initial, middle initial, and full last name. We could create new fields for all these potential formats, and intelligently choose which to use for each row.
- **Tuning the weights and thresholds.** I didn't spend a huge amount of time optimizing these parameters. I generally found that changing them solves some problems while creating new problems, but there is sure to be a more optimal set than what I've stuck with. 
- **Auto-tuning.** If we wanted to get really fancy, we could possibly automate the weight and threshold tuning process. One approach would be to create a synthetic dataset where we know the actual matches ahead of time. We could then use a [grid search](https://en.wikipedia.org/wiki/Hyperparameter_optimization#Grid_search) to systematically sweep through values for each parameter, and choose the set that provides optimal results. Defining "optimal" is a bit of an open question, but I suspect area-under-the-curve of an [ROC analysis](https://towardsdatascience.com/understanding-auc-roc-curve-68b2303cc9c5) would be a pretty good metric to optimize.
- **Character encoding issues.** One issue that commonly impacts fuzzy name-matching is inconsistent character encoding. For example, one source might reference the name "Göransson" (with a unicode "ö") while another would drop the umlaut and use "Goransson" (with an ASCII "o"). There are a few ways to strip accents/diacritics from characters, but I like the [unidecode](https://pypi.org/project/Unidecode/) Python package. This doesn't seem to be a big issue in the Ohio voterfile data, but in general it's a good idea to do some normalization here.

## Alternate approaches
The cosine similarity metric we use for fuzzy matching is fast and reasonably effective, but there are some other interesting options.

- **Edit distance** is another class of fuzzy string comparison. It's basically a [family of heuristics](https://en.wikipedia.org/wiki/Edit_distance) that determines how many point-changes need to be made to a string to turn it into a reference string. I've used [this Python package](https://github.com/seatgeek/fuzzywuzzy) that implements Levenshtein distance - it works pretty well but it's very slow.
- **In-database solutions.** Some databases (e.g. Postgres) have support for [full text search](https://about.gitlab.com/blog/2016/03/18/fast-search-using-postgresql-trigram-indexes/), and will even do n-gram-based comparisons. I don't have much experience with this, but I suspect it might be possible to write some clever queries that leverage this feature set to populate e.g. voter IDs into an input table.
- **Pre-packaged type-ahead solutions.** In a similar vein, it might be possible to re-purpose a third-party type-ahead search tool for this use-case. In a previous job, our team used a nice, fast type-ahead search service called [meilisearch](https://www.meilisearch.com). It handles typos gracefully, you can specify any fields you like to index for searching, and you can even self-host the service to keep data private. It might take a bit of shoe-horning to use it for this kind of work, but it's a potentially interesting option.
