#!/usr/bin/python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import re
from collections import namedtuple
import parse_gc_graph
import argparse



# (this comment is out of date)


# Find the objects that are rooting a particular object (or objects of
# a certain class) in the cycle collector graph
#
# This works by reversing the graph, then flooding to find roots.
#
# There are various options to alter what is treated as a root, but
# these are mostly experimental, so they may not produce particularly
# useful results.
#
# --node-name-as-root nsRange (for example) will treat all objects
# with the node name nsRange as roots.  This is useful if a previous
# analysis has determined that a leak always involves an object being
# held onto by a certain class, and you want to continue with manual
# analysis starting at that object.



# Command line arguments

parser = argparse.ArgumentParser(description='Find a rooting object in the garbage collector graph.')

parser.add_argument('file_name',
                    help='cycle collector graph file name')

parser.add_argument('target',
                    help='address of target object or prefix of class name of targets')

parser.add_argument('--simple-path', '-sp', dest='simple_path', action='store_true',
                    default=False,
                    help='Print paths on a single line and remove addresses to help large-scale analysis of paths.')

parser.add_argument('--dot-mode', '-d', dest='dot_mode', action='store_true',
                    default=False,
                    help='Experimental dot mode.  Outputs to graph.dot.')
# Convert dot file to a PDF with 'sfdp -Gsize=67! -Goverlap=prism -Tpdf -O graph.dot'


args = parser.parse_args()


# If this is True, only trace from black roots. Otherwise, also trace from gray roots.
blackRootsOnly = False

# If this is non-None, use all strings containing this string as the target.
#stringTarget = 'https://marketplace.firefox.com/app/7eccfd71-2765-458d-983f-078580b46a11/manifest.webapp'
stringTarget = None


# print a node description
def print_node (ga, x):
  sys.stdout.write ('{0} [{1}]'.format(x, ga.nodeLabels[x]))

# print an edge description
def print_edge (ga, x, y):
  def print_edge_label (l):
    if len(l) == 2:
      l = l[0]
    sys.stdout.write(l)

  sys.stdout.write('--')
  lbls = ga.edgeLabels.get(x, {}).get(y, [])
  if len(lbls) != 0:
    sys.stdout.write('[')
    print_edge_label(lbls[0])
    for l in lbls[1:]:
      sys.stdout.write(', ')
      print_edge_label(l)
    sys.stdout.write(']')

  sys.stdout.write('->')


def explain_root (ga, root):
  print "via", ga.rootLabels[root], ":"

# print out the path to an object that has been discovered
def print_path (revg, ga, roots, x, path):
  if path == []:
    explain_root(ga, x)
  else:
    explain_root(ga, path[0][0])

  for p in path:
    print_node(ga, p[0])
    sys.stdout.write('\n    ')
    print_edge(ga, p[0], p[1])
    sys.stdout.write(' ')
  print_node(ga, x)
  print
  print


def print_simple_node (ga, x):
  sys.stdout.write ('[{0}]'.format(ga.nodeLabels[x]))

def simple_explain_root (ga, root):
  # This won't work on Windows.
  l = re.sub(r'0x[0-9a-f]{8}', '*', ga.rootLabels[root])
  #l = addrPatt.sub("ADDR", ga.rootLabels[root])
  #l = ga.rootLabels[root]
  print "via", l, ":",

# produce a simplified version of the path, with the intent of
# eliminating differences that are uninteresting with a large set of
# paths.
def print_simple_path (revg, ga, roots, x, path):
  if path == []:
    simple_explain_root(ga, x)
  else:
    simple_explain_root(ga, path[0][0])

  for p in path:
    print_simple_node(ga, p[0])
    sys.stdout.write(', ')
    print_edge(ga, p[0], p[1])
    sys.stdout.write(' ')
  print_simple_node(ga, x)
  print


def add_dot_mode_path(revg, ga, roots, x, path):
  if path == []:
    newPath = [x]
  else:
    newPath = [path[0][0]]

  for p in path:
    newPath.append(p[1])

  gPaths.append(newPath)


# look for roots and print out the paths to the given object
def findRoots (revg, ga, roots, x):
  visited = set([])
  path = []
  anyFound = [False]

  def findRootsDFS (y):
    if y in visited:
      return False
    visited.add(y)
    if y in roots and (not blackRootsOnly or roots[y]): # roots[y] is true for black roots
      path.reverse()
      if args.simple_path:
        print_simple_path(revg, ga, roots, x, path)
      elif args.dot_mode:
        add_dot_mode_path(revg, ga, roots, x, path)
      else:
        print_path(revg, ga, roots, x, path)
      path.reverse()
      anyFound[0] = True

    # Whether or not y is a root, we want to find other paths to y.
    if not y in revg:
      return False
    path.append(None)
    for z in revg[y]:
      path[-1] = (z, y)
      if findRootsDFS(z):
        return True
    path.pop()
    return False

  if not x in revg:
    sys.stdout.write ('No other nodes point to {0}.\n\n'.format(x))
    return

  findRootsDFS(x)

  if not anyFound[0]:
    print 'No roots found.'


def reverseGraph (g):
  g2 = {}
  print 'Reversing graph.',
  sys.stdout.flush()
  for src, dsts in g.iteritems():
    for d in dsts:
      g2.setdefault(d, set([])).add(src)
  print 'Done.'
  print
  return g2


