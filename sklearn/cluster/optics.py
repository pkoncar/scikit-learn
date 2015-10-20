# -*- coding: utf-8 -*-

#                                              #
# Authors:                                     #
#     Shane Grigsby <refuge@rocktalus.com      #
#     Amy X. Zhang <amy.xian.zhang@gmail.com>  #
#     Sean Freeman                             #
# Date:             May  2013                  #
# Updated:          Nov  2014                  #
# Benchmarked:      Sept 2015                  #

# Imports #

import scipy as sp
import numpy as np
from ..utils import check_array
from sklearn.neighbors import BallTree
from sklearn.base import BaseEstimator, ClusterMixin


class setOfObjects(BallTree):

    """Build balltree data structure with processing index from given data
    in preparation for OPTICS Algorithm

    Parameters
    ----------
    data_points: array [n_samples, n_features]"""

    def __init__(self, data_points, **kwargs):

        super(setOfObjects, self).__init__(data_points, **kwargs)

        self._n = len(self.data)
        # Start all points as 'unprocessed' ##
        self._processed = sp.zeros((self._n, 1), dtype=bool)
        self.reachability_ = sp.ones(self._n) * sp.inf
        self.core_dists_ = sp.ones(self._n) * sp.nan
        self._index = sp.array(range(self._n))
        self._nneighbors = sp.ones(self._n, dtype=int)
        # Start all points as noise ##
        self._cluster_id = -sp.ones(self._n, dtype=int)
        self._is_core = sp.zeros(self._n, dtype=bool)
        # Ordering is important below... ###
        self.ordering_ = []


def _prep_optics(self, epsilon, min_samples):
    """Prep data set for main OPTICS loop

    Parameters
    ----------
    epsilon: float or int
        Determines maximum object size that can be extracted.
        Smaller epsilons reduce run time
    min_samples: int
        The minimum number of samples in a neighborhood to be
        considered a core point

    Returns
    -------
    Modified setOfObjects tree structure"""

    self._nneighbors = self.query_radius(self.data, r=epsilon,
                                         count_only=True)

    # Only core distance lookups for points capable of being core
    mask_idx = self._nneighbors >= min_samples
    core_query = self.get_arrays()[0][mask_idx]
    # Check to see if that there is at least one cluster
    if len(core_query) >= 1:
        core_dist = self.query(core_query, k=min_samples)[0][:, -1]
        self.core_dists_[mask_idx] = core_dist


# Main OPTICS loop #


def _build_optics(setofobjects, epsilon):
    """Builds OPTICS ordered list of clustering structure

    Parameters
    ----------
    SetofObjects: Instantiated and prepped instance of 'setOfObjects' class
    epsilon: float or int
        Determines maximum object size that can be extracted. Smaller
        epsilons reduce run time. This should be equal to epsilon
        in 'prep_optics' """

    for point in setofobjects._index:
        if not setofobjects._processed[point]:
            _expandClusterOrder(setofobjects, point, epsilon)

# OPTICS helper functions; these should not be public #

# Not parallelizable. The order that entries are written to
# the 'ordering_' is important!


def _expandClusterOrder(setofobjects, point, epsilon):
    if setofobjects.core_dists_[point] <= epsilon:
        while not setofobjects._processed[point]:
            setofobjects._processed[point] = True
            setofobjects.ordering_.append(point)
            point = _set_reach_dist(setofobjects, point, epsilon)
    else:
        setofobjects.ordering_.append(point) # For very noisy points
        setofobjects._processed[point] = True


# As above, not parallelizable. Parallelizing would allow items in
# the 'unprocessed' list to switch to 'processed'
def _set_reach_dist(setofobjects, point_index, epsilon):

    # Assumes that the query returns ordered (smallest distance first)
    # entries. This is the case for the balltree query...

    dists, indices = setofobjects.query(setofobjects.data[point_index],
                                        setofobjects._nneighbors[point_index])

    # Checks to see if there more than one member in the neighborhood ##
    if sp.iterable(dists):

        # Masking processed values ##
        # n_pr is 'not processed'
        n_pr = indices[(setofobjects._processed[indices] < 1)[0].T]
        rdists = sp.maximum(dists[(setofobjects._processed[indices] < 1)[0].T],
                            setofobjects.core_dists_[point_index])

        new_reach = sp.minimum(setofobjects.reachability_[n_pr], rdists)
        setofobjects.reachability_[n_pr] = new_reach

        # Checks to see if everything is already processed;
        # if so, return control to main loop ##
        if n_pr.size > 0:
            # Define return order based on reachability distance ###
            return n_pr[sp.argmin(setofobjects.reachability_[n_pr])]
        else:
            return point_index

