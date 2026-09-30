"""Ingestion pipeline for the eight-thousander corpus.

Each module here does one stage: fetch (this step), parse, chunk, embed, store.
They are separate files on purpose so a stage can be tested or swapped without
touching the others.
"""
