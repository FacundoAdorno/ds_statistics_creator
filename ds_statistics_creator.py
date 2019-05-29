#!/bin/python
#DSpace Solr Statistics Records Creator. Recommended its use in software DSpace (https://duraspace.org/dspace/)
#v0.1

import contextlib,urllib,urllib2,json,sys,progressbar,getopt,random,socket,struct, time, getpass, pkg_resources, psycopg2, os.path
from pkg_resources import DistributionNotFound, VersionConflict
from test_data import *
from datetime import datetime
from dateutil.rrule import rrule, MINUTELY
from dateutil.relativedelta import *
from dateutil.parser import *

page_size = 2500
solr_server = ""
search_core_name='search'
statistics_core_name='statistics'
comm_handle = ""
comm_uid = ""
base_url = "{0}"
count_to_process = 10000
totalDocs = 0
dry_run_mode = False
dry_run_tmpf = None
dry_run_tmpf_location = "/tmp/solr_records_dry_run_mode.json"
SOLR_SOURCE = "SOLR"
PG_SOURCE = "POSTGRESQL"
children_data_source = "SOLR" #defaults to solr
include_bots = False
bots_count = 0
end_datetime = datetime.now()
start_datetime= end_datetime + relativedelta(years=-5)
#Packages required for this script
dependencies = ['psycopg2>=2.8.2', 'progressbar>=2.5', 'python-dateutil>=2.8.0']
#DB PostgreSQL connection data
database_connection_data = {"host": "localhost", "port": "5432", "username": "", "password":"", "database": ""}
connection = None

"""
Process all childs (Sub-communities, Collections, and Items) for specified Community, and create
test statistics record. Then POST those records to Solr Server at the statistics core specified 
(defaults to 'statistics').

Until now, only "view" statistics_type records are created.
"""
def process():
    global comm_handle, comm_uid, include_bots, count_to_process, bots_count, start_datetime, end_datetime
    totalDocs = 0
    start_time = time.time()
    info("Getting childs of %s community..." % comm_handle)
    #Get info of child (community, collection, item, NO bitstream)
    if children_data_source == SOLR_SOURCE:
        children_data = getChildrenFromSolr()
    else: # source == PG_SOURCE
        children_data = getChildrenFromDB()
    ##Add the parent community object in order to create statistics records for it too...
    children_data.append( {"search.resourceid": comm_uid, "search.resourcetype": 4 })

    #Starting processing with pagination
    bar = createProgressBar(count_to_process) 
    start_from = 0
    #hook for pre-processing
    pre_process(start_time)
    info("Generating records between dates '%s' and '%s'." % (start_datetime.strftime("%Y-%m-%d %H:%M:%S"), end_datetime.strftime("%Y-%m-%d %H:%M:%S")))
    info("POSTing %i records to Solr Server at %s..." % (count_to_process, getStatisticsURL()))
    bar.start()
    while (start_from < count_to_process):
        records = []
        page_pos = 0
        ch_data_size = len(children_data)
        while (page_pos < page_size and start_from + page_pos < count_to_process):
            records.append(createRandomStatisticsRecord(children_data[page_pos % ch_data_size], start_datetime, end_datetime, include_bots))
            page_pos += 1
        if dry_run_mode:
            records_str = ",".join(records)
            if start_from + page_pos < count_to_process:
                #if there is more records to get, then add ending ","...
                records_str += ","
        else:
            records_str =  "[" + ",".join(records) + "]"
        postJsonData(records_str)
        
        if (start_from + page_size > count_to_process):
            start_from = count_to_process
        else:
            start_from = start_from + page_size
        bar.update(start_from)
    
    bar.finish()
    #hook for post-processing
    post_process(start_time)