# End Algorithm #

# class OPTICS(object):


class OPTICS(BaseEstimator, ClusterMixin):

    """Estimate clustering structure from vector array

    OPTICS: Ordering Points To Identify the Clustering Structure
    Equivalent to DBSCAN, finds core sample of high density and expands
    clusters from them. Unlike DBSCAN, keeps cluster hierarchy for varying
    epsilon values. Optimized for usage on large point datasets.

    Parameters
    ----------
    eps : float, optional
    The maximum distance between two samples for them to be considered
    as in the same neighborhood. This is also the largest object size
    expected within the dataset. Lower eps values can be used after
    OPTICS is run the first time, with fast returns of labels.
    min_samples : int, optional
    The number of samples in a neighborhood for a point to be considered
    as a core point.
    metric : string or callable, optional
    The distance metric to use for neighborhood lookups. Default is
    "minkowski". Other options include “euclidean”, “manhattan”,
    “chebyshev”, “haversine”, “seuclidean”, “hamming”, “canberra”,
    and “braycurtis”. The “wminkowski” and “mahalanobis” metrics are
    also valid with an additional argument.

    Attributes
    ----------
    `core_sample_indices_` : array, shape = [n_core_samples]
        Indices of core samples.
    `labels_` : array, shape = [n_samples]
        Cluster labels for each point in the dataset given to fit().
        Noisy samples are given the label -1.
    `reachability_` : array, shape = [n_samples]
        Reachability distances per sample
    `ordering_` : array, shape = [n_samples]
        The cluster ordered list of sample indices
    `core_dists_` : array, shape = [n_samples]
        Distance at which each sample becomes a core point.
        Points which will never be core have a distance of inf.

    References
    ----------
    Ankerst, Mihael, Markus M. Breunig, Hans-Peter Kriegel, and Jörg Sander.
    "OPTICS: ordering points to identify the clustering structure." ACM SIGMOD
    Record 28, no. 2 (1999): 49-60.
    """

    def __init__(self, eps=0.5, min_samples=5, metric='minkowski', **kwargs):
        self.eps = eps
        self.min_samples = min_samples
        self.metric = metric
        self.processed = False

    def fit(self, X, y=None):
        """Perform OPTICS clustering

        Extracts an ordered list of points and reachability distances, and
        performs initial clustering using 'eps' distance specified at OPTICS
        object instantiation.

        Parameters
        ----------
        X : array [n_samples, n_features]"""

        #  Checks for sparse matrices
        X = check_array(X)

        self.tree = setOfObjects(X)  # ,self.metric)
        _prep_optics(self.tree, self.eps * 5.0, self.min_samples)
        _build_optics(self.tree, self.eps * 5.0)
        self._index = self.tree._index[:]
        self.reachability_ = self.tree.reachability_[:]
        self.core_dists_ = self.tree.core_dists_[:]
        self._cluster_id = self.tree._cluster_id[:]
        self._is_core = self.tree._is_core[:]
        self.ordering_ = self.tree.ordering_[:]
        _extractDBSCAN(self, self.eps)  # extraction needs to be < eps
        self.labels_ = self._cluster_id[:]
        self.core_sample_indices_ = self._index[self._is_core[:] == True]
        self.n_clusters = max(self._cluster_id)
        self.processed = True
        return self  # self.core_sample_indices_, self.labels_

    def extract(self, epsilon_prime, clustering='dbscan',
                significant_ratio=0.75, similarity_ratio=0.4, 
                min_reach_ratio=0.1):
        """Performs DBSCAN equivalent extraction for arbitrary epsilon.
        Can be run multiple times.

        Parameters
        ----------
        epsilon_prime: float or int, optional
        Used for 'dbscan' clustering. Must be less than or equal to what 
        was used for prep and build steps
        clustering: {'dbscan', hierarchical'}, optional
        Type of cluster extraction to perform; defaults to 'dbscan'.
        significant_ratio : float, optional
        Used for hierarchical clustering. The ratio for the reachability 
        score of a local maximum compared to its neighbors to be considered 
        significant.
        similarity_ratio : float, optional
        Used for hierarchical clustering. The ratio for the reachability 
        score of a split point compared to the parent split point for it to 
        be considered similar.
        min_reach_ratio : float, optional
        Used for hierarchical clustering. The ratio of the largest 
        reachability score that a local maximum needs to reach in order to 
        be considered.
        
        Returns
        -------
        New core_sample_indices_ and labels_ arrays. Modifies OPTICS object
        and stores core_sample_indices_ and lables_ as attributes."""

        if self.processed is True:
            if epsilon_prime > self.eps * 5.0:
                print('Specify an epsilon smaller than ' + str(self.eps * 5))
            else:
                if clustering == 'dbscan':
                    self.eps_prime = epsilon_prime
                    _extractDBSCAN(self, epsilon_prime)
                elif clustering == 'hierarchical':
                    _hierarchical_extraction(self, significant_ratio, 
                                             similarity_ratio, 
                                             min_reach_ratio)   
                self.labels_ = self._cluster_id[:]
                # Setting following line to '1' instead of 'True' to keep
                # line shorter than 79 characters
                self.core_sample_indices_ = self._index[self._is_core[:] == 1]
                self.n_clusters = max(self._cluster_id)
                if epsilon_prime > (self.eps * 1.05):
                    print("Warning, eps is close to epsilon_prime:")
                    print("Output may be unstable")
                return self.core_sample_indices_, self.labels_
        else:
            print("Run fit method first")

