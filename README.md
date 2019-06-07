# ds_statistics_creator
Python script for the creation of fake statistics records, specially recommended when testing some instance of a DSpace repository and no statistics data is available.

```
$ python ds_statistics_creator.py -h
[HELP] script -s <solr-server-url>  -i <community-handle> [[-e <search-core>| -d] -t <statistics-core> -c <count> --start <date> --end <date> -b --dry-run] 
      -s, --solr-server: specify the URL to SOLR Server. Don't include the core name, i.e. 'http:localhost:7080/solr'.
      -i, --handle: the HANDLE of the target community to generate test statistics records.
      -t, --statistics-core: specify the name of the statistics core. 'statistics' is the default.
      -c, --count: specify the total number of statistics records you want to create. Mutually exclusive with "--count-per-object" option. Defaults to 10000.
      -p, --count-per-object: specifiy the total number of records created by every child object of the target community. This option is mutually exclusive with "--count" option.
      -b, --include-bots: use this flag if you want to combine both "normal" and "of known bots/crawlers" User Agents in created records.
      --start: specifiy the start datetime for the generation of the statistics records. This date must be lesser than NOW or the --end date parameter.
                The string format of this parameter could be "year-month-date" or "year-month-date hour:minutes:seconds". I.e. "2019-01-21" or "2019-01-21 12:50:00".
                By default, the start date corresponds to 5 years back.
      --end: specifiy the end datetime for the generation of the statistics records. This date must be bigger than --start date parameter but must not be bigger than NOW.
                The string format of this parameter could be "year-month-date" or "year-month-date hour:minutes:seconds". I.e. "2019-01-21" or "2019-01-21 12:50:00".
                By default, the end date is NOW.
      --dry-run: run the command in a SAFE-MODE. No records will be POSTed to Solr server. The records created will be seen
                in a temporary file at "/tmp/solr_records_dry_run_mode.json".
    
  **CHILDREN DATA SOURCE** (Solr or PostgreSQL):
  ====================================
    You can specify the source from where get the children related (SUB-COMMUNITIES, COLLECTIONS, ITEMS, BITSTREAMS)
    to community specified.
    OPTIONS:
        -e <name_core>, --search-core <name_core>: specify the name of the search core. 'search' is the default. Use this option if you want to use SOLR as data source.
                This option lacks on obtain some child information (1- Cannot obtain subcommunities info, 2- Cannot obtain bitstreams info).
        -d, --database-info: interactive mode where prompt for database connection data. Use this option if you want to user PostgreSQL as data source. It is recommended
                to use a pg_user with SELECT and TEMPORARY permissions (for read and create temporary tables).

  >>INFO<<: This script index testing records for Solr Statistics core in DSpace. By default, it generates testing records within the date lapse of five years until now.
```
