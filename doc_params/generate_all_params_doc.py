#!/usr/bin/env python3
 
import glob,os,sys


for m in ['preproc','physics','postproc']:
    
    L = glob.glob('../igm/modules/'+m+'/*.py')
    L = [l.split('/')[-1].split('.')[0] for l in L]
    L.remove('__init__')
    
    for l in L:

        print(m,l)

        with open('igm-run.py', "w") as f:

            print("import sys", file=f)
            print("sys.path.append('../')", file=f)
            print("import argparse", file=f)
            print("import igm", file=f)
            print("parser = argparse.ArgumentParser()", file=f)
            print("igm.params_"+l+"(parser)", file=f)
            print("params = parser.parse_args()", file=f)
         
        os.system("argmark -f igm-run.py")
        
        os.system('mv argmark.md '+ l + '.md')

os.system('rm igm-run.py')
