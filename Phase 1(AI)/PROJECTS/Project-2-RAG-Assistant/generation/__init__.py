"""Generation: turning retrieved chunks into an answer.

Step 13 is the only place a model *writes prose*. Everything before it either
stored data or found the right chunks. This package assembles those chunks into a
prompt and asks the model to answer strictly from them.
"""
