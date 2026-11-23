"""Shared deterministic benchmark helpers."""
from __future__ import annotations
import csv, os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'docs'/'benchmarks'; OUT.mkdir(parents=True,exist_ok=True)
load_dotenv(ROOT/'.env')
SEED=104729
def client(): return MongoClient(os.environ['MONGODB_URI'],serverSelectionTimeoutMS=15000)
def csv_write(name,rows):
    rows=list(rows); path=OUT/name
    if rows:
        with path.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return path
