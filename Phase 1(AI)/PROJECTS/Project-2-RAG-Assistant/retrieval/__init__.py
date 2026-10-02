"""Retrieval: everything that turns a question into candidate chunks.

Step 8 (dense) and Step 9 (sparse) each produce a RANKED LIST of chunks. Step 11
fuses those lists and reranks them. Keeping all of that in one package, behind the
shared `Retrieved` type, is what lets the pieces be combined without adapters.
"""