"""
Obtain children of the Community specified at invocation from Solr 'search' core. Sub-communities and bitstreams cannot be obtained using this method.
"""
def getChildrenFromSolr():
    global page_size,comm_handle,comm_uid
    children_list = []
    comm_uid_q_params = {"q" : "handle:({0})".format(comm_handle), "wt":"json", "indent":"true"}
    community_uid_query_url= getSearchURL() + "/select?" +  urllib.urlencode(comm_uid_q_params)
    
    comm_data = getJsonResponse(community_uid_query_url) 
    totalDocs = comm_data["response"]["numFound"]
    if totalDocs < 1:
        exitError("[I] No community is indexed at Solr Server with HANDLE=%s..." % (comm_handle))
    else:
        info("Starting getting %d Solr Documents." % (totalDocs))
        comm_uid=comm_data["response"]["docs"][0]["search.resourceid"]
    info("The UID for community %s is %s" % (comm_handle,comm_uid))
    
    #Retrieving child UIDs, using bar to show progress 
    comm_children_q_params = {"q" : "location.comm:({0})".format(comm_uid),"wt":"json", "indent":"true"}
    child_data = getJsonResponse(getSearchURL() + "/select?" +  urllib.urlencode(merge_two_dicts(comm_children_q_params, {"rows":0})))
    total_child_count = child_data["response"]["numFound"] 
    if (total_child_count < 1):
        info("Community has no child...")
    else:
        info("Community %s has %i childs. Processing..." % (comm_handle, total_child_count))
    
    bar = createProgressBar(total_child_count) 
    bar.start()
    start_from = 0
    while (start_from <= total_child_count):
        page_child_data = getJsonResponse(getSearchURL() + "/select?" +  urllib.urlencode(merge_two_dicts(comm_children_q_params, {"start": str(start_from) ,"rows": str(page_size)})), quiet=True)
        for result in page_child_data["response"]["docs"]:
            dso_child_dict = {}
            dso_child_dict["search.resourceid"] = result["search.resourceid"]
            dso_child_dict["search.resourcetype"] = result["search.resourcetype"]
            if "location.comm" in result:
                dso_child_dict["location.comm"] = result["location.comm"]
            if "location.coll" in result:
                dso_child_dict["location.coll"] = result["location.coll"]
            children_list.append(dso_child_dict)
            #info(result["search.resourceid"])

        start_from = start_from + page_size
        if(start_from <= total_child_count):
            bar.update(start_from)
        
    bar.finish()

    return children_list

