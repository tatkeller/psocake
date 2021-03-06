import psana
import numpy as np
from psalgos.pypsalgos import PyAlgos
from ImgAlgos.PyAlgos import PyAlgos as PA
from scipy.spatial.distance import cdist
from scipy.spatial import distance
import time
import zmq
import json
import base64
from psana import *
import random
from peaknet import Peaknet
from crawler import Crawler
#import pymongo

#Intialize global variables

#Amount of events sent to PeakNet
batchSize = 64
#Calculated Likelihood that counts as a "good event"
goodLikelihood = .03
#Limit of events iterated through in a run
eventLimit = 1000
#Minimum number of peaks to be found to calculate likelihood
goodNumPeaks = 15
#Minimum number of events to be found before peak finding on 1000 events of a run
minEvents = 3
#Initialization of Peaknet
psnet = Peaknet()



def pull():
    """ Recieve information from the master zmq socket. 
    When called, the program will wait until information 
    has been pushed by the master zmq socket.
    """
    context = zmq.Context()
    results_receiver = context.socket(zmq.PULL)
    results_receiver.connect("tcp://127.0.0.1:5560")
    result = results_receiver.recv_json()    
    print("I just pulled:", result)  
    return result

def push(val):
    """ Give information to the master zmq socket.
    
    Arguments:
    val -- The information/value that will be pushed to the master zmq socket.
    """
    context = zmq.Context()
    zmq_socket = context.socket(zmq.PUSH)
    zmq_socket.bind("tcp://127.0.0.1:5559")
    print("I am pushing:", val)
    zmq_socket.send_json(val)


#converts a numpy array to be sent through json
def bitwise_array(value):
    """ Convert a numpy array to a form that can be sent through json.
    
    Arguments:
    value -- a numpy array that will be converted.
    """
    if np.isscalar(value):
        return value
    val = np.asarray(value)
    return [base64.b64encode(val), val.shape, val.dtype.str]

def calculate_likelihood(qPeaks):
    """ Calculate the likelihood that an event is a crystal

    Arguments:
    qPeaks -- 
    """
    nPeaks = int(qPeaks.shape[1])
    selfD = distance.cdist(qPeaks.transpose(), qPeaks.transpose(), 'euclidean')
    sortedSelfD = np.sort(selfD)
    closestNeighborDist = sortedSelfD[:, 1]
    meanClosestNeighborDist = np.median(closestNeighborDist)
    closestPeaks = [None] * nPeaks
    coords = qPeaks.transpose()
    pairsFound = 0.
    for ii in range(nPeaks):
        index = np.where(selfD[ii, :] == closestNeighborDist[ii])
        closestPeaks[ii] = coords[list(index[0]), :].copy()
        p = coords[ii, :]
        flip = 2 * p - closestPeaks[ii]
        d = distance.cdist(coords, flip, 'euclidean')
        sigma = closestNeighborDist[ii] / 4.
        mu = 0.
        bins = d
        vals = np.exp(-(bins - mu) ** 2 / (2. * sigma ** 2))
        weight = np.sum(vals)
        pairsFound += weight
    pairsFound = pairsFound / 2.
    pairsFoundPerSpot = pairsFound / float(nPeaks)
    return [meanClosestNeighborDist, pairsFoundPerSpot]

#gets detector information
def getDetectorInformation(exp, runnum, det):
    """ Returns the detector, the peak finding algorithm, and the number of events for
    this run.
    
    Arguments:
    exp -- the experiment name
    runnum -- the run number for this experiment
    det -- the detector used for this experiment
    """
    ds = psana.DataSource('exp=%s:run=%d:idx'%(exp,runnum))
    d = psana.Detector(det)
    d.do_reshape_2d_to_3d(flag=True)
    alg = PyAlgos(mask = None, pbits = 0)
    alg.set_peak_selection_pars(npix_min=2, npix_max=30, amax_thr=300, atot_thr=600, son_min=10)
    hdr = '\nSeg  Row  Col  Npix    Amptot'
    fmt = '%3d %4d %4d  %4d  %8.1f'
    run = ds.runs().next()
    times = run.times()
    env = ds.env()
    numEvents = len(times)
    mask = d.mask(runnum,calib=True,status=True,edges=True,central=True,unbond=True,unbondnbrs=True)
    return [d, alg, hdr, fmt, numEvents, mask, times, env, run]

def getPeaks(d, alg, hdr, fmt, mask, times, env, run, j):
    """Finds peaks within an event, and returns the event information, peaks found, and hits found
    
    Arguments:
    d -- psana.Detector() of this experiment's detector
    alg -- the algorithm used to find peaks
    hdr -- Title row for printed chart of peaks found
    fmt -- Locations of peaks found for printed chart
    mask -- the detector mask
    times -- all the events for this run
    env -- ds.env()
    run -- ds.runs().next(), the run information
    j -- this event's number
    
    """
    evt = run.event(times[j])
    try:
        nda = d.calib(evt) * mask
    except TypeError:
        nda = d.calib(evt)
    if (nda is not None):
        peaks = alg.peak_finder_v3r3(nda, rank=3, r0=3, dr=2, nsigm =5)
        numPeaksFound = len(peaks)
        alg = PA()
        thr = 20
        numpix = alg.number_of_pix_above_thr(nda, thr)
        #totint = alg.intensity_of_pix_above_thr(nda, thr)
        return [evt, nda, peaks, numPeaksFound, numpix]
    else:
        return[None,None,None,None,None]

