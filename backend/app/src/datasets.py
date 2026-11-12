"""dataset metadata shared by the API and the importers"""

# Maps an IMDb dataset filename to the final database table it populates.
DATASET_TABLE_MAP: dict[str, str] = {
    "title.basics.tsv": "titles",
    "name.basics.tsv": "people",
    "title.ratings.tsv": "title_ratings",
    "title.episode.tsv": "episodes",
    "title.akas.tsv": "title_akas",
    "title.principals.tsv": "title_principals",
}