def loadGraph(fname):
  sys.stdout.write ('Parsing {0}. '.format(fname))
  sys.stdout.flush()
  (g, ga) = parse_gc_graph.parseGCEdgeFile(fname)
  #sys.stdout.write ('Converting to single graph. ')
  #sys.stdout.flush()
  g = parse_gc_graph.toSinglegraph(g)
  print 'Done loading graph.',

  return (g, ga)


def stringTargets(ga, stringTarget):
  targs = []

  for addr, lbl in ga.nodeLabels.iteritems():
    if not lbl.startswith('string '):
      continue
    s = lbl[7:]
    if stringTarget == s:
    #if stringTarget in s:
      targs.append(addr)

  return targs


def selectTargets (g, ga, target):
  if stringTarget:
    targs = stringTargets(ga, stringTarget)
  elif addrPatt.match(target):
    targs = [target]
  else:
    # look for objects with a class name prefixes, not a particular object
    targs = []
    for x in g.keys():
      if ga.nodeLabels.get(x, '')[0:len(target)] == target:
        targs.append(x)
    if targs == []:
      print 'No matching class names found.'

  return targs



#######
# union find with path compression and union by rank

def findi (m, x):
  if not x in m:
    m[x] = [x, 0]
    return m[x]
  if m[x][0] == x:
    return m[x]
  z = findi (m, m[x][0])
  m[x] = z
  return z

def find (m, x):
  return findi(m, x)[0]

def union (m, rep, x, y):
  xp = findi (m, x)
  yp = findi (m, y)
  if xp == yp:
    return
  if xp[1] < yp[1]:
    rep[yp[0]] = rep.get(xp[0], xp[0])
    if xp[0] in rep:
      del rep[xp[0]]
    m[xp[0]][0] = yp[0]
  elif xp[1] > yp[1]:
    m[yp[0]][0] = xp[0]
  else:
    m[yp[0]][0] = xp[0]
    m[xp[0]][1] += 1


#######
# dotify support

gPaths = []


def finishDotMode(ga):

  # build the set of nodes
  nodes = set([])
  for p in gPaths:
    for x in p:
      nodes.add(x)

  # build the edge map
  edges = {}

  for p in gPaths:
    prevNode = None
    for x in p:
      if prevNode:
        edges.setdefault(prevNode, set([])).add(x)
      prevNode = x

  # compress shapes
  shape_merge = {}
  shape_rep = {}

  for x in nodes:
    if ga.nodeLabels.get(x, '') != 'shape':
      continue
    if not x in edges:
      continue
    for y in edges[x]:
      if ga.nodeLabels.get(y, '') != 'shape' and ga.nodeLabels.get(y, '') != 'base_shape':
        continue
      union(shape_merge, shape_rep, y, x)
      break

  def canon_node(x):
    y = find(shape_merge, x)
    if y in shape_rep:
      y = shape_rep[y]
    return y

  # Remove merged away nodes
  for x in shape_merge.keys():
    if canon_node(x) != x:
      nodes.remove(x)

  # Update the edges for merging
  new_edges = {}
  for x, dsts in edges.iteritems():
    new_dsts = set([])
    for y in dsts:
      new_dsts.add(canon_node(y))
    x = canon_node(x)
    if x in new_dsts:
      new_dsts.remove(x)
    new_edges[x] = new_edges.get(x, set([])).union(new_dsts)
  edges = new_edges


  # output the dot file

  outf = open('graph.dot', 'w')
  outf.write('digraph {\n')

  for n in nodes:
    lbl = ga.nodeLabels.get(n, '')
    if lbl.startswith('Object'):
      lbl = lbl[6:]
      shape = 'square'
      color = 'black'
    elif lbl.startswith('Function'):
      lbl = lbl[9:]
      shape = 'ellipse'
      color = 'black'
    elif lbl.startswith('HTML'):
      lbl = lbl[4:]
      shape = 'diamond'
      color = 'blue'
    elif lbl.startswith('XPCWrappedNative'):
      lbl = 'XPCWN' + lbl[16:]
      shape = 'diamond'
      color = 'black'
    elif lbl.startswith('script'):
      if lbl.startswith('script app://system.gaiamobile.org/'):
        lbl = lbl[35:]
      else:
        lbl = lbl[7:]
      shape = 'ellipse'
      color = 'red'
    else:
      shape = 'circle'
      color = 'black'
    if lbl.endswith('<no private>'):
      lbl = lbl[:-13]
    outf.write('  node [color = {3}, shape = {2}, label="{1}"] q{0};\n'.format(n, lbl[:15], shape, color))

  for x, dsts in edges.iteritems():
    for y in dsts:
      outf.write('  q{0} -> q{1};\n'.format(x, y))

  outf.write('}\n')
  outf.close()


####################

addrPatt = re.compile ('(?:0x)?[a-fA-F0-9]+')


(g, ga) = loadGraph (args.file_name)
roots = ga.roots
revg = reverseGraph(g)


targs = selectTargets(g, ga, args.target)

for a in targs:
  if a in g:
    findRoots(revg, ga, roots, a)
  else:
    sys.stdout.write('{0} is not in the graph.\n'.format(a))

if args.dot_mode:
  finishDotMode(ga)
