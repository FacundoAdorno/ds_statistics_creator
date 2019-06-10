# ds_statistics_creator
Python script for the creation of fake statistics records, specially recommended when testing some instance of a DSpace repository and no statistics data is available.

```bash
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

## What does this script?
This script allows you to create and post an arbitrarious number of records (*millons* if required) of "statistical" data for [SOLR-Statistics module](https://wiki.duraspace.org/display/DSDOC6x/SOLR+Statistics) in DSpace, that is, it allows populate with fake and random data the 'statistics' Solr core of a DSpace instance. The Solr server must be reachable via HTTP by the machine executing this script.

The records created by this script are vinculated with the "target community", that is the community specified with the `-i |--handle` parameter. These records are related to this community and its children (communities, collections, items and bitstreams).

The format of this data is described at [DSpace documentation](https://wiki.duraspace.org/display/DSDOC6x/SOLR+Statistics#SOLRStatistics-Whatisexactlybeinglogged?), but basically exists four types of statistics records in DSpace: *views, downloads, searches, and workflow usage*. Until now, this scripts only create "view" and "download" statistics records.

## When/Where to use this script?
Is highly encouraged to use this script only for test purposes. You should use a testing instance of Solr core for DSpace as the endpoint where post fake data created by this script, since this script can post millons of records when you confirm. **The actions of this scripts cannot be undone easily, so use this script under your own risk.**

> For more security, before running this script, you can check the output data generated if you append the `--dry-run` flag when you execute it. 

## How to use this script?
This script only require the following parameters to run:
1. The endpoint URL where Solr Server test instance used by your DSpace is located.
2. The HANDLE of the community for what you want to create fake test records.

By default, it push all created records to "solr/statistics" core in Solr. However, you can change this endpoint name if this is not the name of your "statistics" core at your DSpace instance configuration. 

Then you can specify others optional parameters, run with `--help` flag.

### Safe run mode
For test the output result of script after appling this in a test environment, you can run it with the `--dry-run` flag. This will create a temporal file containing all fake records that would have been posted to Solr server.

### Optimize Solr after every execution

After script execution finish, you must run the `bash [path-to-dspace]/bin/dspace stat-utils -o` command, in order to see changes made.

## How to modify fake data?

The data used for create random statistics records are localized at "aux" submodule. For instance, if you want to add "Tokyo" as a new geo-localization data for the creation of the fake records, then you must append the following python list at ["location_random_data"](https://github.com/FacundoAdorno/ds_statistics_creator/blob/770c237236b521a144a074203736883aeb68abce/aux/aux_data.py#L11):
```python
location_random_data = [ ... ,
            ["AS", "JP", "Tokyo"]
     ]
```
And so on, you can modify any data located at "aux_data.py" file:
* a randomlist of "referrer" URLs,
* a test list of bots user agents,
* a test list of non-bots user agents
* a random list of "Reverse DNS" URLs.

## Possible children data sources

You can specify differents data sources from where obtain children information of the target community:

* **Solr as source**: this option retrieve children information from Discovery core. By default, this core is named as 'search', but you can specify any other name with the `--search-core` parameter. This option lacks of information, so you cannot get (1) sub-communities and (2) bitstreams data.

* **PostgreSQL database as source**: interactive mode where prompt for database connection data. Use this option if you want to user PostgreSQL as data source. It is recommended to use a pg_user with [SELECT and TEMPORARY permissions](https://www.postgresql.org/docs/10/sql-grant.html#SQL-GRANT-DESCRIPTION-OBJECTS) (for read and create temporary tables).
  * This option needs to create temporary tables for construct the (potentially) deep tree of elements that conforms the repository structure.

The default data source is Solr, but is highly recommended to use PostgreSQL database source, as it does not lacks of information when retrieve data for community children.

## EXAMPLES

-TODO

