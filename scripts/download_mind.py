"""Fetch the official research dataset for local experiments; never redistribute it."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('.runtime/mind'))
    args=p.parse_args()
    print('Source and Microsoft Research license: https://msnews.github.io/')
    print('Local noncommercial learning/research use. Downloaded data is excluded from Git and releases.')
    for name,part in [('train','train'),('dev','dev')]:
        target=args.output/name;target.mkdir(parents=True,exist_ok=True)
        if (target/'news.tsv').exists() and (target/'behaviors.tsv').exists():
            print(name,'already present');continue
        archive=args.output/f'MINDsmall_{part}.zip'
        # Current upstream Recommenders downloader uses this maintained mirror.
        # https://github.com/recommenders-team/recommenders/blob/main/recommenders/datasets/mind.py
        url=f'https://huggingface.co/datasets/Recommenders/MIND/resolve/main/MINDsmall_{part}.zip'
        with urllib.request.urlopen(url,timeout=60) as response, archive.open('wb') as out:
            while chunk:=response.read(1024*1024):out.write(chunk)
        print(name,'downloaded bytes',archive.stat().st_size,'sha256',hashlib.file_digest(archive.open('rb'),'sha256').hexdigest())
        with zipfile.ZipFile(archive) as z:
            for filename in ['news.tsv','behaviors.tsv']:
                with z.open(filename) as source,(target/filename).open('wb') as out:
                    while chunk:=source.read(1024*1024):out.write(chunk)
        archive.unlink()

if __name__=='__main__':main()
