import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import clients.cms_client as cms_client

cfg  = config.load()
docs = cms_client.fetch_cms_documents(cfg)

if not docs:
    print("No documents found.")
else:
    for d in docs:
        print("-" * 60)
        print(d["subject"])
        print(d["body"][:300])