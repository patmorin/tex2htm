#!/usr/bin/python3
import os
import subprocess

if __name__ == "__main__":
    texfiles=['intro', 'arrays', 'linkedlists',  # TODO: why the infinitte loop?
              'skiplists', 'hashing',
              'binarytrees', 'rbs', 'scapegoat', 'redblack', 'heaps', 'sorting',
              'graphs', 'integers', 'btree'
              ]
    texfiles = [f+'.tex' for f in texfiles]
    texfiles.append('ods-java.bbl')
    basedir = '/home/morin/remote/public_html/ods/newhtml/ods/latex2'
    texfiles = [basedir + os.path.sep + f for f in texfiles]

    subprocess.call(['./tex2htm.py'] + texfiles)
