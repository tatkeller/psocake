import loadClients
import argparse

#runClient takes an argument "-host", enter the master's host name
# FIXME: remove the peak finding parameters from input argument
parser = argparse.ArgumentParser()
parser.add_argument("-host", help="master's host node")
parser.add_argument("-type", default = "clientPeakFinderAnt", help="type of worker/name of plugin, e.g. clientPeakFinder") # FIXME: empty default
parser.add_argument("-npix_min", default = 2, type = int, help = "minimum number of pixels for a peak")
parser.add_argument("-npix_max", default = 30, type = int, help = "maximum number of pixels for a peak")
parser.add_argument("-amax_thr", default = 300, type = int, help = "maximum value threshold")
parser.add_argument("-atot_thr", default = 600, type = int, help = "integral inside peak")
parser.add_argument("-son_min", default = 10, type = int, help = "signal over noise ratio")
parser.add_argument("-name", default = "Client", help = "Name of client for database")
parser.add_argument("-dbname" , default = "PeakFindingDatabase", help = "The database you would like to save your information to")
parser.add_argument("-isFirstWorker" , action='store_true', help = "This worker will train and run validation")
parser.add_argument("-v", action='store_true', help="Print debug information")
parser.add_argument("-vv", action='store_true', help="Print debug information")
parser.add_argument("-vvv", action='store_true', help="Print debug information")
args = parser.parse_args()

class runClients(object):
    def __init__(self, args):
        self.runClient = True
        self.clientType = args.type
        self.filename = "databaseLocation.txt"
        self.databaseLocation = self.locateDatabase()
        self.verbose = 0
        if args.vvv:
            self.verbose = 3
        elif args.vv:
            self.verbose = 2
        elif args.v:
            self.verbose = 1
        # FIXME: these kwargs belong to clientPeakFinder
        kwargs = {"isFirstWorker": args.isFirstWorker, "npix_min": args.npix_min, "npix_max": args.npix_max, "amax_thr": args.amax_thr,
              "atot_thr": args.atot_thr, "son_min" : args.son_min, "host" : args.host, "name" : args.name,
              "server" : self.databaseLocation, "dbname" : args.dbname, "verbose" : self.verbose}
        #print(kwargs)
        self.invoke_model(**kwargs)

    def locateDatabase(self):
        try:
            file = open(self.filename, "r")
        except IOError:
            print "Database not running"
            self.runClient = False
        return file.read()

    def invoke_model(self, **kwargs):
        """Load a plugin client by giving a client name, and entering arguments for corresponding algorithms
    
        Arguments:
        **kwargs -- arguments for peakFinding algorithm, master host name, and client name
        """
        if(self.runClient):
            print "client: ", self.clientType
            model_module_obj = loadClients.load_module(self.clientType)
            model_module_obj.algorithm(**kwargs)
        else:
            print("Start database and rerun client")

print("### Running runClients")
runClients(args)