"""
Obtain children of the Community specified at invocation from PostgreSQL database. Through this method can obtain all children from a Community (items, bitstreams and collections).
"""
def getChildrenFromDB():
    global comm_handle, comm_uid
    pg_cur = connection.cursor()
    
    ### Get comm_handle data
    pg_cur.execute("SELECT resource_id FROM handle WHERE handle = '%s'" % comm_handle)
    comm_query_result = pg_cur.fetchall() 
    if len(comm_query_result) < 1:
        exitError("[I] No community exists in database with HANDLE=%s..." % (comm_handle))
    else:
        comm_uid =comm_query_result[0][0] 
    info("The UID for community %s is %s" % (comm_handle,comm_uid))

    pg_cur.execute(open("create_aux_temp_tables.sql", "r").read())
    pg_cur.execute("SELECT uuid, uuid_path  FROM tree WHERE depth > 0 AND path like '%%.%s.%%'" % comm_handle) #depth = 0 is comm_handle 
    subcomm_rows = pg_cur.fetchall()
    #pg_cur.execute("SELECT * FROM cant_per_com")
    #all_child_uuids += [subc[1] for subc in subcomm_rows] #columna uuid_path
   
    ###Add sub-communities children
    comm_children_list = []
    for subcomm in subcomm_rows:
        uuid, uuid_path = subcomm[0], subcomm[1]
        #"uuid_path" has the form ".uuid_ancesterN.uuid_ancesterN-1.*.uuid_ancester0.uuid_self."
        uuids_parents = uuid_path[0:uuid_path.find(uuid)-1]
        if (uuids_parents.startswith('.')): #remove initial dot
            uuids_parents = uuids_parents[1:] 
        if (uuids_parents.endswith('.')): #remove final dot
            uuids_parents = uuids_parents[:-1]
        comm_children_list.append({"search.resourceid": uuid, "search.resourcetype": 4, "location.comm": uuids_parents.split(".")})

    ### Add Collections children of previous calculated Communities. Collection can be under Main Community for this script or its subcommunities...
    coll_children_list = []
    ## Also get direct children collections of the "Main Community"
    comms_for_get_coll_children = [comm_uid]
    comms_for_get_coll_children += [subc["search.resourceid"] for subc in comm_children_list] #get all uuids from sub-comms
    for comm_ch_uuid in comms_for_get_coll_children:
        current_comm = filter(lambda comm: comm['search.resourceid'] == comm_ch_uuid, comm_children_list)
        pg_cur.execute("SELECT collection_id FROM community2collection WHERE community_id = '%s'" % comm_ch_uuid)
        for coll_uuid in pg_cur.fetchall():
            #current_comm is empty for Main Community...
            if not current_comm:
                loc_comm = [comm_uid]
            else:
                loc_comm = current_comm[0]["location.comm"]
            coll_children_list.append({"search.resourceid": coll_uuid[0], "search.resourcetype": 3, "location.comm": loc_comm})
   
    ### Add Items children for previously Collections calculated
    item_children_list = []
    for coll_ch in coll_children_list:
        pg_cur.execute("SELECT item_id FROM collection2item WHERE collection_id = '%s'" % coll_ch["search.resourceid"])
        for item_uuid in pg_cur.fetchall():
            item_children_list.append({"search.resourceid": item_uuid[0], "search.resourcetype": 2, "location.comm": coll_ch["location.comm"], 
                "location.coll": [coll_ch["search.resourceid"]]})
            #TODO get ALL parent collections of an item. An Item can be under more than one Collection, but only one is its real parent...
    
    ### Add Bitstreams children (from ORIGINAL bundle) for previously Items calculated
    bs_original_children_list = []
    ## First calculate what is the "dc.title" metadata, so you can know what bundle is ORIGINAL...
    pg_cur.execute("SELECT mf.metadata_field_id FROM metadatafieldregistry mf WHERE mf.metadata_schema_id \
            IN (SELECT metadata_schema_id FROM metadataschemaregistry WHERE short_id = 'dc') AND element = 'title' AND qualifier IS NULL") 
    dc_title_result = pg_cur.fetchall()
    if not dc_title_result:
        exitError("BAD ERROR! No \"dc.title\" metadata exists in this DSpace database!! Fatal exit...")
    dc_title_id = dc_title_result[0][0]
    for item_ch in item_children_list: 
        pg_cur.execute("SELECT b2b.bitstream_id FROM bundle b INNER JOIN metadatavalue mv ON (b.uuid = mv.dspace_object_id) \
                INNER JOIN item2bundle i2b ON (b.uuid = i2b.bundle_id) INNER JOIN bundle2bitstream b2b ON (i2b.bundle_id = b2b.bundle_id) \
                WHERE mv.metadata_field_id = %s AND mv.text_value = 'ORIGINAL' AND i2b.item_id = '%s'" % (dc_title_id, item_ch["search.resourceid"]))
        for bs_uuid in pg_cur.fetchall():
            bs_original_children_list.append({"search.resourceid": bs_uuid[0], "search.resourcetype": 0, "location.comm": item_ch["location.comm"], 
                "location.coll": item_ch["location.coll"], "location.item": [item_ch["search.resourceid"]]})

    #Return all children lists concatenated...
    return comm_children_list + coll_children_list + item_children_list + bs_original_children_list

"""
Things to do before main process...
"""
def pre_process(start_time):
    global dry_run_mode
    if dry_run_mode:
        writeDryRunMode("[")

"""
Things to do after main process...
"""
def post_process(start_time):
    global dry_run_mode,dry_run_tmpf_location,include_bots,count_to_process,bots_count
    if dry_run_mode:
        writeDryRunMode("]")
        info("DRY-RUN-MODE: File with fake statistics records was created at \"%s\"." % dry_run_tmpf_location)
    if include_bots:  
        info("BOTS: The %.2f%%  (%i/%i) of created records coincide with known bots/spiders User Agents..." % ((bots_count * 100)/count_to_process, bots_count, count_to_process))
    info("Processing was finished successfully in %.2f seconds..." % (round(time.time() - start_time,2)))
    info("Now you must run a Solr Optimize at statistics core in order to see the changes...")

def getSearchURL():
    global search_core_name, solr_server
    return solr_server + "/" + search_core_name

def getStatisticsURL():
    global statistics_core_name, solr_server
    return solr_server + "/" + statistics_core_name