# Extract DBSCAN Equivalent cluster structure ##

# Important: Epsilon prime should be less than epsilon used in OPTICS #


def _extractDBSCAN(setofobjects, epsilon_prime):

    # Start Cluster_id at zero, incremented to '1' for first cluster
    cluster_id = 0
    for entry in setofobjects.ordering_:
        if setofobjects.reachability_[entry] > epsilon_prime:
            if setofobjects.core_dists_[entry] <= epsilon_prime:
                cluster_id += 1
                setofobjects._cluster_id[entry] = cluster_id
            else:
                # This is only needed for compatibility for repeated scans.
                # -1 is Noise points
                setofobjects._cluster_id[entry] = -1
                setofobjects._is_core[entry] = 0
        else:
            setofobjects._cluster_id[entry] = cluster_id
            if setofobjects.core_dists_[entry] <= epsilon_prime:
                # One (i.e., 'True') for core points #
                setofobjects._is_core[entry] = 1
            else:
                # Zero (i.e., 'False') for non-core, non-noise points #
                setofobjects._is_core[entry] = 0

# Automatic clustering
# Author:     Amy X. Zhang, 2012
# Modified:   Shane Grigsby, 2015

def isLocalMaxima(index,RPlot,RPoints,nghsize):
    # 0 = point at index is not local maxima
    # 1 = point at index is local maxima
    
    for i in range(1,nghsize+1):
        #process objects to the right of index 
        if index + i < len(RPlot):
            if (RPlot[index] < RPlot[index+i]):
                return 0
            
        #process objects to the left of index 
        if index - i >= 0:
            if (RPlot[index] < RPlot[index-i]):
                return 0
    
    return 1

def findLocalMaxima(RPlot, RPoints, nghsize):
    
    localMaximaPoints = {}
    
    # 1st and last points on Reachability Plot are not taken 
    # as local maxima points
    for i in range(1,len(RPoints)-1):
        # if the point is a local maxima on the reachability plot with 
        # regard to nghsize, insert it into priority queue and maxima list
        if (RPlot[i] > RPlot[i-1] and RPlot[i] >= RPlot[i+1] and 
            isLocalMaxima(i,RPlot,RPoints,nghsize) == 1):

            localMaximaPoints[i] = RPlot[i]
    
    return sorted(localMaximaPoints, 
                  key=localMaximaPoints.__getitem__ , reverse=True)
    
