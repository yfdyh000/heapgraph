#!/usr/bin/python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Library for parsing garbage collector log files into a graph data structure.


# This documentation hasn't been updated.

# parseCCEdgeFile (file_name): given the file name of a CC edge file, parse and 
#   return the data.  This function returns a tuple with two components.
#
#   The first component is a multigraph representing the nodes and
#   edges in the graph.  It is implemented as a dictionary of
#   dictionaries.  The domain of the outer dictionary is the nodes of
#   the graphs.  The inner dictionaries map the destinations of the
#   edges in the graph to the number of times they occur.  For
#   instance, if there are two edges from x to y in the multigraph g,
#   then g[x][y] == 2.
#
#   The second component contains various graph attributes in a GraphAttribs
#      - nodeLabels maps node names to their labels, if any
#      - rcNodes maps ref counted nodes to the number of references
#        they have
#      - gcNodes maps gc'd nodes to a boolean, which is True if the
#        node is marked, False otherwise.
#      - edgeLabels maps source nodes to dictionaries.  These inner
#        dictionaries map destination nodes to a list of edge labels.


# toSinglegraph (gm): convert a multigraph into a single graph

# reverseMultigraph (gm): reverse a multigraph

# printGraph(g): print out a graph

# pringAttribs(ga): print out graph attributes


import sys
import re
from collections import namedtuple



GraphAttribs = namedtuple('GraphAttribs', 'edgeLabels nodeLabels roots rootLabels compartments')


####
####  Log parsing
####

nodePatt = re.compile ('(0x[a-fA-F0-9]+) (0x[a-fA-F0-9]+) (.*)$')
rootPatt = re.compile ('(0x[a-fA-F0-9]+) (.*)$')
edgePatt = re.compile ('> (0x[a-fA-F0-9]+) (.*)$')


# just skip over these for now
def parseCompartments(f):
  for l in f:
    if l == "==========\n":
      return


# A bit of a hack.  I imagine this could fail in bizarre circumstances.

def switchToGreyRoots(l):
  return l == "XPC global object" or l.startswith("XPCWrappedNative") or \
      l.startswith("XPCVariant") or l.startswith("nsXPCWrappedJS")

def parseRoots (f):
  roots = {}
  rootLabels = {}
  blackRoot = True;

  for l in f:
    nm = rootPatt.match(l)
    if nm:
      addr = nm.group(1)
      lbl = nm.group(2)

      if blackRoot and switchToGreyRoots(lbl):
        blackRoot = False
      roots[addr] = blackRoot
      rootLabels[addr] = lbl

    elif l == "==========\n":
      break;
    else:
      print("Error: unknown line ", l)
      exit(-1)

  return [roots, rootLabels]


# parse CC graph
def parseGraph (f):
  edges = {}
  edgeLabels = {}
  nodeLabels = {}
  rcNodes = {}
  gcNodes = {}
  compartments = {}

  def addNode (node, comp, nodeLabel):
    assert(not node in edges)
    edges[node] = {}
    assert(not node in edgeLabels)
    edgeLabels[node] = {}
    assert(nodeLabel != None)
    compartments[node] = comp
    if nodeLabel != '':
      assert (not node in nodeLabels)
      nodeLabels[node] = nodeLabel

  def addEdge (source, target, edgeLabel):
    edges[source][target] = edges[source].get(target, 0) + 1
    if edgeLabel != '':
      edgeLabels[source].setdefault(target, []).append(edgeLabel)

  currNode = None

  for l in f:
    e = edgePatt.match(l)
    if e:
      assert(currNode != None)
      addEdge(currNode, e.group(1), e.group(2))
    else:
      nm = nodePatt.match(l)
      if nm:
        currNode = nm.group(1)
        addNode(currNode, nm.group(2), nm.group(3))
      else:
        print('Error: Unknown line:', l[:-1])

  # yar, should pass the root crud in and wedge it in here, or somewhere
  return [edges, edgeLabels, nodeLabels, compartments]


def parseGCEdgeFile (fname):
  try:
    f = open(fname, 'r')
  except:
    print('Error opening file', fname)
    exit(-1)

  parseCompartments(f)
  [roots, rootLabels] = parseRoots(f)
  [edges, edgeLabels, nodeLabels, compartments] = parseGraph(f)
  f.close()

  ga = GraphAttribs (edgeLabels=edgeLabels, nodeLabels=nodeLabels, roots=roots, rootLabels=rootLabels, compartments=compartments)
  return (edges, ga)


# Some applications may not care about multiple edges.
# They can instead use a single graph, which is represented as a map
# from a source node to a set of its destinations.
def toSinglegraph (gm):
  g = {}
  for src, dsts in gm.items():
    d = set([])
    for dst, k in dsts.items():
      d.add(dst)
    g[src] = d
  return g


def reverseMultigraph (gm):
  gm2 = {}
  for src, dsts in gm.items():
    if not src in gm2:
      gm2[src] = {}
    for dst, k in dsts.items():
      gm2.setdefault(dst, {})[src] = k
  return gm2


def printGraph(g, ga):
  for x, edges in g.items():
    if x in ga.roots:
      sys.stdout.write('R {0}: '.format(x))
    else:
      sys.stdout.write('  {0}: '.format(x))
    for e, k in edges.items():
      for n in range(k):
        sys.stdout.write('{0}, '.format(e))
    print()

def printAttribs(ga):
  print('Roots: ', end=' ')
  for x in ga.roots:
    sys.stdout.write('{0}, '.format(x))
  print()
  return;

  print('Node labels: ', end=' ')
  for x, l in ga.nodeLabels.items():
    sys.stdout.write('{0}:{1}, '.format(x, l))
  print()

  print('Edge labels: ', end=' ')
  for src, edges in ga.edgeLabels.items():
    for dst, l in edges.items():
      sys.stdout.write('{0}->{1}:{2}, '.format(src, dst, l))
  print()


if False:
  # A few simple tests

  if len(sys.argv) < 2:
    print('Not enough arguments.')
    exit()

  #import cProfile
  #cProfile.run('x = parseGCEdgeFile(sys.argv[1])')

  x = parseGCEdgeFile(sys.argv[1])

  #printGraph(x[0], x[1])
  printAttribs(x[1])

  assert (x[0] == reverseMultigraph(reverseMultigraph(x[0])))