def parseParams(argv):
    global solr_server, comm_handle, statistics_core_name, search_core_name, count_to_process,dry_run_tmpf_location, dry_run_mode, dry_run_tmpf, count_to_process, database_info, children_data_source, include_bots, start_datetime, end_datetime
    
    help_text = """[HELP] script -s <solr-server-url>  -i <community-handle> [[-e <search-core>| -d] -t <statistics-core> -c <count> --start <date> --end <date> -b --dry-run] 
      -s, --solr-server: specify the URL to SOLR Server. Don't include the core name, i.e. \'http:localhost:7080/solr\'.
      -i, --handle: the HANDLE of the community to generate test statistics records.
      -t, --statistics-core: specify the name of the statistics core. 'statistics' is the default.
      -c, --count: specify the total number of statistics records you want to create. Defaults to %i.
      -b, --include-bots: use this flag if you want to combine both "normal" and "of known bots/crawlers" User Agents in created records.
      --start: specifiy the start datetime for the generation of the statistics records. This date must be lesser than NOW or the --end date parameter.
                The string format of this parameter could be "year-month-date" or "year-month-date hour:minutes:seconds". I.e. "2019-01-21" or "2019-01-21 12:50:00".
                By default, the start date corresponds to 5 years back.
      --end: specifiy the end datetime for the generation of the statistics records. This date must be bigger than --start date parameter but must not be bigger than NOW.
                The string format of this parameter could be "year-month-date" or "year-month-date hour:minutes:seconds". I.e. "2019-01-21" or "2019-01-21 12:50:00".
                By default, the end date is NOW.
      --dry-run: run the command in a SAFE-MODE. No records will be POSTed to Solr server. The records created will be seen
                in a temporary file at \"%s".
    
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
  """ % (count_to_process, dry_run_tmpf_location)
    try:
        opts, args = getopt.getopt(argv,"hs:i:e:t:c:db",["solr-server=","uid=","search-core=","statistics-core=","count=","database-info","include-bots","dry-run","start=","end="])
    except getopt.GetoptError:
       print help_text
       sys.exit(2)
    for opt, arg in opts:
       if opt == '-h':
          print help_text
          sys.exit()
       elif opt in ("-s", "--solr-server"):
          solr_server = arg
          if (not solr_server.startswith("http://")):
              solr_server = "http://" + solr_server
       elif opt in ("-i", "--handle"):
          comm_handle = arg
       elif opt in ("-e", "--search-core"):
           search_core_name = arg
       elif opt in ("-t", "--statistics-core"):
           statistics_core_name = arg
       elif opt in ("-c", "--count"):
           try:
               count_to_process = int(arg)
           except ValueError:
               exitError("Value '%s' is invalid. Please correct it..." % arg)
       elif opt in ("-d", "--database-info"):
           children_data_source = PG_SOURCE
       elif opt in ("-b", "--include-bots"):
           include_bots = True
       elif opt in ("--start"):
           start_datetime = parseDate(arg)
       elif opt in ("--end"):
           end_datetime = parseDate(arg)
       elif opt in ("--dry-run"):
           dry_run_mode = True
           dry_run_tmpf = createTempFile(dry_run_tmpf_location)
    if (solr_server == "" or comm_handle == ""):
        print '[ERROR] Missing required parameters...'
        print help_text
        sys.exit(2)
    #check if start date and end date are ok
    dtnow = datetime.now()
    if (start_datetime > dtnow or end_datetime > dtnow):
        exitError("Starting or ending date must not be bigger than now [starting='%s', ending='%s']." % (start_datetime, end_datetime))
    elif (start_datetime >= end_datetime):
        exitError("Starting date must be smaller than ending date [starting='%s', ending='%s']." % (start_datetime, end_datetime))
    #Prompt for database data connection if required.
    if (children_data_source == PG_SOURCE):
        promptForDBInfo()

#<===== AUX =========>
def exitError(message):
    print "[ERROR] " + message
    sys.exit(2)

def info(message):
    print "[I] " + message

def warn(message):
    print "[WARN] " + message

def parseDate(date):
    try:
        return parse(date)
    except ValueError as e:
        exitError("Date format invalid! " + str(e))