def getLikelihood(d, evt, peaks, numPeaksFound):
    """ Returns the likeligood value for an event with 15 or more peaks
    
    Arguments:
    d -- psana.Detector() of this experiment's detector
    evt -- ds.env()
    peaks -- the peaks found for this event
    numPeaksFound -- number of peaks found for this event
    """
    if (numPeaksFound >= goodNumPeaks):
        ix = d.indexes_x(evt)
        iy = d.indexes_y(evt) 
        d.ipx, d.ipy = d.point_indexes(evt, pxy_um=(0, 0))
        d.iX = np.array(ix, dtype=np.int64)
        d.iY = np.array(iy, dtype=np.int64)
        cenX = d.iX[np.array(peaks[:, 0], dtype=np.int64),
                    np.array(peaks[:, 1], dtype=np.int64),
                    np.array(peaks[:, 2], dtype=np.int64)] + 0.5
        cenY = d.iY[np.array(peaks[:, 0], dtype=np.int64),
                    np.array(peaks[:, 1], dtype=np.int64),
                    np.array(peaks[:, 2], dtype=np.int64)] + 0.5
        x = cenX - d.ipx
        y = cenY - d.ipy
        pixSize = float(d.pixel_size(evt))
        detdis = np.mean(d.coords_z(evt)) * 1e-6 # metres
        z = detdis / pixSize * np.ones(x.shape)  # pixels
        #ebeam = ebeamDet.get(evt)
        #try:
        #    photonEnergy = ebeam.ebeamPhotonEnergy()
        #except:
        photonEnergy = 1
        wavelength = 12.407002 / float(photonEnergy)  # Angstrom	
        norm = np.sqrt(x ** 2 + y ** 2 + z ** 2)
        qPeaks = (np.array([x, y, z]) / norm - np.array([[0.], [0.], [1.]])) / wavelength
        [meanClosestNeighborDist, pairsFoundPerSpot] = calculate_likelihood(qPeaks)
        return pairsFoundPerSpot
    else:
        return 0



def evaluateRun():
    """ Finds a random experiment run, finds peaks, and determines likelihood of events. If an event is
    likely to be a crystal, it will be used to train PeakNet. This function continues until the amount of 
    events found is equal to the batchSize.
   
    return the list peaks in good events,  the list of corresponding images for the good events, 
    the total number of peaks found by this function, and the total number of hits found 
    """
    # Initialize local variables
    d = 0 #Will be psana.Detector(det)
    evt = 0 #Will be run.event(this event)
    goodlist = [] # List of good peaks - their segment, row, and column
    ndalist = [] # Image of event
    totalNumPeaks = 0 #Number of peaks found during this function's call
    totalPix = 0 #Number of hits found during this function's call
    myCrawler = Crawler() # Crawler used to fetch a random experiment + run
    # Until the amount of good events found is equal to the batchSize, keep finding experiments to find peaks on
    while True:
        timebefore = time.time()
        if(len(goodlist) >= batchSize):
            break
        #Use the crawler to fetch a random experiment+run
        exp, runnum, det = myCrawler.returnOneRandomExpRunDet()
        print(exp, runnum, det)
        runnum = int(runnum)
        eventInfo = getDetectorInformation(exp, runnum, det)
        d, alg, hdr, fmt, numEvents, mask, times, env, run = eventInfo[:]
        numGoodEvents = 0
        #Peak find for each event in an experiment+run
        for j in range(numEvents):
            if(len(goodlist) >= batchSize):
                break
            #If the amount of good events found is less than minEvents before the eventLimit, then 
            #stop and try peak finding on a new experiment+run
            if((j >= eventLimit) and (numGoodEvents < 3)):
                break
            #print(j)
            eventList = [[],[],[]]
            peakInfo = getPeaks(d, alg, hdr, fmt, mask, times, env, run, j)
            evt, nda, peaks, numPeaksFound, numpix = peakInfo[:]
            if nda is None:
	        continue
            pairsFoundPerSpot = getLikelihood(d, evt, peaks, numPeaksFound)
            if (pairsFoundPerSpot > goodLikelihood):
                print hdr
                for peak in peaks:
                    totalNumPeaks += 1
                    seg,row,col,npix,amax,atot = peak[0:6]
                    eventList[0].append([seg])
                    eventList[1].append([row])
                    eventList[2].append([col])
	            print fmt % (seg, row, col, npix, atot)
                totalPix += numpix
                goodlist.append(np.array(eventList))
                ndalist.append(nda)
                numGoodEvents += 1
                print ("Event Likelihood: %f" % pairsFoundPerSpot)
        timeafter = time.time()
        print("This took " ,timeafter-timebefore, " seconds")
    return [goodlist, ndalist, totalNumPeaks, totalPix]


evaluateinfo = evaluateRun()
goodlist, ndalist, totalNumPeaks, totalPix = evaluateinfo[:]

#Master gets the number of peaks and hits found
push(totalNumPeaks)
push(totalPix)

#Train PeakNet on the good events
for i,element in enumerate(ndalist):
	psnet.train(element, goodlist[i])

#for now, send an random numpy array to the master (this will eventually be used to send the weights to the master)
a = np.array([[1, 2],[3, 4]])
b = bitwise_array(a)
push(b)

#push("Done!")
