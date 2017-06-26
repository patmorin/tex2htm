#!/usr/bin/python3
import os
import subprocess

if __name__ == "__main__":
    texfiles=['intro', 'arrays', 'linkedlists',  # TODO: why the infinitte loop?
              'skiplists', 'hashing',
              'binarytrees', 'rbs', 'scapegoat', 'redblack', 'heaps', 'sorting',
              'graphs', 'integers', 'btree'
              ]
    texfiles = ['ods' + os.path.sep + f + '.tex' for f in texfiles]
    texfiles.append('ods/ods.bbl')

    subprocess.call(['./tex2htm.py'] + texfiles)