def createTempFile(location="./temp.file"):
    try:
        if (os.path.isfile(location)):
            os.remove(location)
    except OSError:
        exitError("File at %s cannot be deleted when running in DRY-RUN mode. Exiting..." % location)
    temp_file = open(location, 'w')
    return temp_file

"""
Write to a temporary file created for dry-run executions...
"""
def writeDryRunMode(stringToFile):
    global dry_run_tmpf
    if (stringToFile != ""):
        #print >> dry_run_tmpf, stringToFile
        dry_run_tmpf.write(stringToFile)
    else:
        warn("Trying to write empty data in dry-run mode...")
        

def confirmProcess():
    global comm_handle, count_to_process, dry_run_mode
    if dry_run_mode:
        info("Running in DRY-RUN mode...")
        return
    confirm = raw_input("[QUESTION] Are you sure to continue and create fake statistics records for community \"%s\"?\n\
\t You are about to create and post %i records to %s solr server. This is not recommended in a PRODUCTION environment as it can make a mess with your real data... [y/n]" % 
    (comm_handle, count_to_process, getStatisticsURL()))
    if not(confirm == "y" or confirm == "Y"):
        info("Exiting by user demand...")
        sys.exit()
    confirm2 = raw_input("[QUESTION] Last confirmation required: you are about to create and post %i fake records to %s solr server. This is correct?... [y/n]" % 
    (count_to_process, getStatisticsURL().upper()))
    if not(confirm2 == "y" or confirm2 == "Y"):
        info("Exiting by user demand...")
        sys.exit()

def promptForDBInfo():
    global database_connection_data
    database_connection_data["host"] = raw_input("[PG Data] Please enter the <<hostname>> for database server[defaults 'localhost']: ") or "localhost" 
    database_connection_data["port"] = raw_input("[PG Data] Please enter the <<port>> for database server[defaults '5432']: ") or "5432"
    database_connection_data["database"] = raw_input("[PG Data] Please enter the <<database name>> for DSpace: ")
    database_connection_data["username"] = raw_input("[PG Data] Please enter the <<username>> for DSpace database (recommended user with READ and TEMPORARY permissions ONLY): ")
    print "[PG Data] Please enter the <<password>> for Dspace database."
    database_connection_data["password"] = getpass.getpass()
   
    #check if there is not empty data required for PG connection
    if (not database_connection_data["database"] or not database_connection_data["username"] or not database_connection_data["password"]):
        exitError("Required data for PostgreSQL database connection is not specified. Exiting...") 
    else:
        #create database connection
        createDBConnection()

def createDBConnection():
    global connection
    if connection is None:
        info("Creating database connection at %s@%s:%s..."%(database_connection_data["host"], database_connection_data["port"], database_connection_data["database"]))
        try:
            connection = psycopg2.connect(host=database_connection_data["host"], port=database_connection_data["port"], database=database_connection_data["database"], user=database_connection_data["username"], password=database_connection_data)
        except:
            exitError("Cannot connect to PG database. Please correct the connection parameters...")
    info("Connection established successfully.")
    return connection

def closeDBConnection():
    global connection
    if not connection is None:
        connection.close()

def postJsonData(json_data=''):
    global dry_run_mode, dry_run_tmpf
    #Check if the script is running at "dry-run" mode...
    if dry_run_mode:
        writeDryRunMode(json_data)
        return
    #If not in "dry-run" mode, then continue...
    url = getStatisticsURL() + "/update"
    if not json_data == '':
        cont_len = len(json_data) 
        try:
            with contextlib.closing(urllib2.urlopen(urllib2.Request(url, json_data, {'Content-Type': 'application/json', 'Content-Length': cont_len}))) as response:
                if not (response.getcode() == 200):
                    exitError("An error ocurred during the post process to Solr server...")
        except urllib2.URLError:
            exitError("Cannot establish connection with server at %s. Exiting..." % getStatisticsURL())
    else:
        exitError("JSON data is empty...")
