#! /usr/bin/env python
import argparse
import sys
import codecs
from itertools import izip
from collections import defaultdict as dd
import re
import os.path
import numpy as np
from numpy import linalg as LA
from scipy.spatial.distance import cosine
from scipy.spatial import cKDTree as kdt
from sklearn.preprocessing import normalize
import cPickle


scriptdir = os.path.dirname(os.path.abspath(__file__))

def main():
  parser = argparse.ArgumentParser(description="Evaluate the 1 matrix no interlingus embedding experiment",
                                   formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--sourcedictionary", "-S", type=argparse.FileType('r'),  help="source vocabulary dictionary of the form lang word vec; headed by row col")
  parser.add_argument("--targetdictionary", "-T", type=argparse.FileType('r'),  help="target vocabulary dictionary of the form lang word vec; headed by row col")
  parser.add_argument("--infile", "-i", type=argparse.FileType('r'), default=sys.stdin, help="evaluation instruction of the form word1 lang1 lang2 [word2]. If word2 is absent it is only predicted, not evaluated")
  parser.add_argument("--modelfile", "-m", nargs='?', type=argparse.FileType('r'), default=sys.stdin, help="all models input file")
  parser.add_argument("--outfile", "-o", nargs='?', type=argparse.FileType('w'), default=sys.stdout, help="results file of the form word1 lang1 lang2 word2 [pos wordlist], where the first three fields are identical to eval and the last field is the 1-best prediction. If truth is known, ordinal position of correct answer (-1 if not found) followed by the n-best list in order")
  parser.add_argument("--nbest", "-n", type=int, default=10, help="nbest neighbors generated for purposes of evaluation")
  parser.add_argument("--pickle", "-p", action='store_true', default=False, help="dictionaries are pickled with pickle_vocab")

  try:
    args = parser.parse_args()
  except IOError, msg:
    parser.error(str(msg))


  reader = codecs.getreader('utf8')
  writer = codecs.getwriter('utf8')
  infile = reader(args.infile)
  outfile = writer(args.outfile)
  sourcedictionary = cPickle.load(args.sourcedictionary) if args.pickle else reader(args.sourcedictionary)
  targetdictionary = cPickle.load(args.targetdictionary) if args.pickle else reader(args.targetdictionary)

  dims = {}
  if args.pickle:
    sourcelang = sourcedictionary['lang']
    dims[sourcelang]=int(sourcedictionary['dim'])
    targetlang = targetdictionary['lang']
    dims[targetlang]=int(targetdictionary['dim'])
  else:
    sourceinfo = sourcedictionary.readline().strip().split()
    targetinfo = targetdictionary.readline().strip().split()
    sourcelang=sourceinfo[2]
    targetlang=targetinfo[2]
    dims[sourcelang] = int(sourceinfo[1])
    dims[targetlang] = int(targetinfo[1])
  dicts_by_lang = {}
  dicts_by_lang[sourcelang]=sourcedictionary
  dicts_by_lang[targetlang]=targetdictionary
  sourcedim = dims[sourcelang]
  targetdim = dims[targetlang]
  print sourcedim,targetdim


  mat = np.matrix(np.load(args.modelfile)['arr_0'])
  print mat.shape

  vocab = dd(lambda: dict())
  if args.pickle:
    print "Unpickling"
    targets = dicts_by_lang[targetlang]['targets']
    targetvoc = dicts_by_lang[targetlang]['targetvoc']
    for lang in (sourcelang, targetlang):
      vocab[lang] = dicts_by_lang[lang]['vocab']
  else:
    print "Loading vocab from text files"
    targets = []
    targetvoc = []

    # load transformation matrices
    # TODO: would be cool if this could exist on-disk in some binary format so only the instructions need be passed in
    # Kludgy: store source and target in different structures

    for lang in (sourcelang, targetlang):
      istarget = lang == targetlang
      fdim = dims[lang]
      dfile = dicts_by_lang[lang]
      try:
        for ln, line in enumerate(dfile):
          entry = line.strip().split(' ')
          if len(entry) < fdim+1:
            sys.stderr.write("skipping line %d in %s because it only has %d fields; first field is %s\n" % (ln, dfile.name, len(entry), entry[0]))
            continue
          word = ' '.join(entry[:-fdim])
          vec = np.array(entry[-fdim:]).astype(float)
          vocab[lang][word]=vec
          if istarget:
            targets.append(vec)
            targetvoc.append(word)

      except:
        print dfile.name
        print line
        print len(entry)
        print word
        print ln
        raise
  targets = kdt(normalize(np.array(targets), axis=1, norm='l2'))
  print "loaded vocabularies"

  for line in infile:
    inst = line.strip().split()
    inword = inst[0]
    inlang = inst[1]
    outlang = inst[2]
    outword = inst[3] if len(inst) > 3 else None
    if inword not in vocab[inlang]:
#      sys.stderr.write("Warning: Couldn't find %s -> %s\n" % (inlang, inword))
      continue
    invec = np.matrix(vocab[inlang][inword])
    xform = np.asarray(invec*mat)[0]
    neighbors = []
    cosines, cands = targets.query(xform, args.nbest)
    for cos, cand in zip(cosines, cands):
      neighbors.append((cos, targetvoc[cand]))

    report = inst[:3]
    nb_words = [x[1] for x in neighbors]
    xbest=str(cosine(xform, vocab[outlang][nb_words[0]]))
    if outword is not None:
      report.append(inst[3])
      #cosines: xform to truth, xform to 1best, truth to 1best
      truth=vocab[outlang][outword]
      xtruth=str(cosine(xform, truth))
      truthbest=str(cosine(truth, vocab[outlang][nb_words[0]]))
      rank = nb_words.index(outword) if outword in nb_words else -1
      report.append(str(rank))
      report.extend([xtruth, xbest, truthbest])
    else:
      report.append(xbest)
    report.extend(nb_words)
    outfile.write('\t'.join(report)+"\n")
  # TODO: some overall stats to stderr?

if __name__ == '__main__':
  main()

