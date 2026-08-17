# Processing

Read each `.dly` member directly from `ghcnd_all.tar.gz`. Parse the fixed-width station, year, month, element, and 31 daily value groups. Invalid calendar days are discarded; missing values remain null. Write bounded Parquet shards and join station metadata only through the station identifier. Never extract the complete tar archive.