"""
Connect to the URL specified, it must return a SOLR JSON response object.
Then parse the result and return an object resulting of parse the JSON response.
"""
def getJsonResponse(json_url,quiet=False):    
    if not quiet:
        info("Connecting to URL %s" % (json_url))
    try:
        with contextlib.closing(urllib.urlopen(json_url)) as response:
            json_data = json.loads(response.read())
    except IOError:
        exitError("Connection to URL=%s cannot be stablished. Exiting..." % json_url)
    #If success, return Json representation object
    return json_data


def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z 

def createProgressBar(max_size):
    return  progressbar.ProgressBar(maxval=max_size, term_width=100,  widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])

#<========= RANDOM DATA HELPERS ===============>
def getRandomIPv4():
    return socket.inet_ntoa(struct.pack('>I', random.randint(1, 0xffffffff)))

def getRandomURL():
    global url_random_list
    return url_random_list[random.randint(0,49)]

def getRandomDomain():
    global domain_random_list
    return domain_random_list[random.randint(0,49)]

def getRandomUserAgent(use_bots=False):
    global user_agent_random_list, bot_user_agent_random_list, bots_count
    #Next expression allows the use of combined "normal" and "bots" user agent field. If "use_bots" is False, this expression always returns False.
    bot_decision = use_bots and (random.randint(0,10) % 2)
    if bot_decision:
        bots_count += 1
        return bot_user_agent_random_list[random.randint(0,19)]
    else:
        return user_agent_random_list[random.randint(0,14)]

#Cache of datetimes. Contains datetime objects generated randomly every 15 minutes beetween the specificied script start and end dates...
datetime_cache_list = None
def getRandomDateTime(dtstart, dtend):
    global datetime_cache_list
    #Initialize cache of datetimes...
    if not datetime_cache_list:
        #TODO add debug mode and inform when generating this cache...
        datetime_cache_list = list(rrule(MINUTELY, interval=15, dtstart=dtstart, until=dtend))
    return random.choice(datetime_cache_list).strftime("%Y-%m-%dT%H:%M:%SZ")

def getRandomGeolocationData():
    global location_random_data
    return location_random_data[random.randint(0,20)]

def createRandomStatisticsRecord(child_dict, stdate, etdate, use_bots=False):
    location = getRandomGeolocationData()
    view_record_tmpl = "{"
    view_record_tmpl += "\"ip\": \"%s\", \"referrer\": \"%s\", \"dns\": \"%s\", \"userAgent\": \"%s\", \"isBot\": false, \"time\": \"%s\" , \"statistics_type\": \"view\", \"continent\": \"%s\", \"countryCode\": \"%s\", \"city\": \"%s\""
    
      
    view_record_tmpl += ", \"id\": \"%s\", \"type\": %i" % (child_dict["search.resourceid"], child_dict["search.resourcetype"]) 
    if "location.comm" in child_dict:
        view_record_tmpl += ", \"owningComm\": [ %s ]" % ("\"" + '","'.join(child_dict["location.comm"]) + "\"")
    if "location.coll" in child_dict:
        view_record_tmpl += ", \"owningColl\": [ %s ]" % ("\"" + '","'.join(child_dict["location.coll"]) + "\"")
    if "location.item" in child_dict: 
        ## When comes this key in child_dict, then a "download" view record is created instead a "regular" view record... 
        view_record_tmpl += ", \"owningItem\": [ %s ], \"bundleName\": [ \"ORIGINAL\" ]" % ("\"" + '","'.join(child_dict["location.item"]) + "\"")
        

    view_record_tmpl += "}" 
    return view_record_tmpl % (getRandomIPv4(), getRandomURL(), getRandomDomain(), getRandomUserAgent(use_bots), getRandomDateTime(stdate, etdate), location[0], location[1], location[2])


#<==== END AUX =======>

#################################################
########### MAIN MAIN MAIN MAIN MAIN ############
#################################################
def main(argv):
    # here, if a dependency is not met, a DistributionNotFound or VersionConflict exception is thrown. 
    try:
        pkg_resources.require(dependencies)
    except (DistributionNotFound, VersionConflict) as e:
        info(str(e))
        exitError("A required dependency is not installed! Run a 'pip install -r requirements.txt' to solve this.") 
    parseParams(argv) 
    confirmProcess()
    process()

#<--- ENTRY-POINT --->
if __name__ == "__main__":
   main(sys.argv[1:])