def clusterTree(node, parentNode, localMaximaPoints, 
                RPlot, RPoints, min_cluster_size):
    # node is a node or the root of the tree in the first call
    # parentNode is parent node of N or None if node is root of the tree
    # localMaximaPoints is list of local maxima points sorted in 
    # descending order of reachability
    if len(localMaximaPoints) == 0:
        return #parentNode is a leaf
    
    # take largest local maximum as possible separation between clusters
    s = localMaximaPoints[0]
    node.assignSplitPoint(s)
    localMaximaPoints = localMaximaPoints[1:]

    # create two new nodes and add to list of nodes
    Node1 = TreeNode(RPoints[node.start:s],node.start,s, node)
    Node2 = TreeNode(RPoints[s+1:node.end],s+1, node.end, node)
    LocalMax1 = []
    LocalMax2 = []

    for i in localMaximaPoints:
        if i < s:
            LocalMax1.append(i)
        if i > s:
            LocalMax2.append(i)
    
    Nodelist = []
    Nodelist.append((Node1,LocalMax1))
    Nodelist.append((Node2,LocalMax2))
    
    # set a lower threshold on how small a significant maxima can be
    significantMin = .003

    if RPlot[s] < significantMin:
        node.assignSplitPoint(-1)
        #if splitpoint is not significant, ignore this split and continue
        clusterTree(node,parentNode, localMaximaPoints, 
                    RPlot, RPoints, min_cluster_size)
        return
        
        
    # only check a certain ratio of points in the child 
    # nodes formed to the left and right of the maxima
    checkRatio = .8
    checkValue1 = int(NP.round(checkRatio*len(Node1.points)))
    checkValue2 = int(NP.round(checkRatio*len(Node2.points)))
    if checkValue2 == 0:
        checkValue2 = 1
    avgReachValue1 = float(NP.average(RPlot[(Node1.end - 
                                             checkValue1):Node1.end]))
    avgReachValue2 = float(NP.average(RPlot[Node2.start:(Node2.start + 
                                                         checkValue2)]))


    '''
    To adjust the fineness of the clustering, adjust the following ratios.
    The higher the ratio, the more generous the algorithm is to preserving
    local minimums, and the more cuts the resulting tree will have.
    '''

    # the maximum ratio we allow of average height of clusters 
    # on the right and left to the local maxima in question
    maximaRatio = .75
    
    # if ratio above exceeds maximaRatio, find which of the clusters 
    # to the left and right to reject based on rejectionRatio
    rejectionRatio = .7
    
    if (float(avgReachValue1 / float(RPlot[s])) > 
        maximaRatio or float(avgReachValue2 / 
                             float(RPlot[s])) > maximaRatio):

        if float(avgReachValue1 / float(RPlot[s])) < rejectionRatio:
          #reject node 2
            Nodelist.remove((Node2, LocalMax2))
        if float(avgReachValue2 / float(RPlot[s])) < rejectionRatio:
          #reject node 1
            Nodelist.remove((Node1, LocalMax1))
        if (float(avgReachValue1 / float(RPlot[s])) >= 
            rejectionRatio and float(avgReachValue2 / 
                                     float(RPlot[s])) >= rejectionRatio):
            node.assignSplitPoint(-1)
            # since splitpoint is not significant, 
            # ignore this split and continue (reject both child nodes)
            clusterTree(node, parentNode, localMaximaPoints, 
                        RPlot, RPoints, min_cluster_size)
            return
 
    # remove clusters that are too small
    if len(Node1.points) < min_cluster_size:
        # cluster 1 is too small"
        try:
            Nodelist.remove((Node1, LocalMax1))
        except Exception:
            sys.exc_clear()
    if len(Node2.points) < min_cluster_size:
        # cluster 2 is too small
        try:
            Nodelist.remove((Node2, LocalMax2))
        except Exception:
            sys.exc_clear()
    if len(Nodelist) == 0:
        # parentNode will be a leaf
        node.assignSplitPoint(-1)
        return
    
    '''
    Check if nodes can be moved up one level - the new cluster created
    is too "similar" to its parent, given the similarity threshold.
    Similarity can be determined by 1)the size of the new cluster relative
    to the size of the parent node or 2)the average of the reachability
    values of the new cluster relative to the average of the
    reachability values of the parent node
    A lower value for the similarity threshold means less levels in the tree.
    '''
    similaritythreshold = 0.4
    bypassNode = 0
    if parentNode != None:
        sumRP = NP.average(RPlot[node.start:node.end])
        sumParent = NP.average(RPlot[parentNode.start:parentNode.end])
        if (float(float(node.end-node.start) / 
                  float(parentNode.end-parentNode.start)) > 
             similaritythreshold): #1)
        #if float(float(sumRP) / float(sumParent)) > similaritythreshold: #2)
            parentNode.children.remove(node)
            bypassNode = 1
        
    for nl in Nodelist:
        if bypassNode == 1:
            parentNode.addChild(nl[0])
            clusterTree(nl[0], parentNode, nl[1], RPlot, RPoints, 
                        min_cluster_size)
        else:
            node.addChild(nl[0])
            clusterTree(nl[0], node, nl[1], RPlot, RPoints, min_cluster_size)
        

