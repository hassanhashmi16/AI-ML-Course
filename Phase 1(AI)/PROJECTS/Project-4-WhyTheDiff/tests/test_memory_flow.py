from contextlib import closing
from datetime import datetime, timezone
from types import SimpleNamespace
from langchain_core.embeddings import Embeddings
from agent.memory import opening_messages, save_findings
from config import settings
from models import Claim, ClaimLabel, Coverage, Report, ReportStatus, RepoSnapshot, SourceKind, SourceRecord, SupportingExcerpt
from retrieval.clients import open_qdrant
from runtime import user_workspace

class TinyEmbeddings(Embeddings):
    def embed_documents(self, texts): return [[1.0, 0.0, 0.0] for _ in texts]
    def embed_query(self, text): return [1.0, 0.0, 0.0]

def test_later_investigations_recall_findings_only_in_their_account(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    snapshot = RepoSnapshot(repository='https://github.com/a/b', sha='a'*40, commit_date=datetime.now(timezone.utc))
    record = SourceRecord(source_id='s1', kind=SourceKind.FILE, repository=snapshot.repository, snapshot_sha=snapshot.sha, content='Use a cache to avoid repeated parsing.', content_revision='r1', url='https://github.com/a/b/blob/main/a.py')
    claim = Claim(statement='The cache avoids repeated parsing.', label=ClaimLabel.DOCUMENTED, excerpts=[SupportingExcerpt(source_id='s1', quote=record.content)])
    report = Report(question='Why cache?', snapshot=snapshot, status=ReportStatus.COMPLETE, summary=claim.statement, claims=[claim], coverage=Coverage(repository=snapshot.repository, snapshot_sha=snapshot.sha))
    embeddings = TinyEmbeddings()
    with user_workspace('1'):
        with closing(open_qdrant()) as client:
            save_findings(client, embeddings, report, {'s1':record})
    for owner, expected in [('2', False), ('1', True)]:
        with user_workspace(owner):
            with closing(open_qdrant()) as client:
                context = SimpleNamespace(client=client, embeddings=embeddings, snapshot=snapshot, collector=SimpleNamespace(sources={'s1':record}))
                messages = opening_messages(context, 'Why cache?')
                assert (len(messages) == 2) is expected
                if expected:
                    assert '[supported]' in messages[1].content
                    assert 'untrusted research leads' in messages[1].content
                    # A later revision cannot silently inherit the old assertion.
                    context.collector.sources = {'s1':record.model_copy(update={'content_revision':'r2'})}
                    assert 'stale: source revision changed' in opening_messages(context, 'Why cache?')[1].content

def test_rejected_claims_do_not_survive_in_the_summary():
    from generation.answer import AnswerDraft, DraftClaim, answer_question
    snapshot = RepoSnapshot(repository='https://github.com/a/b', sha='a'*40, commit_date=datetime.now(timezone.utc))
    record = SourceRecord(source_id='s1', kind=SourceKind.FILE, repository=snapshot.repository, snapshot_sha=snapshot.sha, content='The cache avoids repeated parsing.', url='https://github.com/a/b/blob/main/a.py')
    draft = AnswerDraft(summary='Invented 95% benchmark improvement.', claims=[DraftClaim(statement=record.content,label=ClaimLabel.DOCUMENTED,source_id='s1',quote=record.content)])
    class Model:
        def with_structured_output(self, schema): return self
        def invoke(self, prompt): return draft
    report, issues = answer_question('Why cache?',snapshot,[record],[],Coverage(repository=snapshot.repository,snapshot_sha=snapshot.sha),llm=Model())
    assert not issues
    assert '95%' not in report.summary
    assert report.claims[0].statement in report.summary


def test_tool_batches_respect_remaining_budget_and_account_scope(tmp_path, monkeypatch):
    from agent.nodes import run_tools
    from agent.state import new_state
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.prebuilt import ToolNode
    from langgraph.graph import StateGraph, START, END
    from agent.state import InvestigationState
    from functools import partial
    from models import InvestigationRequest
    from runtime import data_dir
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    monkeypatch.setattr(settings, 'max_tool_calls', 1)
    observed = []
    @tool
    def inspect_scope() -> str:
        """Inspect the current account scope."""
        observed.append(data_dir())
        return 'scoped'
    snapshot = RepoSnapshot(repository='https://github.com/a/b',sha='a'*40,commit_date=datetime.now(timezone.utc))
    state = new_state(InvestigationRequest(repository=snapshot.repository,question='Why?'),snapshot)
    state['messages'] = [AIMessage(content='', tool_calls=[{'id':str(i),'name':'inspect_scope','args':{}} for i in (1,2)])]
    builder = StateGraph(InvestigationState)
    builder.add_node('execute', partial(run_tools,tool_node=ToolNode([inspect_scope]),context=SimpleNamespace(collector=SimpleNamespace(sources={}))))
    builder.add_edge(START,'execute')
    builder.add_edge('execute',END)
    with user_workspace('1'):
        result = builder.compile().invoke(state)
    assert observed == [tmp_path/'users'/'1']
    assert result['tool_calls'] == 1
    tools = [message for message in result['messages'] if message.type == 'tool']
    assert len(tools) == 2
    assert 'Not executed' in tools[1].content