def printTree(node, num):
    if node is not None:
        print "Level %d" % num
        print str(node)
        for n in node.children:
            printTree(n, num+1)

def writeTree(fileW, locationMap, RPoints, node, num):
    if node is not None:
        fileW.write("Level " + str(num) + "\n")
        fileW.write(str(node) + "\n")
        for x in range(node.start,node.end):
            item = RPoints[x]
            lon = item[0]
            lat = item[1]
            placeName = locationMap[(lon,lat)]
            s = (str(x) + ',' + placeName + ', ' + 
                 str(lat) + ', ' + str(lon) + '\n')
            fileW.write(s)
        fileW.write("\n")
        for n in node.children:
            writeTree(fileW, locationMap, RPoints, n, num+1)


def getArray(node,num, arr):
    if node is not None:
        if len(arr) <= num:
            arr.append([])
        try:
            arr[num].append(node)
        except:
            arr[num] = []
            arr[num].append(node)
        for n in node.children:
            getArray(n,num+1,arr)
        return arr
    else:
        return arr


def getLeaves(node, arr):
    if node is not None:
        if node.splitpoint == -1:
            arr.append(node)
        for n in node.children:
            getLeaves(n,arr)
    return arr


def graphTree(root, RPlot):

    fig = plt.figure()
    ax = fig.add_subplot(111)

    a1 = [i for i in range(len(RPlot))]
    ax.vlines(a1, 0, RPlot)
    
    num = 2
    graphNode(root, num, ax)

    plt.savefig('RPlot.png', dpi=None, facecolor='w', edgecolor='w',
      orientation='portrait', papertype=None, format=None,
     transparent=False, bbox_inches=None, pad_inches=0.1)
    plt.show()

            
def graphNode(node, num, ax):
    ax.hlines(num,node.start,node.end,color="red")
    for item in node.children:
        graphNode(item, num - .4, ax)

def automaticCluster(RPlot, RPoints):

    min_cluster_size_ratio = .005
    min_neighborhood_size = 2
    min_maxima_ratio = 0.001
    
    min_cluster_size = int(min_cluster_size_ratio * len(RPoints))

    if min_cluster_size < 5:
        min_cluster_size = 5
    
    
    nghsize = int(min_maxima_ratio*len(RPoints))

    if nghsize < min_neighborhood_size:
        nghsize = min_neighborhood_size
    
    localMaximaPoints = findLocalMaxima(RPlot, RPoints, nghsize)
    
    rootNode = TreeNode(RPoints, 0, len(RPoints), None)
    clusterTree(rootNode, None, localMaximaPoints, 
                RPlot, RPoints, min_cluster_size)


    return rootNode
    

class TreeNode(object):
    def __init__(self, points, start, end, parentNode):
        self.points = points
        self.start = start
        self.end = end
        self.parentNode = parentNode
        self.children = []
        self.splitpoint = -1

    def __str__(self):
        return "start: %d, end %d, split: %d" % (self.start, 
                                                 self.end, 
                                                 self.splitpoint)

        
    def assignSplitPoint(self,splitpoint):
        self.splitpoint = splitpoint

    def addChild(self, child):
        self.children.append(child)
